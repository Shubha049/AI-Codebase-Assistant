"""
Resolves each file's extracted imports to another file INSIDE the same
repository, where possible. Only genuine intra-repo edges are returned —
stdlib imports, third-party packages, and anything that can't be matched
to a real file in the scanned set are simply not resolved (not treated as
an error; most imports in any real repo are external, and that's normal).

Two resolution strategies, chosen by import style:
  - Python: dotted module paths (`app.services.foo`) resolved against the
    repo's actual package structure (looking for `app/services/foo.py`
    or `app/services/foo/__init__.py`).
  - JS/TS: relative paths (`./utils`, `../lib/helpers`) resolved against
    the importing file's own directory, trying common extensions and
    index-file conventions.
Absolute/bare imports in JS/TS (`import x from "react"`) are external by
definition and never resolved — there's no ambiguity to guess at there.
"""
from __future__ import annotations

from dataclasses import dataclass
import posixpath
from pathlib import PurePosixPath

_JS_TS_EXTENSIONS_TO_TRY = ["", ".ts", ".tsx", ".js", ".jsx"]
_JS_TS_INDEX_FILES = ["index.ts", "index.tsx", "index.js", "index.jsx"]
_PYTHON_EXTENSIONS_TO_TRY = ["", ".py"]


@dataclass(frozen=True)
class ImportToResolve:
    source_file: str      # relative path of the file containing the import
    language: str          # "Python" | "JavaScript" | "TypeScript" | ...
    module: str             # raw import target as written


@dataclass(frozen=True)
class ResolvedEdge:
    source_file: str
    target_file: str


def build_dependency_graph(
    imports: list[ImportToResolve], known_files: set[str]
) -> list[ResolvedEdge]:
    edges: list[ResolvedEdge] = []
    seen: set[tuple[str, str]] = set()

    for imp in imports:
        target = _resolve_single_import(imp, known_files)
        if target is None:
            continue
        key = (imp.source_file, target)
        if key in seen or target == imp.source_file:
            continue  # de-dupe; also skip a (rare) self-import edge
        seen.add(key)
        edges.append(ResolvedEdge(source_file=imp.source_file, target_file=target))

    return edges


def _resolve_single_import(imp: ImportToResolve, known_files: set[str]) -> str | None:
    if imp.language == "Python":
        return _resolve_python_import(imp.module, known_files)
    if imp.language in ("JavaScript", "TypeScript"):
        return _resolve_js_ts_import(imp.module, imp.source_file, known_files)
    return None


def _resolve_python_import(module: str, known_files: set[str]) -> str | None:
    if not module or module.startswith("."):
        # Relative imports with only dots and no name (rare edge form) —
        # not handled; genuinely ambiguous without more context.
        return None
    module_as_path = module.replace(".", "/")

    # Pass 1: exact match assuming the scanned root IS the package root.
    for ext in _PYTHON_EXTENSIONS_TO_TRY:
        candidate = f"{module_as_path}{ext}"
        if candidate in known_files:
            return candidate
        init_candidate = f"{module_as_path}/__init__.py"
        if init_candidate in known_files:
            return init_candidate

    # Pass 2: suffix match. Real uploads very often have an extra wrapping
    # directory the source code doesn't know about — e.g. a GitHub zip
    # download nests everything under "reponame-main/", but `app.config`
    # was written assuming "app/" sits at the repo root, not one level
    # down. Found via a real failing test with exactly this shape, not
    # anticipated in advance. Picks the SHORTEST matching path (fewest
    # extra prefix segments) to reduce ambiguity when multiple candidates
    # could match; a genuine remaining limitation for repos with multiple
    # same-named modules at different depths (documented, not solved).
    candidates: list[str] = []
    for ext in (f"{module_as_path}.py", f"{module_as_path}/__init__.py"):
        suffix = f"/{ext}"
        candidates.extend(f for f in known_files if f.endswith(suffix))
    if candidates:
        return min(candidates, key=lambda p: p.count("/"))

    return None


def _resolve_js_ts_import(module: str, source_file: str, known_files: set[str]) -> str | None:
    if not (module.startswith("./") or module.startswith("../")):
        return None  # bare/absolute specifier ("react", "@scope/pkg") = external, by definition

    source_dir = PurePosixPath(source_file).parent
    # posixpath.normpath (NOT PurePosixPath's own str()) actually collapses
    # ".." segments — PurePosixPath is a lexical path object that leaves
    # "a/b/../c" as-is; only normpath resolves it to "a/c". Verified this
    # distinction directly before relying on it: a naive str(PurePosixPath(...))
    # silently failed to resolve any "../" import.
    target_base = posixpath.normpath(f"{source_dir}/{module}")

    for ext in _JS_TS_EXTENSIONS_TO_TRY:
        candidate = f"{target_base}{ext}"
        if candidate in known_files:
            return candidate
    for index_name in _JS_TS_INDEX_FILES:
        candidate = f"{target_base}/{index_name}"
        if candidate in known_files:
            return candidate
    return None
