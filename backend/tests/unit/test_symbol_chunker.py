from app.services.chunking.symbol_chunker import generate_chunks_for_file
from app.services.parsing.orchestrator import parse_file

_PYTHON_SRC = '''import os
from typing import List

class Foo:
    """A test class."""
    def bar(self, x):
        """Does a thing."""
        return x + 1

    def baz(self):
        return None

def top_level(a, b):
    return a + b
'''


def _chunk_python(src: str, max_tokens: int = 500, overlap_ratio: float = 0.15):
    result = parse_file("app/main.py", src.encode())
    return generate_chunks_for_file(src, result.symbols, result.used_fallback, max_tokens, overlap_ratio)


def test_class_with_methods_splits_into_header_plus_one_chunk_per_method():
    """Regression test: earlier version kept a class-with-methods as ONE
    chunk whenever the whole class fit under the token budget, silently
    contradicting the module's own documented design. Only over-budget
    classes got split. Found by inspecting real chunker output on a small
    test class, not caught by inspection alone."""
    chunks = _chunk_python(_PYTHON_SRC)
    by_symbol = {c.symbol_name: c for c in chunks if c.symbol_name in ("Foo", "bar", "baz")}
    assert by_symbol["Foo"].chunk_type == "class_header"
    assert by_symbol["bar"].chunk_type == "method"
    assert by_symbol["bar"].parent_symbol_name == "Foo"
    assert by_symbol["baz"].chunk_type == "method"
    assert by_symbol["baz"].parent_symbol_name == "Foo"


def test_top_level_function_gets_its_own_chunk():
    chunks = _chunk_python(_PYTHON_SRC)
    fn_chunks = [c for c in chunks if c.symbol_name == "top_level"]
    assert len(fn_chunks) == 1
    assert fn_chunks[0].chunk_type == "function"
    assert fn_chunks[0].parent_symbol_name is None


def test_imports_become_module_level_chunk():
    chunks = _chunk_python(_PYTHON_SRC)
    module_chunks = [c for c in chunks if c.chunk_type == "module_level"]
    assert len(module_chunks) == 1
    assert "import os" in module_chunks[0].content


def test_class_without_methods_stays_single_chunk():
    src = "class Config:\n    DEBUG = True\n    PORT = 8000\n"
    chunks = _chunk_python(src)
    class_chunks = [c for c in chunks if c.symbol_name == "Config"]
    assert len(class_chunks) == 1
    assert class_chunks[0].chunk_type == "class"


def test_oversized_method_gets_windowed_not_left_as_one_giant_chunk():
    long_body = "\n".join(f"        x{i} = {i}" for i in range(200))  # 8-space indent: nested inside the method
    src = f"class Big:\n    def huge_method(self):\n{long_body}\n"
    chunks = _chunk_python(src, max_tokens=50)
    method_windows = [c for c in chunks if c.chunk_type == "method_window"]
    assert len(method_windows) > 1
    assert all(c.parent_symbol_name == "Big" for c in method_windows)


def test_fallback_parsed_file_uses_file_window_regardless_of_symbols():
    # Go uses the regex fallback (Phase 2) — used_fallback=True
    src = 'package main\n\nfunc main() {\n    println("hi")\n}\n'
    result = parse_file("main.go", src.encode())
    assert result.used_fallback is True
    chunks = generate_chunks_for_file(src, result.symbols, result.used_fallback, 400, 0.15)
    assert all(c.chunk_type == "file_window" for c in chunks)


def test_empty_file_produces_no_chunks():
    chunks = generate_chunks_for_file("", [], False, 400, 0.15)
    assert chunks == []


def test_full_file_content_is_covered_no_silent_gaps():
    """Every non-blank line of the source should appear in some chunk's
    content — nothing silently dropped between/around symbols."""
    chunks = _chunk_python(_PYTHON_SRC)
    covered_text = "\n".join(c.content for c in chunks)
    for line in _PYTHON_SRC.split("\n"):
        if line.strip():
            assert line in covered_text, f"line not covered: {line!r}"


def test_chunks_are_returned_in_line_order():
    chunks = _chunk_python(_PYTHON_SRC)
    starts = [c.start_line for c in chunks]
    assert starts == sorted(starts)


def test_chunk_js_ts_file_with_arrow_function_and_class():
    src = '''import React from 'react';

export const handleEvent = (event: any) => {
    console.log("handled", event);
    return true;
};

export class UserProfile {
    render() {
        return "profile";
    }

    onSave = (data: any) => {
        return data;
    };
}
'''
    result = parse_file("src/UserProfile.tsx", src.encode("utf-8"))
    chunks = generate_chunks_for_file(src, result.symbols, result.used_fallback, max_tokens=500, overlap_ratio=0.15)
    
    types = {c.symbol_name: c.chunk_type for c in chunks if c.symbol_name}
    assert types.get("handleEvent") == "function"
    assert types.get("UserProfile") == "class_header"
    assert types.get("render") == "method"
    # Ensure all chunks have valid ChunkType values
    from app.db.models import ChunkType
    for c in chunks:
        assert ChunkType(c.chunk_type) in ChunkType


def test_map_symbol_to_chunk_type_audited_kinds():
    from app.services.chunking.symbol_chunker import map_symbol_to_chunk_type
    # Top-level callables
    assert map_symbol_to_chunk_type("arrow_function") == "function"
    assert map_symbol_to_chunk_type("function_declaration") == "function"
    assert map_symbol_to_chunk_type("generator_function") == "function"
    assert map_symbol_to_chunk_type("function_expression") == "function"

    # Member callables (parent_name provided)
    assert map_symbol_to_chunk_type("arrow_function", parent_name="MyClass") == "method"
    assert map_symbol_to_chunk_type("function_declaration", parent_name="MyClass") == "method"
    assert map_symbol_to_chunk_type("method_definition") == "method"
    assert map_symbol_to_chunk_type("constructor") == "method"
    assert map_symbol_to_chunk_type("getter") == "method"

    # Classes and types
    assert map_symbol_to_chunk_type("class_declaration") == "class"
    assert map_symbol_to_chunk_type("abstract_class_declaration") == "class"
    assert map_symbol_to_chunk_type("interface") == "class"
    assert map_symbol_to_chunk_type("struct_declaration") == "class"
    assert map_symbol_to_chunk_type("enum_declaration") == "class"

    # Unmapped fallback
    assert map_symbol_to_chunk_type("unknown_future_ast_kind") == "code_block"


def test_chunk_type_enum_safe_instantiation():
    from app.db.models import ChunkType
    # Known AST aliases resolve to proper enum members
    assert ChunkType("arrow_function") == ChunkType.FUNCTION
    assert ChunkType("generator_function") == ChunkType.FUNCTION
    assert ChunkType("method_definition") == ChunkType.METHOD
    assert ChunkType("class_declaration") == ChunkType.CLASS
    # Unknown string gracefully falls back to CODE_BLOCK
    assert ChunkType("completely_unrecognized_node") == ChunkType.CODE_BLOCK

