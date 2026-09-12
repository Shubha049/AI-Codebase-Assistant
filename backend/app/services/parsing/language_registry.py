"""
Central registry of extension -> tree-sitter grammar name, and which
languages have a real, hand-written AST extractor (full support) versus
falling back to the honest, clearly-labeled regex-based extractor.

Being explicit about this split matters: silently giving every language
"AST extraction" language in a status field when only two are truly
AST-based would misrepresent what the pipeline actually did.
"""
from __future__ import annotations

# extension -> tree-sitter-language-pack grammar identifier
EXTENSION_TO_TS_LANGUAGE: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
}

# Languages with a real hand-written tree-sitter extractor in this codebase.
FULL_AST_LANGUAGES: set[str] = {"python", "javascript", "typescript", "tsx"}

EXTENSION_TO_LANGUAGE_LABEL: dict[str, str] = {
    ".py": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".java": "Java",
    ".go": "Go",
    ".rb": "Ruby",
    ".php": "PHP",
    ".c": "C",
    ".h": "C",
    ".cpp": "C++",
    ".hpp": "C++",
    ".cs": "C#",
    ".rs": "Rust",
    ".swift": "Swift",
    ".kt": "Kotlin",
    ".scala": "Scala",
}


def has_full_ast_support(extension: str) -> bool:
    ts_lang = EXTENSION_TO_TS_LANGUAGE.get(extension)
    return ts_lang is not None and ts_lang in FULL_AST_LANGUAGES
