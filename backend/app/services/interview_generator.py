from __future__ import annotations
import json
import logging
import re
import uuid
from collections import Counter
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.config import get_settings
from app.db.models import CodeSymbol, DependencyEdge, Repository, SecurityFinding, SecurityScan, InterviewQuestionSet
from app.services.llm import LLMError, build_llm_provider

logger = logging.getLogger(__name__)

ALLOWED_TYPES = {"code_explanation", "architecture", "debugging", "security", "design"}


def _source(symbol: CodeSymbol) -> dict:
    return {"file": symbol.file_path, "start_line": symbol.start_line, "end_line": symbol.end_line, "symbol": symbol.name}


def _make_questions(db: Session, repo: Repository, count: int, difficulty: str | None, types: list[str] | None) -> list[dict]:
    symbols = db.query(CodeSymbol).filter(CodeSymbol.repository_id == repo.id).order_by(CodeSymbol.file_path, CodeSymbol.start_line).all()
    edges = db.query(DependencyEdge).filter(DependencyEdge.repository_id == repo.id).all()
    findings = db.query(SecurityFinding).filter(SecurityFinding.repository_id == repo.id).order_by(SecurityFinding.severity).limit(100).all()
    requested = [t for t in (types or []) if t in ALLOWED_TYPES] or list(ALLOWED_TYPES)
    levels = [difficulty] if difficulty else ["easy", "medium", "hard"]
    questions: list[dict] = []
    seen: set[str] = set()

    frameworks = repo.frameworks or []
    primary_lang = max(repo.language_breakdown.items(), key=lambda x: x[1])[0] if repo.language_breakdown else "the codebase"
    fw_str = ", ".join(frameworks) if frameworks else primary_lang

    pools: dict[str, list[dict]] = {
        "design": [],
        "architecture": [],
        "code_explanation": [],
        "debugging": [],
        "security": [],
    }

    def add_to_pool(qtype: str, level: str, question: str, answer: str, explanation: str, sources: list[dict]) -> None:
        key = re.sub(r"\W+", " ", question.lower()).strip()
        if key in seen:
            return
        seen.add(key)
        item = {
            "id": str(uuid.uuid4()),
            "question_type": qtype,
            "difficulty": level,
            "question": question,
            "expected_answer": answer,
            "explanation": explanation,
            "sources": sources,
        }
        pools.setdefault(qtype, []).append(item)

    # 1. CONCEPTUAL & SYSTEM DESIGN / SCALING QUESTIONS
    if "design" in requested:
        classes = [s for s in symbols if (getattr(s.symbol_type, "value", str(s.symbol_type)) == "class")]
        functions = [s for s in symbols if (getattr(s.symbol_type, "value", str(s.symbol_type)) in ("function", "arrow_function", "method"))]

        for idx, s in enumerate(classes[:10]):
            level = "hard" if "hard" in levels else levels[idx % len(levels)]
            add_to_pool(
                "design",
                level,
                f"How would you scale `{s.name}` in `{s.file_path}` if request throughput or dataset volume increased by 100x?",
                f"For `{s.name}` in `{s.file_path}` (lines {s.start_line}-{s.end_line}), a senior engineer should analyze bottleneck points (such as synchronous blocking I/O, memory footprint, or database locks), propose asynchronous background task queues (e.g., job workers or event streams), implement caching layers (e.g. Redis), and apply database indexing or connection pooling.",
                "Assesses distributed systems intuition, scalability foresight, and ability to evolve monolithic components into high-throughput services.",
                [_source(s)],
            )

        for idx, s in enumerate(functions[:10]):
            level = levels[idx % len(levels)]
            add_to_pool(
                "design",
                level,
                f"Why did the team choose the current design for `{s.name}` in `{s.file_path}`, and what alternative approaches could be considered?",
                f"`{s.name}` is implemented on lines {s.start_line}-{s.end_line} of `{s.file_path}`. The answer should analyze whether a functional vs. object-oriented pattern was chosen, evaluate error handling guarantees, and weigh trade-offs against alternatives like event-driven handling, pluggable pipelines, or higher-order composition.",
                "Tests technical reasoning, justification of design patterns, and critical evaluation of existing codebases.",
                [_source(s)],
            )

    # 2. ARCHITECTURAL & COUPLING QUESTIONS (from dependency graph)
    if "architecture" in requested and edges:
        grouped = Counter(e.source_file for e in edges)
        for idx, (source, degree) in enumerate(grouped.most_common(12)):
            targets = sorted({e.target_file for e in edges if e.source_file == source})[:6]
            level = levels[idx % len(levels)]
            add_to_pool(
                "architecture",
                level,
                f"Why is `{source}` a central architectural component in this codebase, and what trade-offs exist with its {degree} dependency connection(s)?",
                f"`{source}` directly imports and coordinates {degree} internal module(s): {', '.join(f'`{x}`' for x in targets)}. A strong answer should discuss how `{source}` acts as an architectural orchestrator, identify the coupling trade-offs, and explain how to prevent tight coupling using interface abstractions or dependency injection.",
                "Evaluates high-level architectural comprehension, dependency topology awareness, and ability to balance modular separation against cohesion.",
                [{"file": source, "dependencies": targets}],
            )

    # 3. TECHNOLOGY & FRAMEWORK SPECIFIC QUESTIONS
    if ("code_explanation" in requested or "architecture" in requested) and frameworks:
        for idx, s in enumerate(symbols[:15]):
            level = levels[idx % len(levels)]
            kind = getattr(s.symbol_type, "value", str(s.symbol_type))
            add_to_pool(
                "code_explanation",
                level,
                f"How does `{s.name}` in `{s.file_path}` leverage {fw_str} conventions and language patterns?",
                f"`{s.name}` ({kind} on lines {s.start_line}-{s.end_line}) integrates with the project's technology stack ({fw_str}). An ideal answer details how framework lifecycle hooks, schema models, type annotations, and routing or dependency injection patterns are utilized within `{s.file_path}`.",
                "Validates concrete fluency in the specific libraries, frameworks, and idioms used throughout the project.",
                [_source(s)],
            )

    # 4. CONCRETE CODE EXPLANATION & IMPLEMENTATION
    if "code_explanation" in requested:
        for idx, s in enumerate(symbols):
            level = levels[idx % len(levels)]
            kind = getattr(s.symbol_type, "value", str(s.symbol_type))
            doc = f" (Docstring: \"{s.docstring}\")" if s.docstring else ""
            add_to_pool(
                "code_explanation",
                level,
                f"What is the exact responsibility of the {kind} `{s.name}` in `{s.file_path}`?",
                f"`{s.name}` is a {kind} spanning lines {s.start_line}-{s.end_line} in `{s.file_path}`{doc}. The candidate should explain its input parameters, return values, control flow logic, and how callers in the repository interact with it.",
                "Tests ability to read, analyze, and succinctly articulate the core logic of specific code units.",
                [_source(s)],
            )

    # 5. DEBUGGING & FAILURE MODES
    if "debugging" in requested:
        for idx, s in enumerate(symbols):
            level = "hard" if "hard" in levels else ("medium" if "medium" in levels else "easy")
            add_to_pool(
                "debugging",
                level,
                f"If `{s.name}` in `{s.file_path}` begins failing or producing unexpected outputs, what step-by-step diagnostic workflow would you execute?",
                f"1. Check input arguments and validation contracts in `{s.file_path}` (lines {s.start_line}-{s.end_line}).\n2. Trace upstream callers and downstream imports linked to `{s.name}`.\n3. Add unit test assertions isolating the failure case.\n4. Inspect system logs, exception stack traces, and database/network transaction boundaries.",
                "Evaluates systematic debugging methodology, root-cause isolation skills, and observability awareness.",
                [_source(s)],
            )

    # 6. SECURITY & AUDIT REMEDIATION
    if "security" in requested:
        if findings:
            for f in findings:
                sev = getattr(f.severity, "value", str(f.severity))
                level = "hard" if sev in {"critical", "high"} else "medium"
                add_to_pool(
                    "security",
                    level,
                    f"How would you remediate the {f.title} ({sev.upper()}) finding in `{f.file_path}`?",
                    f"At line {f.line_number} of `{f.file_path}`, the scanner identified rule `{f.rule_id}` ({f.title}). Remediation involves: {f.remediation or 'replacing the unsafe pattern with secure parameterized/sanitized APIs, storing secrets in environment variables, and validating all inputs'}.",
                    f"Tests practical secure-coding knowledge and vulnerability remediation directly grounded in finding {f.rule_id}.",
                    [{"file": f.file_path, "line": f.line_number, "rule_id": f.rule_id, "severity": sev}],
                )
        else:
            for s in symbols[:6]:
                add_to_pool(
                    "security",
                    "medium",
                    f"What security precautions and input validation should be maintained when modifying `{s.name}` in `{s.file_path}`?",
                    f"Ensure all inputs received by `{s.name}` (lines {s.start_line}-{s.end_line}) are strictly validated and sanitized, verify authentication and authorization checks where applicable, avoid logging sensitive data, and adhere to least-privilege principles.",
                    "Checks security mindfulness when working on core business logic.",
                    [_source(s)],
                )

    # Interleave categories in round-robin fashion for balanced variety
    category_order = ["design", "architecture", "code_explanation", "debugging", "security"]
    active_categories = [c for c in category_order if c in requested] or category_order
    
    questions: list[dict] = []
    max_pool_len = max((len(pools.get(c, [])) for c in active_categories), default=0)
    for i in range(max_pool_len):
        for c in active_categories:
            pool = pools.get(c, [])
            if i < len(pool):
                questions.append(pool[i])
                if len(questions) >= count:
                    break
        if len(questions) >= count:
            break

    # Deterministic fallback ensures the endpoint always returns grounded content
    if not questions:
        questions.append({
            "id": str(uuid.uuid4()),
            "question_type": "design",
            "difficulty": levels[0],
            "question": f"What architectural layers and dependency paths would you review before contributing to `{repo.name}`?",
            "expected_answer": f"Review the primary entrypoints, framework configurations ({fw_str}), analyzed code symbols, and dependency edges to understand state flow and component responsibilities before proposing modifications.",
            "explanation": "Evaluates repo onboarding methodology and codebase exploration strategies.",
            "sources": [],
        })

    return questions[:count]


def _llm_enhance(questions: list[dict], repo: Repository) -> tuple[list[dict], str, str]:
    provider = build_llm_provider(get_settings())
    payload = json.dumps(questions, ensure_ascii=False)
    prompt = (
        "Improve these repository-specific interview questions. Preserve every cited file, line, "
        "rule ID and factual statement. Make the questions engaging, professional, and diverse "
        "(mixing conceptual design, scaling trade-offs, and technical framework questions). "
        "Return a JSON array with exactly the same objects/keys.\n\n"
        f"REPOSITORY: {repo.name}\nQUESTIONS:\n{payload}"
    )
    response = provider.generate("You are a senior technical interviewer. Repository evidence is authoritative.", prompt, None)
    try:
        parsed = json.loads(response.text)
        if not isinstance(parsed, list) or len(parsed) != len(questions):
            raise ValueError("invalid question array")
        return parsed, provider.provider_name, provider.model_name
    except (json.JSONDecodeError, ValueError) as exc:
        raise LLMError("LLM returned invalid interview-question JSON") from exc


def generate_interview(
    db: Session,
    repo: Repository,
    count: int,
    difficulty: str | None,
    types: list[str] | None,
    use_llm: bool = False,
    record_id: str | None = None,
) -> InterviewQuestionSet:
    record = db.get(InterviewQuestionSet, record_id) if record_id else None
    if record is None:
        record = InterviewQuestionSet(
            repository_id=repo.id,
            status="running",
            requested_count=count,
            difficulty=difficulty,
            used_llm=False,
            questions=[],
        )
        db.add(record)
        db.commit()
        db.refresh(record)
    else:
        record.status = "running"
        db.commit()

    try:
        questions = _make_questions(db, repo, count, difficulty, types)
        if use_llm:
            questions, pname, model = _llm_enhance(questions, repo)
            record.used_llm = True
            record.llm_provider = pname
            record.llm_model = model
        record.questions = questions
        record.status = "completed"
        record.completed_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(record)
        return record
    except Exception as exc:
        db.rollback()
        fresh = db.get(InterviewQuestionSet, record.id)
        if fresh:
            fresh.status = "failed"
            fresh.error_message = str(exc)[:2000]
            fresh.completed_at = datetime.now(timezone.utc)
            db.commit()
        raise


def latest_interview(db: Session, repo_id: str) -> InterviewQuestionSet | None:
    return (
        db.query(InterviewQuestionSet)
        .filter(InterviewQuestionSet.repository_id == repo_id)
        .order_by(InterviewQuestionSet.created_at.desc())
        .first()
    )

