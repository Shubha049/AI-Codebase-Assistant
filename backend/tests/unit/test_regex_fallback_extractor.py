from app.services.parsing.regex_fallback_extractor import extract_basic


def test_go_receiver_methods_attach_to_struct_type():
    code = (
        "package main\n\n"
        'import "fmt"\n\n'
        "type Server struct {\n    Port int\n}\n\n"
        "func (s *Server) Start() {\n    fmt.Println(\"starting\")\n}\n\n"
        "func main() {\n}\n"
    )
    symbols, imports = extract_basic("go", code)
    by_name = {s.name: s for s in symbols}
    assert by_name["Server"].symbol_type == "class"
    assert by_name["Start"].symbol_type == "method"
    assert by_name["Start"].parent_name == "Server"
    assert by_name["main"].symbol_type == "function"
    assert by_name["main"].parent_name is None
    assert imports[0].module == "fmt"


def test_go_string_literal_in_function_body_not_mistaken_for_import():
    code = 'func main() {\n    x := "not an import"\n}\n'
    _, imports = extract_basic("go", code)
    assert imports == []


def test_java_class_and_methods():
    code = (
        "package com.example;\n\n"
        "import java.util.List;\n\n"
        "public class UserService {\n"
        "    public User findById(int id) {\n"
        "        return null;\n"
        "    }\n"
        "}\n"
    )
    symbols, imports = extract_basic("java", code)
    by_name = {s.name: s for s in symbols}
    assert by_name["UserService"].symbol_type == "class"
    assert by_name["findById"].symbol_type == "method"
    assert by_name["findById"].parent_name == "UserService"
    assert imports[0].module == "java.util.List"


def test_rust_pub_fn_and_struct():
    code = "pub struct Point {\n    x: i32,\n}\n\npub fn distance() -> f64 {\n    0.0\n}\n"
    symbols, _ = extract_basic("rust", code)
    names = {s.name for s in symbols}
    assert "Point" in names
    assert "distance" in names


def test_ruby_def_and_require():
    code = 'require "json"\n\nclass Widget\n  def render\n    nil\n  end\nend\n'
    symbols, imports = extract_basic("ruby", code)
    by_name = {s.name: s for s in symbols}
    assert by_name["Widget"].symbol_type == "class"
    assert by_name["render"].parent_name == "Widget"
    assert imports[0].module == "json"


def test_unknown_language_returns_empty_not_crash():
    symbols, imports = extract_basic("cobol", "IDENTIFICATION DIVISION.\n")
    assert symbols == []
    assert imports == []


def test_leading_blank_lines_do_not_shift_reported_line_numbers():
    """
    Regression test: `^\\s*` (instead of `^[ \\t]*`) let `^` anchor at a
    blank line and \\s* swallow that blank line's own newline, silently
    reporting every symbol's line number one or more lines too early
    whenever blank lines preceded it. Caught by manually inspecting
    match.start() against the source, not assumed correct.
    """
    code = "\n\n\nclass Widget {\n    void render() {}\n}\n"
    symbols, _ = extract_basic("java", code)
    by_name = {s.name: s for s in symbols}
    assert by_name["Widget"].start_line == 4  # not 1, 2, or 3
    assert by_name["render"].start_line == 5
