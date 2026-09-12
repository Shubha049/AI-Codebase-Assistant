from tree_sitter_language_pack import get_parser

from app.services.parsing.python_extractor import extract_python

_parser = get_parser("python")


def _parse(code: str):
    tree = _parser.parse(code.encode("utf-8"))
    return extract_python(tree.root_node)


def test_extracts_class_and_method_with_docstrings():
    symbols, _ = _parse(
        'class Foo:\n'
        '    """A test class."""\n'
        '    def bar(self, x):\n'
        '        """Does a thing."""\n'
        '        return x + 1\n'
    )
    by_name = {s.name: s for s in symbols}
    assert by_name["Foo"].symbol_type == "class"
    assert by_name["Foo"].docstring == "A test class."
    assert by_name["bar"].symbol_type == "method"
    assert by_name["bar"].parent_name == "Foo"
    assert by_name["bar"].docstring == "Does a thing."


def test_top_level_function_has_no_parent():
    symbols, _ = _parse("def top_level(a, b):\n    return a + b\n")
    assert len(symbols) == 1
    assert symbols[0].symbol_type == "function"
    assert symbols[0].parent_name is None


def test_class_without_docstring_is_none_not_crash():
    symbols, _ = _parse("class Plain:\n    def method_no_doc(self):\n        pass\n")
    by_name = {s.name: s for s in symbols}
    assert by_name["Plain"].docstring is None
    assert by_name["method_no_doc"].docstring is None


def test_does_not_double_count_class_keyword_as_symbol():
    """Regression test: earlier version matched the literal `class`
    keyword token as a second, nameless class due to a tree-sitter
    node-type collision."""
    symbols, _ = _parse("class Foo:\n    pass\n")
    assert len(symbols) == 1
    assert symbols[0].name == "Foo"


def test_extracts_plain_and_from_imports():
    _, imports = _parse(
        "import os\n"
        "from typing import List, Optional\n"
    )
    by_module = {i.module: i for i in imports}
    assert "os" in by_module
    assert by_module["typing"].imported_names == ["List", "Optional"]


def test_wildcard_import():
    _, imports = _parse("from os.path import *\n")
    assert imports[0].module == "os.path"
    assert imports[0].imported_names == ["*"]


def test_multiple_classes_in_one_file_all_detected():
    symbols, _ = _parse(
        "class A:\n    def m1(self): pass\n\n"
        "class B:\n    def m2(self): pass\n"
    )
    class_names = [s.name for s in symbols if s.symbol_type == "class"]
    assert class_names == ["A", "B"]
