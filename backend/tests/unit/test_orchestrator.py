from app.services.parsing.orchestrator import parse_file


def test_python_file_uses_full_ast_not_fallback():
    result = parse_file("app/main.py", b"def hello():\n    return 1\n")
    assert result.error is None
    assert result.used_fallback is False
    assert result.language == "Python"
    assert [s.name for s in result.symbols] == ["hello"]


def test_go_file_uses_fallback_and_is_labeled_as_such():
    result = parse_file("main.go", b"package main\n\nfunc main() {\n}\n")
    assert result.error is None
    assert result.used_fallback is True
    assert result.language == "Go"


def test_invalid_utf8_is_isolated_as_error_not_exception():
    result = parse_file("weird.py", b"\x00\x01\xff\xfe not real python \x00")
    assert result.error is not None
    assert "utf-8" in result.error.lower()
    assert result.symbols == []


def test_unsupported_extension_returns_honest_error():
    result = parse_file("data.bin", b"whatever")
    assert result.error is not None
    assert result.symbols == []


def test_typescript_uses_full_ast():
    result = parse_file("app.tsx", b"export function App() { return null; }\n")
    assert result.used_fallback is False
    assert result.language == "TypeScript"


def test_malformed_source_never_raises():
    """Deliberately garbled/incomplete code should degrade gracefully,
    not crash the whole batch."""
    result = parse_file("broken.py", b"def incomplete(:\n  this is not valid python at all !!!")
    # tree-sitter is error-tolerant and will still return a (partial) tree;
    # the key assertion is that this never raises.
    assert result.file_path == "broken.py"
