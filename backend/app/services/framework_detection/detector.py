"""
Detects build systems and frameworks by reading actual manifest files in
the repository root (and one level down, for monorepo-ish layouts) and
matching real dependency names against a curated list — no inference from
file extensions or guessing. A manifest that doesn't exist means that
build system isn't detected; a dependency that isn't listed means that
framework isn't detected. Every result is traceable back to the specific
file and line/entry that triggered it.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

MANIFEST_TO_BUILD_SYSTEM = {
    "requirements.txt": "pip",
    "pyproject.toml": "pip",  # could be poetry, but pip-installable either way
    "Pipfile": "pipenv",
    "package.json": "npm",
    "yarn.lock": "yarn",
    "pnpm-lock.yaml": "pnpm",
    "pom.xml": "maven",
    "build.gradle": "gradle",
    "build.gradle.kts": "gradle",
    "go.mod": "go modules",
    "Cargo.toml": "cargo",
    "Gemfile": "bundler",
    "composer.json": "composer",
}

# framework display name -> substrings to look for in dependency names
# (checked as a whole-token match against parsed dependency names, not a
# raw substring-in-file search, to avoid false positives like a package
# named "django-extensions-lite" matching unrelated tools).
_PYTHON_FRAMEWORK_SIGNATURES: dict[str, str] = {
    "fastapi": "FastAPI", "flask": "Flask", "django": "Django",
    "pytest": "pytest", "celery": "Celery", "sqlalchemy": "SQLAlchemy",
}
_NODE_FRAMEWORK_SIGNATURES: dict[str, str] = {
    "react": "React", "vue": "Vue", "next": "Next.js", "nuxt": "Nuxt",
    "express": "Express", "@nestjs/core": "NestJS", "svelte": "Svelte",
    "@angular/core": "Angular", "vite": "Vite",
}


@dataclass
class FrameworkFinding:
    name: str
    evidence_file: str
    evidence: str  # e.g. "found 'fastapi' in requirements.txt"


@dataclass
class DetectionResult:
    build_systems: list[str]
    frameworks: list[FrameworkFinding]


def detect_frameworks_and_build_systems(root_dir: Path) -> DetectionResult:
    build_systems: set[str] = set()
    frameworks: list[FrameworkFinding] = []
    seen_frameworks: set[str] = set()

    manifest_paths = _find_manifests(root_dir)

    for manifest_path in manifest_paths:
        rel_name = manifest_path.name
        build_system = MANIFEST_TO_BUILD_SYSTEM.get(rel_name)
        if build_system:
            build_systems.add(build_system)

        rel_path = str(manifest_path.relative_to(root_dir))

        if rel_name == "requirements.txt":
            frameworks.extend(_scan_requirements_txt(manifest_path, rel_path, seen_frameworks))
        elif rel_name == "pyproject.toml":
            frameworks.extend(_scan_pyproject_toml(manifest_path, rel_path, seen_frameworks))
        elif rel_name == "package.json":
            frameworks.extend(_scan_package_json(manifest_path, rel_path, seen_frameworks))
        elif rel_name == "go.mod":
            frameworks.extend(_scan_go_mod(manifest_path, rel_path, seen_frameworks))

    return DetectionResult(
        build_systems=sorted(build_systems),
        frameworks=frameworks,
    )


_SKIP_DIR_NAMES = {
    "node_modules", ".git", "__pycache__", ".venv", "venv",
    "dist", "build", ".next", ".pytest_cache", ".mypy_cache",
    "coverage", ".idea", ".vscode",
}


def _find_manifests(root_dir: Path, max_depth: int = 4) -> list[Path]:
    """
    Bounded-depth walk (not a flat glob) so manifests nested under a
    wrapping directory — e.g. a GitHub zip download's "reponame-main/"
    folder, or a monorepo's "frontend/package.json" — are still found.
    Depth 2 was insufficient in practice (found via a real failing test:
    "myrepo/frontend/package.json" is 2 levels deep, past what a
    depth-0/depth-1-only glob covers). Explicitly skips vendor/build
    directories so a nested node_modules/**/package.json is never
    mistaken for the project's own manifest.
    """
    found: list[Path] = []
    manifest_names = set(MANIFEST_TO_BUILD_SYSTEM)

    def walk(current_dir: Path, depth: int) -> None:
        if depth > max_depth:
            return
        try:
            entries = list(current_dir.iterdir())
        except OSError:
            return
        for entry in entries:
            if entry.is_file() and entry.name in manifest_names:
                found.append(entry)
            elif entry.is_dir() and entry.name not in _SKIP_DIR_NAMES:
                walk(entry, depth + 1)

    walk(root_dir, 0)
    return found


def _scan_requirements_txt(path: Path, rel_path: str, seen: set[str]) -> list[FrameworkFinding]:
    findings = []
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return findings
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Dependency name = everything before the first version specifier.
        name = re.split(r"[=<>!\[;\s]", line, maxsplit=1)[0].strip().lower()
        display = _PYTHON_FRAMEWORK_SIGNATURES.get(name)
        if display and display not in seen:
            seen.add(display)
            findings.append(FrameworkFinding(
                name=display, evidence_file=rel_path,
                evidence=f"'{name}' listed in requirements.txt",
            ))
    return findings


def _scan_pyproject_toml(path: Path, rel_path: str, seen: set[str]) -> list[FrameworkFinding]:
    findings = []
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return findings
    # Deliberately not using a TOML parser dependency for this — a simple
    # line scan for `name = "version"` / `"name"` entries under any
    # dependency-like table is sufficient for detection purposes and adds
    # no new dependency to the project.
    for match in re.finditer(r'^\s*"?([a-zA-Z][\w.-]*)"?\s*=', text, re.MULTILINE):
        name = match.group(1).lower()
        display = _PYTHON_FRAMEWORK_SIGNATURES.get(name)
        if display and display not in seen:
            seen.add(display)
            findings.append(FrameworkFinding(
                name=display, evidence_file=rel_path,
                evidence=f"'{name}' listed in pyproject.toml",
            ))
    return findings


def _scan_package_json(path: Path, rel_path: str, seen: set[str]) -> list[FrameworkFinding]:
    findings = []
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except (OSError, json.JSONDecodeError):
        return findings
    all_deps: dict[str, str] = {}
    all_deps.update(data.get("dependencies", {}) or {})
    all_deps.update(data.get("devDependencies", {}) or {})
    for dep_name in all_deps:
        display = _NODE_FRAMEWORK_SIGNATURES.get(dep_name.lower())
        if display and display not in seen:
            seen.add(display)
            findings.append(FrameworkFinding(
                name=display, evidence_file=rel_path,
                evidence=f"'{dep_name}' listed in package.json",
            ))
    return findings


def _scan_go_mod(path: Path, rel_path: str, seen: set[str]) -> list[FrameworkFinding]:
    findings = []
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return findings
    go_signatures = {
        "github.com/gin-gonic/gin": "Gin",
        "github.com/labstack/echo": "Echo",
        "github.com/gofiber/fiber": "Fiber",
    }
    for module_path, display in go_signatures.items():
        if module_path in text and display not in seen:
            seen.add(display)
            findings.append(FrameworkFinding(
                name=display, evidence_file=rel_path,
                evidence=f"'{module_path}' listed in go.mod",
            ))
    return findings
