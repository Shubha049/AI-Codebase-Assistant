from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import PurePosixPath

from sqlalchemy.orm import Session

from app.db.models import Chunk, CodeSymbol, DependencyEdge, ImportStatement, Repository


@dataclass(frozen=True)
class ArchitectureNode:
    id: str
    path: str
    kind: str
    language: str | None
    symbol_count: int
    chunk_count: int
    inbound_count: int
    outbound_count: int


@dataclass(frozen=True)
class ArchitectureEdge:
    source: str
    target: str
    weight: int = 1


def _language_for(path: str, chunks: list[Chunk]) -> str | None:
    for chunk in chunks:
        if chunk.file_path == path:
            return chunk.language
    return None


def _build_file_data(db: Session, repo_id: str):
    chunks = db.query(Chunk).filter(Chunk.repository_id == repo_id).all()
    symbols = db.query(CodeSymbol).filter(CodeSymbol.repository_id == repo_id).all()
    imports = db.query(ImportStatement).filter(ImportStatement.repository_id == repo_id).all()
    edges = db.query(DependencyEdge).filter(DependencyEdge.repository_id == repo_id).all()

    files: set[str] = {c.file_path for c in chunks}
    files.update(s.file_path for s in symbols)
    files.update(i.file_path for i in imports)
    for edge in edges:
        files.add(edge.source_file)
        files.add(edge.target_file)

    symbol_counts = defaultdict(int)
    chunk_counts = defaultdict(int)
    import_counts = defaultdict(int)
    inbound = defaultdict(int)
    outbound = defaultdict(int)
    edge_weights = defaultdict(int)

    for s in symbols:
        symbol_counts[s.file_path] += 1
    for c in chunks:
        chunk_counts[c.file_path] += 1
    for i in imports:
        import_counts[i.file_path] += 1
    for e in edges:
        outbound[e.source_file] += 1
        inbound[e.target_file] += 1
        edge_weights[(e.source_file, e.target_file)] += 1

    languages = {}
    for c in chunks:
        languages.setdefault(c.file_path, c.language)

    return files, symbols, chunks, imports, edges, symbol_counts, chunk_counts, import_counts, inbound, outbound, edge_weights, languages


def get_overview(db: Session, repo: Repository) -> dict:
    data = _build_file_data(db, repo.id)
    files, symbols, chunks, imports, edges, symbol_counts, chunk_counts, import_counts, inbound, outbound, edge_weights, languages = data

    directories = sorted({str(PurePosixPath(p).parent) for p in files if str(PurePosixPath(p).parent) != "."})
    languages_count: dict[str, int] = defaultdict(int)
    for path in files:
        language = languages.get(path)
        if language:
            languages_count[language] += 1

    return {
        "repository_id": repo.id,
        "repository_name": repo.name,
        "status": repo.status,
        "file_count": len(files),
        "symbol_count": len(symbols),
        "chunk_count": len(chunks),
        "import_count": len(imports),
        "dependency_edge_count": len(edges),
        "directory_count": len(directories),
        "languages": dict(sorted(languages_count.items())),
        "frameworks": repo.frameworks or [],
        "build_systems": repo.build_systems or [],
        "top_files_by_centrality": _top_central_files(files, inbound, outbound),
        "top_files_by_symbols": sorted(
            [{"path": p, "symbol_count": symbol_counts[p]} for p in files],
            key=lambda x: (-x["symbol_count"], x["path"]),
        )[:10],
    }


def _top_central_files(files: set[str], inbound: dict[str, int], outbound: dict[str, int]) -> list[dict]:
    rows = [
        {"path": p, "inbound": inbound[p], "outbound": outbound[p], "centrality": inbound[p] + outbound[p]}
        for p in files
    ]
    return sorted(rows, key=lambda x: (-x["centrality"], -x["inbound"], x["path"]))[:10]


def get_graph(db: Session, repo_id: str, max_nodes: int = 1000) -> dict:
    data = _build_file_data(db, repo_id)
    files, symbols, chunks, imports, edges, symbol_counts, chunk_counts, import_counts, inbound, outbound, edge_weights, languages = data

    # Include isolated files too; otherwise an architecture visualization hides
    # perfectly valid modules that simply have no resolved internal imports.
    ranked_files = sorted(files, key=lambda p: (-(inbound[p] + outbound[p]), p))
    visible = set(ranked_files[:max_nodes])

    nodes = [
        {
            "id": p,
            "path": p,
            "kind": "file",
            "language": languages.get(p),
            "symbol_count": symbol_counts[p],
            "chunk_count": chunk_counts[p],
            "inbound_count": inbound[p],
            "outbound_count": outbound[p],
        }
        for p in ranked_files[:max_nodes]
    ]
    graph_edges = [
        {"source": s, "target": t, "weight": w}
        for (s, t), w in sorted(edge_weights.items())
        if s in visible and t in visible
    ]

    return {
        "repository_id": repo_id,
        "nodes": nodes,
        "edges": graph_edges,
        "truncated": len(files) > max_nodes,
        "total_nodes": len(files),
        "total_edges": len(edges),
    }


def get_file_detail(db: Session, repo_id: str, file_path: str) -> dict:
    chunks = db.query(Chunk).filter(Chunk.repository_id == repo_id, Chunk.file_path == file_path).order_by(Chunk.start_line).all()
    symbols = db.query(CodeSymbol).filter(CodeSymbol.repository_id == repo_id, CodeSymbol.file_path == file_path).order_by(CodeSymbol.start_line).all()
    imports = db.query(ImportStatement).filter(ImportStatement.repository_id == repo_id, ImportStatement.file_path == file_path).order_by(ImportStatement.line_number).all()
    outgoing = db.query(DependencyEdge).filter(DependencyEdge.repository_id == repo_id, DependencyEdge.source_file == file_path).all()
    incoming = db.query(DependencyEdge).filter(DependencyEdge.repository_id == repo_id, DependencyEdge.target_file == file_path).all()

    if not chunks and not symbols and not imports and not outgoing and not incoming:
        return None

    language = chunks[0].language if chunks else (symbols[0].language if symbols else (imports[0].language if imports else None))
    return {
        "repository_id": repo_id,
        "path": file_path,
        "language": language,
        "symbol_count": len(symbols),
        "chunk_count": len(chunks),
        "import_count": len(imports),
        "symbols": [
            {"name": s.name, "type": s.symbol_type.value, "parent_name": s.parent_name, "start_line": s.start_line, "end_line": s.end_line, "docstring": s.docstring}
            for s in symbols
        ],
        "imports": [
            {"module": i.module, "imported_names": i.imported_names, "line_number": i.line_number, "language": i.language}
            for i in imports
        ],
        "dependencies": sorted({e.target_file for e in outgoing}),
        "dependents": sorted({e.source_file for e in incoming}),
    }


def get_impact(db: Session, repo_id: str, file_path: str, depth: int = 2) -> dict:
    edges = db.query(DependencyEdge).filter(DependencyEdge.repository_id == repo_id).all()
    forward: dict[str, set[str]] = defaultdict(set)
    reverse: dict[str, set[str]] = defaultdict(set)
    for e in edges:
        forward[e.source_file].add(e.target_file)
        reverse[e.target_file].add(e.source_file)

    def walk(graph: dict[str, set[str]]) -> list[dict]:
        seen = {file_path}
        frontier = {file_path}
        rows = []
        for current_depth in range(1, depth + 1):
            nxt = set()
            for node in frontier:
                nxt.update(graph.get(node, set()))
            nxt -= seen
            for node in sorted(nxt):
                rows.append({"path": node, "depth": current_depth})
            seen.update(nxt)
            frontier = nxt
            if not frontier:
                break
        return rows

    return {
        "repository_id": repo_id,
        "file_path": file_path,
        "depth": depth,
        "dependencies": walk(forward),
        "dependents": walk(reverse),
    }
