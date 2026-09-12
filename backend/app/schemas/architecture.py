from __future__ import annotations

from pydantic import BaseModel, Field


class CentralFile(BaseModel):
    path: str
    inbound: int = 0
    outbound: int = 0
    centrality: int = 0


class SymbolHotspot(BaseModel):
    path: str
    symbol_count: int


class ArchitectureOverviewResponse(BaseModel):
    repository_id: str
    repository_name: str
    status: str
    file_count: int
    symbol_count: int
    chunk_count: int
    import_count: int
    dependency_edge_count: int
    directory_count: int
    languages: dict[str, int]
    frameworks: list[str]
    build_systems: list[str]
    top_files_by_centrality: list[CentralFile]
    top_files_by_symbols: list[SymbolHotspot]


class ArchitectureNode(BaseModel):
    id: str
    path: str
    kind: str
    language: str | None
    symbol_count: int
    chunk_count: int
    inbound_count: int
    outbound_count: int


class ArchitectureEdge(BaseModel):
    source: str
    target: str
    weight: int = 1


class ArchitectureGraphResponse(BaseModel):
    repository_id: str
    nodes: list[ArchitectureNode]
    edges: list[ArchitectureEdge]
    truncated: bool
    total_nodes: int
    total_edges: int


class ArchitectureSymbol(BaseModel):
    name: str
    type: str
    parent_name: str | None
    start_line: int
    end_line: int
    docstring: str | None


class ArchitectureImport(BaseModel):
    module: str
    imported_names: list
    line_number: int
    language: str


class ArchitectureFileResponse(BaseModel):
    repository_id: str
    path: str
    language: str | None
    symbol_count: int
    chunk_count: int
    import_count: int
    symbols: list[ArchitectureSymbol]
    imports: list[ArchitectureImport]
    dependencies: list[str]
    dependents: list[str]


class ImpactItem(BaseModel):
    path: str
    depth: int


class ArchitectureImpactResponse(BaseModel):
    repository_id: str
    file_path: str
    depth: int = Field(ge=1, le=10)
    dependencies: list[ImpactItem]
    dependents: list[ImpactItem]
