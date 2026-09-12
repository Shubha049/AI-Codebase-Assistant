"""
The Phase 2 analysis pipeline: given a repository already extracted and
scanned (Phase 1), parses every analyzable file, resolves the internal
dependency graph, detects frameworks/build systems, and persists all of
it. Runs as a background task after upload — see repos.py.

Designed so a failure on any ONE file never aborts the whole run (each
file's parse errors are recorded, not raised), but a failure in the
pipeline's own orchestration (DB write failure, etc.) does mark the job
and repository as failed — that's a real infrastructure problem, not an
expected per-file edge case.
"""
from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import (
    CodeSymbol,
    DependencyEdge,
    ImportStatement,
    IndexingJob,
    JobStage,
    JobStatus,
    Repository,
    RepoStatus,
    SymbolType,
)
from app.db.session import SessionLocal
from app.services.dependency_graph.resolver import ImportToResolve, build_dependency_graph
from app.services.framework_detection.detector import detect_frameworks_and_build_systems
from app.services.ingestion.scanner import scan_repository
from app.services.parsing.orchestrator import parse_file

logger = logging.getLogger(__name__)


def run_analysis_pipeline(repository_id: str) -> None:
    """
    Entry point dispatched via FastAPI BackgroundTasks. Opens its OWN
    database session — cannot reuse the request-scoped one, since this
    runs after the HTTP response has already been sent.
    """
    db = SessionLocal()
    job = IndexingJob(repository_id=repository_id, stage=JobStage.PARSING, status=JobStatus.RUNNING)
    db.add(job)
    db.commit()

    try:
        repo = db.get(Repository, repository_id)
        if repo is None:
            logger.error("run_analysis_pipeline: repository %s not found", repository_id)
            return

        repo.status = RepoStatus.PARSING
        db.commit()

        settings = get_settings()
        repo_dir = settings.repo_storage_dir / repository_id

        scan_result = scan_repository(repo_dir)
        analyzable_paths = scan_result.analyzable_file_paths
        total = len(analyzable_paths) or 1

        symbol_count = 0
        imports_to_resolve: list[ImportToResolve] = []
        files_with_errors = 0

        for i, rel_path in enumerate(analyzable_paths):
            file_disk_path = repo_dir / rel_path
            try:
                source = file_disk_path.read_bytes()
            except OSError as exc:
                logger.warning("Could not read %s: %s", rel_path, exc)
                files_with_errors += 1
                continue

            result = parse_file(rel_path, source)
            if result.error:
                files_with_errors += 1
            else:
                for sym in result.symbols:
                    db.add(CodeSymbol(
                        repository_id=repository_id,
                        file_path=rel_path,
                        language=result.language,
                        symbol_type=SymbolType(sym.symbol_type),
                        name=sym.name,
                        parent_name=sym.parent_name,
                        start_line=sym.start_line,
                        end_line=sym.end_line,
                        docstring=sym.docstring,
                    ))
                    symbol_count += 1

                for imp in result.imports:
                    db.add(ImportStatement(
                        repository_id=repository_id,
                        file_path=rel_path,
                        language=result.language,
                        module=imp.module,
                        imported_names=imp.imported_names,
                        line_number=imp.line_number,
                    ))
                    imports_to_resolve.append(ImportToResolve(
                        source_file=rel_path, language=result.language, module=imp.module,
                    ))

            job.progress_percent = int((i + 1) / total * 70)  # parsing = first 70%
            if (i + 1) % 25 == 0:  # commit in batches, not one row at a time
                db.commit()

        db.commit()

        # --- Dependency graph (next 20%) ---
        known_files = set(analyzable_paths)
        edges = build_dependency_graph(imports_to_resolve, known_files)
        for edge in edges:
            db.add(DependencyEdge(
                repository_id=repository_id,
                source_file=edge.source_file,
                target_file=edge.target_file,
            ))
        job.progress_percent = 90
        db.commit()

        # --- Framework / build-system detection (last 10%) ---
        detection = detect_frameworks_and_build_systems(repo_dir)
        repo.frameworks = [f.name for f in detection.frameworks]
        repo.build_systems = detection.build_systems

        repo.symbol_count = symbol_count
        repo.parsed_file_count = len(analyzable_paths) - files_with_errors
        repo.dependency_edge_count = len(edges)
        repo.status = RepoStatus.ANALYZED

        job.status = JobStatus.COMPLETED
        job.progress_percent = 100
        job.message = (
            f"Parsed {repo.parsed_file_count}/{len(analyzable_paths)} files "
            f"({files_with_errors} with errors), {symbol_count} symbols, "
            f"{len(edges)} dependency edges, {len(detection.frameworks)} frameworks detected."
        )
        from datetime import datetime, timezone
        job.completed_at = datetime.now(timezone.utc)
        db.commit()

        logger.info(
            "Analysis pipeline completed for repo %s: %s",
            repository_id, job.message,
        )

        # Phase 3: chunking runs immediately after analysis, chained in the
        # same background task rather than a second separately-scheduled
        # one — simpler to reason about (one task = one full pipeline run
        # per upload). run_chunking_pipeline opens its own independent DB
        # session, so this outer `db` doesn't need closing first.
        from app.services.chunk_generation_pipeline import run_chunking_pipeline
        run_chunking_pipeline(repository_id)
        return

    except Exception as exc:  # noqa: BLE001 - top-level pipeline guard
        logger.exception("Analysis pipeline failed for repo %s", repository_id)
        db.rollback()
        job.status = JobStatus.FAILED
        job.message = str(exc)
        repo = db.get(Repository, repository_id)
        if repo is not None:
            repo.status = RepoStatus.FAILED
            repo.error_message = f"Analysis pipeline failed: {exc}"
        db.commit()
    finally:
        db.close()
