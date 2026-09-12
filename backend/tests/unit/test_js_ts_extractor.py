from tree_sitter_language_pack import get_parser

from app.services.parsing.js_ts_extractor import extract_js_ts

_parser = get_parser("typescript")


def _parse(code: str):
    tree = _parser.parse(code.encode("utf-8"))
    return extract_js_ts(tree.root_node)


def test_extracts_class_and_method():
    symbols, _ = _parse(
        "export class Widget {\n"
        "    render() {\n"
        "        return null;\n"
        "    }\n"
        "}\n"
    )
    by_name = {s.name: s for s in symbols}
    assert "Widget" in by_name and by_name["Widget"].symbol_type == "class"
    assert by_name["render"].parent_name == "Widget"


def test_does_not_double_count_class_keyword_as_symbol():
    """Regression test: earlier version matched the literal `class`
    keyword TOKEN (a child of class_declaration) as a second phantom
    class named '<anonymous>'."""
    symbols, _ = _parse("export class Widget {\n    render() { return null; }\n}\n")
    class_symbols = [s for s in symbols if s.symbol_type == "class"]
    assert len(class_symbols) == 1
    assert class_symbols[0].name == "Widget"


def test_does_not_double_count_function_keyword_as_symbol():
    symbols, _ = _parse("function helper(x) {\n    return x;\n}\n")
    assert len(symbols) == 1
    assert symbols[0].name == "helper"
    assert symbols[0].symbol_type == "function"


def test_extracts_arrow_function_assigned_to_const():
    symbols, _ = _parse("const handler = (e) => {\n    console.log(e);\n};\n")
    assert len(symbols) == 1
    assert symbols[0].symbol_type == "arrow_function"
    assert symbols[0].name == "handler"


def test_extracts_default_named_and_namespace_imports():
    _, imports = _parse(
        'import React from "react";\n'
        'import { useState, useEffect as useEff } from "react";\n'
        'import * as utils from "./utils";\n'
    )
    assert imports[0].module == "react"
    assert imports[0].imported_names == ["React"]
    assert imports[1].imported_names == ["useState", "useEffect"]
    assert imports[2].module == "./utils"
    assert imports[2].imported_names == ["* as utils"]


def test_multiple_classes_each_with_own_methods():
    symbols, _ = _parse(
        "class First {\n    a() {}\n}\n"
        "class Second {\n    b() {}\n    c() {}\n}\n"
    )
    methods = [s for s in symbols if s.symbol_type == "method"]
    assert {(m.name, m.parent_name) for m in methods} == {
        ("a", "First"), ("b", "Second"), ("c", "Second")
    }
