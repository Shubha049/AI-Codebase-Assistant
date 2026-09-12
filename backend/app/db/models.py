import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RepoStatus(str, enum.Enum):
    UPLOADING = "uploading"
    EXTRACTING = "extracting"
    SCANNING = "scanning"
    SCANNED = "scanned"          # Phase 1 end state: scan complete, nothing AI-related done yet
    PARSING = "parsing"          # Phase 2: AST extraction + dependency graph running in background
    ANALYZED = "analyzed"        # Phase 2 end state: parsing + dependency graph + framework detection done
    CHUNKING = "chunking"        # Phase 3: chunk generation running in background
    CHUNKED = "chunked"          # Phase 3 end state: semantic chunks generated, ready for embedding
    INDEXING = "indexing"        # Phase 4+
    READY = "ready"              # Phase 4+: fully indexed, Q&A available
    FAILED = "failed"


class SourceType(str, enum.Enum):
    ZIP = "zip"
    GITHUB = "github"            # not implemented until a later phase


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(512))
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Repository(Base):
    __tablename__ = "repositories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    owner_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    source_type: Mapped[SourceType] = mapped_column(Enum(SourceType), default=SourceType.ZIP)
    original_filename: Mapped[str | None] = mapped_column(String(512), nullable=True)
    storage_path: Mapped[str] = mapped_column(String(1024))

    status: Mapped[RepoStatus] = mapped_column(Enum(RepoStatus), default=RepoStatus.UPLOADING)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    file_count: Mapped[int] = mapped_column(Integer, default=0)
    total_size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    language_breakdown: Mapped[dict] = mapped_column(JSON, default=dict)
    # Fires when a file's extension is analyzable but its content couldn't
    # be scanned for some reason (binary despite extension, decode error, etc.)
    skipped_file_count: Mapped[int] = mapped_column(Integer, default=0)

    # --- Phase 2: analysis results ---
    frameworks: Mapped[list] = mapped_column(JSON, default=list)      # e.g. ["FastAPI", "React"]
    build_systems: Mapped[list] = mapped_column(JSON, default=list)   # e.g. ["pip", "npm"]
    symbol_count: Mapped[int] = mapped_column(Integer, default=0)
    parsed_file_count: Mapped[int] = mapped_column(Integer, default=0)
    dependency_edge_count: Mapped[int] = mapped_column(Integer, default=0)

    # --- Phase 3: chunking results ---
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    chunked_file_count: Mapped[int] = mapped_column(Integer, default=0)

    # --- Phase 4: embedding / vector index results ---
    vector_count: Mapped[int] = mapped_column(Integer, default=0)
    embedding_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    embedding_dimension: Mapped[int | None] = mapped_column(Integer, nullable=True)
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    jobs: Mapped[list["IndexingJob"]] = relationship(
        back_populates="repository", cascade="all, delete-orphan"
    )


class JobStage(str, enum.Enum):
    EXTRACTION = "extraction"
    SCANNING = "scanning"
    PARSING = "parsing"
    DEPENDENCY_GRAPH = "dependency_graph"
    FRAMEWORK_DETECTION = "framework_detection"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"


class JobStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class IndexingJob(Base):
    """
    Tracks progress of a (potentially long-running) processing stage for a
    repository. Phase 1 stages (extraction, scanning) run synchronously and
    complete this row immediately — the table exists now so Phase 3/4's
    genuinely long-running background stages (parsing, embedding) don't
    require a schema migration later.
    """
    __tablename__ = "indexing_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    repository_id: Mapped[str] = mapped_column(ForeignKey("repositories.id"))
    stage: Mapped[JobStage] = mapped_column(Enum(JobStage))
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus), default=JobStatus.PENDING)
    progress_percent: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    repository: Mapped["Repository"] = relationship(back_populates="jobs")


# =============================================================================
# Phase 2: Repository Analysis Engine
# =============================================================================

class SymbolType(str, enum.Enum):
    FUNCTION = "function"
    METHOD = "method"
    CLASS = "class"
    ARROW_FUNCTION = "arrow_function"

    @classmethod
    def _missing_(cls, value: object) -> "SymbolType":
        if not isinstance(value, str):
            return cls.FUNCTION
        st = value.lower().strip()
        if st in {"arrow_function"}:
            return cls.ARROW_FUNCTION
        if st in {"method", "method_definition", "generator_method", "getter", "setter", "constructor", "object_method"}:
            return cls.METHOD
        if st in {
            "class", "class_declaration", "class_definition", "abstract_class_declaration",
            "class_expression", "interface", "interface_declaration", "struct", "struct_declaration",
            "enum", "enum_declaration", "type_alias", "type_alias_declaration",
        }:
            return cls.CLASS
        return cls.FUNCTION


class CodeSymbol(Base):
    """A function/class/method extracted via tree-sitter AST parsing."""
    __tablename__ = "code_symbols"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    repository_id: Mapped[str] = mapped_column(ForeignKey("repositories.id"))

    file_path: Mapped[str] = mapped_column(String(1024))   # relative to repo root
    language: Mapped[str] = mapped_column(String(50))
    symbol_type: Mapped[SymbolType] = mapped_column(Enum(SymbolType))
    name: Mapped[str] = mapped_column(String(255))
    parent_name: Mapped[str | None] = mapped_column(String(255), nullable=True)  # class name, for methods

    start_line: Mapped[int] = mapped_column(Integer)
    end_line: Mapped[int] = mapped_column(Integer)
    docstring: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ImportStatement(Base):
    """A single import/require statement extracted from a parsed file."""
    __tablename__ = "import_statements"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    repository_id: Mapped[str] = mapped_column(ForeignKey("repositories.id"))

    file_path: Mapped[str] = mapped_column(String(1024))
    language: Mapped[str] = mapped_column(String(50))
    module: Mapped[str] = mapped_column(String(1024))       # raw target, e.g. "app.services.foo" or "./utils"
    imported_names: Mapped[list] = mapped_column(JSON, default=list)
    line_number: Mapped[int] = mapped_column(Integer)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class DependencyEdge(Base):
    """
    A resolved internal dependency: source_file imports target_file, both
    within the same repository. External/unresolvable imports (stdlib,
    third-party packages) are not stored as edges — only genuine
    intra-repo structure, which is what makes a dependency graph useful.
    """
    __tablename__ = "dependency_edges"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    repository_id: Mapped[str] = mapped_column(ForeignKey("repositories.id"))

    source_file: Mapped[str] = mapped_column(String(1024))
    target_file: Mapped[str] = mapped_column(String(1024))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class SecuritySeverity(str, enum.Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class SecurityCategory(str, enum.Enum):
    SECRET = "secret"
    COMMAND_INJECTION = "command_injection"
    CODE_INJECTION = "code_injection"
    SQL_INJECTION = "sql_injection"
    INSECURE_DESERIALIZATION = "insecure_deserialization"
    WEAK_CRYPTO = "weak_crypto"
    TLS = "tls"
    INSECURE_CONFIG = "insecure_config"


class SecurityScan(Base):
    __tablename__ = "security_scans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    repository_id: Mapped[str] = mapped_column(ForeignKey("repositories.id"))
    status: Mapped[str] = mapped_column(String(20), default="completed")
    findings_count: Mapped[int] = mapped_column(Integer, default=0)
    critical_count: Mapped[int] = mapped_column(Integer, default=0)
    high_count: Mapped[int] = mapped_column(Integer, default=0)
    medium_count: Mapped[int] = mapped_column(Integer, default=0)
    low_count: Mapped[int] = mapped_column(Integer, default=0)
    info_count: Mapped[int] = mapped_column(Integer, default=0)
    scanned_files: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SecurityFinding(Base):
    __tablename__ = "security_findings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    scan_id: Mapped[str] = mapped_column(ForeignKey("security_scans.id"))
    repository_id: Mapped[str] = mapped_column(ForeignKey("repositories.id"))
    rule_id: Mapped[str] = mapped_column(String(100))
    category: Mapped[SecurityCategory] = mapped_column(Enum(SecurityCategory))
    severity: Mapped[SecuritySeverity] = mapped_column(Enum(SecuritySeverity))
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    file_path: Mapped[str] = mapped_column(String(1024))
    line_number: Mapped[int] = mapped_column(Integer)
    evidence: Mapped[str] = mapped_column(Text)
    remediation: Mapped[str] = mapped_column(Text)
    confidence: Mapped[str] = mapped_column(String(20), default="medium")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ChunkType(str, enum.Enum):
    FUNCTION = "function"                # whole function, fits within token budget
    METHOD = "method"                    # whole method, fits within token budget
    CLASS = "class"                      # whole class with no methods (e.g. dataclass, constants holder), fits within token budget
    CLASS_HEADER = "class_header"        # class signature + docstring, methods chunked separately
    MODULE_LEVEL = "module_level"        # code not covered by any symbol (imports, top-level statements)
    FUNCTION_WINDOW = "function_window"  # a function too large for one chunk, sliding-window split
    METHOD_WINDOW = "method_window"      # a method too large for one chunk, sliding-window split
    FILE_WINDOW = "file_window"          # basic_fallback-parsed file, chunked by sliding window over raw lines
    CODE_BLOCK = "code_block"            # fallback for generic code blocks or unmapped AST nodes
    UNKNOWN = "unknown"                  # safe fallback for unrecognized chunks

    @classmethod
    def _missing_(cls, value: object) -> "ChunkType":
        if not isinstance(value, str):
            return cls.CODE_BLOCK
        st = value.lower().strip()
        # Functions / Callables
        if st in {
            "arrow_function",
            "function_declaration",
            "function_definition",
            "generator_function",
            "generator_function_declaration",
            "function_expression",
            "async_function_definition",
            "lambda",
            "closure",
        }:
            return cls.FUNCTION
        # Methods
        if st in {
            "method_definition",
            "generator_method",
            "getter",
            "setter",
            "constructor",
            "object_method",
        }:
            return cls.METHOD
        # Classes / Types
        if st in {
            "class_declaration",
            "class_definition",
            "abstract_class_declaration",
            "class_expression",
            "interface",
            "interface_declaration",
            "struct",
            "struct_declaration",
            "type_alias",
            "type_alias_declaration",
            "enum",
            "enum_declaration",
        }:
            return cls.CLASS
        import logging
        logging.getLogger(__name__).warning(
            "Unrecognized chunk type %r; defaulting to ChunkType.CODE_BLOCK",
            value,
        )
        return cls.CODE_BLOCK


class Chunk(Base):
    """
    A semantic chunk of source code, ready for embedding in a later phase.
    Covers the WHOLE file's content, not just extracted symbols — gaps
    between/around symbols become MODULE_LEVEL chunks, and files that only
    got regex-fallback parsing (Phase 2) are covered by FILE_WINDOW chunks
    — so nothing in an analyzed repository is silently excluded from
    future retrieval.
    """
    __tablename__ = "chunks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    repository_id: Mapped[str] = mapped_column(ForeignKey("repositories.id"))

    file_path: Mapped[str] = mapped_column(String(1024))
    language: Mapped[str] = mapped_column(String(50))
    chunk_type: Mapped[ChunkType] = mapped_column(Enum(ChunkType))

    symbol_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    parent_symbol_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    start_line: Mapped[int] = mapped_column(Integer)
    end_line: Mapped[int] = mapped_column(Integer)

    content: Mapped[str] = mapped_column(Text)
    # Approximate — see Settings.chunk_max_tokens docstring. Not a real
    # tokenizer; no embedding provider has been chosen yet (Phase 4).
    token_count: Mapped[int] = mapped_column(Integer)

    content_hash: Mapped[str] = mapped_column(String(64), index=True)  # sha256 hex digest
    is_duplicate: Mapped[bool] = mapped_column(default=False)
    duplicate_of_chunk_id: Mapped[str | None] = mapped_column(
        ForeignKey("chunks.id"), nullable=True
    )

    # --- Phase 4: embedding status ---
    # NULL = not yet embedded. Set together whenever a vector is
    # (re)generated; embedding_model is compared against the CURRENT
    # provider's model on each indexing run so a provider/model change
    # correctly triggers re-embedding even if content_hash is unchanged.
    embedded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ChunkedFile(Base):
    """
    Tracks the content hash of each file's last chunking pass, so a
    re-triggered chunking run can skip files that haven't changed
    (incremental indexing) instead of re-chunking the entire repository
    every time.
    """
    __tablename__ = "chunked_files"
    __table_args__ = (
        UniqueConstraint("repository_id", "file_path", name="uq_chunked_files_repo_path"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    repository_id: Mapped[str] = mapped_column(ForeignKey("repositories.id"))

    file_path: Mapped[str] = mapped_column(String(1024))
    file_content_hash: Mapped[str] = mapped_column(String(64))
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)

    chunked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

# =============================================================================
# Phase 5: RAG conversation memory
# =============================================================================
class Conversation(Base):
    __tablename__ = "qa_conversations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    repository_id: Mapped[str] = mapped_column(ForeignKey("repositories.id"))
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)
    messages: Mapped[list["ConversationMessage"]] = relationship(back_populates="conversation", cascade="all, delete-orphan", order_by="ConversationMessage.created_at")


class ConversationMessage(Base):
    __tablename__ = "qa_conversation_messages"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("qa_conversations.id"))
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    conversation: Mapped["Conversation"] = relationship(back_populates="messages")

# =============================================================================
# Phase 9: repository-specific interview questions
# =============================================================================
class InterviewQuestionSet(Base):
    __tablename__ = "interview_question_sets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    repository_id: Mapped[str] = mapped_column(ForeignKey("repositories.id"))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    requested_count: Mapped[int] = mapped_column(Integer, default=10)
    difficulty: Mapped[str | None] = mapped_column(String(20), nullable=True)
    used_llm: Mapped[bool] = mapped_column(default=False)
    llm_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    llm_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    questions: Mapped[list] = mapped_column(JSON, default=list)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    @property
    def count(self) -> int:
        return self.requested_count

# =============================================================================
# Phase 8: generated repository documentation
# =============================================================================
class DocumentationArtifact(Base):
    __tablename__ = "documentation_artifacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    repository_id: Mapped[str] = mapped_column(ForeignKey("repositories.id"))
    status: Mapped[str] = mapped_column(String(20), default="completed")
    format: Mapped[str] = mapped_column(String(20), default="markdown")
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    used_llm: Mapped[bool] = mapped_column(default=False)
    llm_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    llm_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

