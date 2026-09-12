from __future__ import annotations

import logging
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from textwrap import shorten

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Chunk, CodeSymbol, DependencyEdge, DocumentationArtifact, ImportStatement, Repository
from app.services.llm import LLMError, build_llm_provider

logger = logging.getLogger(__name__)


def _safe_source_stats(root: Path, files: set[str]) -> tuple[int, int]:
    total_bytes = 0
    readable = 0
    for rel in files:
        path = root / rel
        try:
            total_bytes += path.stat().st_size
            readable += 1
        except OSError:
            continue
    return readable, total_bytes


def _file_tree(paths: set[str]) -> str:
    tree: dict = {}
    for path in sorted(paths):
        node = tree
        parts = Path(path).parts
        for part in parts:
            node = node.setdefault(part, {})

    lines: list[str] = []
    def walk(node: dict, prefix: str = ""):
        items = sorted(node.items())
        for idx, (name, children) in enumerate(items):
            branch = "└── " if idx == len(items) - 1 else "├── "
            lines.append(prefix + branch + name)
            if children:
                walk(children, prefix + ("    " if idx == len(items) - 1 else "│   "))
    walk(tree)
    return "\n".join(lines)


def _module_rows(files: set[str], symbols: list[CodeSymbol], imports: list[ImportStatement], chunks: list[Chunk], edges: list[DependencyEdge]) -> list[dict]:
    sym = Counter(s.file_path for s in symbols)
    imp = Counter(i.file_path for i in imports)
    chk = Counter(c.file_path for c in chunks)
    out = Counter(e.source_file for e in edges)
    inc = Counter(e.target_file for e in edges)
    languages: dict[str, str] = {}
    for c in chunks:
        languages.setdefault(c.file_path, c.language)
    rows = []
    for path in sorted(files):
        rows.append({
            "path": path,
            "language": languages.get(path, "unknown"),
            "symbols": sym[path],
            "chunks": chk[path],
            "imports": imp[path],
            "dependencies": out[path],
            "dependents": inc[path],
        })
    return rows


def _structural_markdown(db: Session, repo: Repository) -> str:
    symbols = db.query(CodeSymbol).filter(CodeSymbol.repository_id == repo.id).order_by(CodeSymbol.file_path, CodeSymbol.start_line).all()
    imports = db.query(ImportStatement).filter(ImportStatement.repository_id == repo.id).order_by(ImportStatement.file_path, ImportStatement.line_number).all()
    chunks = db.query(Chunk).filter(Chunk.repository_id == repo.id).order_by(Chunk.file_path, Chunk.start_line).all()
    edges = db.query(DependencyEdge).filter(DependencyEdge.repository_id == repo.id).all()

    files: set[str] = {c.file_path for c in chunks}
    files.update(s.file_path for s in symbols)
    files.update(i.file_path for i in imports)
    for e in edges:
        files.update((e.source_file, e.target_file))

    root = Path(repo.storage_path)
    readable, total_bytes = _safe_source_stats(root, files)
    modules = _module_rows(files, symbols, imports, chunks, edges)
    language_counts = Counter(row["language"] for row in modules if row["language"] != "unknown")
    symbol_counts = Counter(s.file_path for s in symbols)
    inbound = Counter(e.target_file for e in edges)
    outbound = Counter(e.source_file for e in edges)

    lines = [
        f"# {repo.name}",
        "",
        "> Generated from the repository's analyzed source, symbols, imports, semantic chunks, and resolved internal dependency graph.",
        "> This document describes observed repository structure; it does not claim behavior that the analysis cannot establish.",
        "",
        "## Overview",
        "",
        f"- Repository status: `{repo.status.value if hasattr(repo.status, 'value') else repo.status}`",
        f"- Analyzed files: **{len(files)}**",
        f"- Readable source files at generation time: **{readable}**",
        f"- Approximate source size: **{total_bytes:,} bytes**",
        f"- Symbols: **{len(symbols)}**",
        f"- Imports: **{len(imports)}**",
        f"- Semantic chunks: **{len(chunks)}**",
        f"- Internal dependency edges: **{len(edges)}**",
        "",
        "## Technology Stack",
        "",
        f"**Frameworks:** {', '.join(f'`{x}`' for x in (repo.frameworks or [])) or 'None detected'}",
        f"**Build systems:** {', '.join(f'`{x}`' for x in (repo.build_systems or [])) or 'None detected'}",
        f"**Languages:** {', '.join(f'`{x}` ({language_counts[x]} files)' for x in sorted(language_counts)) or 'Not determined'}",
        "",
        "## Repository Structure",
        "",
        "```text",
        _file_tree(files) or "(no analyzed files)",
        "```",
        "",
        "## Architecture",
        "",
    ]

    if edges:
        lines.append("The following files participate in the highest-volume internal dependency relationships:")
        lines.append("")
        central = sorted(files, key=lambda p: (-(inbound[p] + outbound[p]), p))[:15]
        for path in central:
            degree = inbound[path] + outbound[path]
            if degree:
                lines.append(f"- `{path}` — {inbound[path]} inbound, {outbound[path]} outbound dependency edges")
    else:
        lines.append("No resolved internal dependency edges were recorded by the repository analyzer.")
    lines += ["", "## Modules and Files", "", "| File | Language | Symbols | Chunks | Dependencies | Dependents |", "|---|---|---:|---:|---:|---:|"]
    for row in modules[:500]:
        lines.append(f"| `{row['path']}` | `{row['language']}` | {row['symbols']} | {row['chunks']} | {row['dependencies']} | {row['dependents']} |")
    if len(modules) > 500:
        lines.append(f"| … | … | … | … | … | … |")
        lines.append(f"\nOnly the first 500 files are listed in the table; the full repository remains available through the API.")

    lines += ["", "## Symbols", ""]
    by_file: dict[str, list[CodeSymbol]] = defaultdict(list)
    for s in symbols:
        by_file[s.file_path].append(s)
    for path in sorted(by_file):
        lines.append(f"### `{path}`")
        for s in by_file[path][:100]:
            kind = s.symbol_type.value if hasattr(s.symbol_type, "value") else str(s.symbol_type)
            parent = f" (class `{s.parent_name}`)" if s.parent_name else ""
            doc = f" — {shorten(' '.join((s.docstring or '').split()), width=180, placeholder='…')}" if s.docstring else ""
            lines.append(f"- `{kind}` **{s.name}**{parent} — lines {s.start_line}-{s.end_line}{doc}")
        if len(by_file[path]) > 100:
            lines.append("- … additional symbols omitted from this section")
        lines.append("")

    lines += ["## Imports", ""]
    if imports:
        for i in imports[:500]:
            names = f" ({', '.join(i.imported_names)})" if i.imported_names else ""
            lines.append(f"- `{i.file_path}:{i.line_number}` → `{i.module}`{names}")
        if len(imports) > 500:
            lines.append("- … additional imports available through repository analysis APIs")
    else:
        lines.append("No imports were recorded.")

    lines += ["", "## Documentation Notes", "", "- This is a structural documentation pass generated from repository analysis data.", "- It does not execute repository code.", "- It does not infer undocumented business rules as facts.", "- Security findings remain in the Security Scanner and are not duplicated here.", "- AI-enhanced prose is optional and is marked separately when used.", ""]
    return "\n".join(lines)


def _enhance_with_llm(markdown: str, repo: Repository) -> tuple[str, str, str]:
    settings = get_settings()
    provider = build_llm_provider(settings)
    prompt = (
        "Improve this repository documentation without inventing facts. Preserve all paths, symbols, "
        "numbers, and architecture relationships exactly. You may add concise explanations only when "
        "supported by the supplied document. Return Markdown only.\n\n"
        f"REPOSITORY: {repo.name}\n\nDOCUMENT:\n{markdown}"
    )
    response = provider.generate(
        "You are a technical documentation editor. The supplied repository documentation is authoritative evidence. Never fabricate implementation details.",
        prompt,
        None,
    )
    if not response.text.strip():
        raise LLMError("LLM returned an empty documentation response.")
    return response.text, provider.provider_name, provider.model_name


def generate_documentation(db: Session, repo: Repository, use_llm: bool = False) -> DocumentationArtifact:
    artifact = DocumentationArtifact(repository_id=repo.id, status="running", format="markdown", used_llm=False)
    db.add(artifact)
    db.commit()
    db.refresh(artifact)
    try:
        content = _structural_markdown(db, repo)
        if use_llm:
            content, provider_name, model_name = _enhance_with_llm(content, repo)
            artifact.used_llm = True
            artifact.llm_provider = provider_name
            artifact.llm_model = model_name
        artifact.content = content
        artifact.status = "completed"
        artifact.completed_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(artifact)
        return artifact
    except Exception as exc:
        db.rollback()
        artifact = db.get(DocumentationArtifact, artifact.id)
        if artifact:
            artifact.status = "failed"
            artifact.error_message = str(exc)[:2000]
            artifact.completed_at = datetime.now(timezone.utc)
            db.commit()
        raise


def latest_documentation(db: Session, repo_id: str) -> DocumentationArtifact | None:
    return (
        db.query(DocumentationArtifact)
        .filter(DocumentationArtifact.repository_id == repo_id)
        .order_by(DocumentationArtifact.created_at.desc())
        .first()
    )
