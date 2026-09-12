from pathlib import Path

from app.services.ingestion.scanner import scan_repository


def _write(path: Path, content: str = "print('hi')\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def test_scan_detects_languages_and_skips_ignored_dirs(tmp_path):
    _write(tmp_path / "app" / "main.py")
    _write(tmp_path / "app" / "utils.py")
    _write(tmp_path / "frontend" / "src" / "App.tsx", "export const App = () => null;\n")
    _write(tmp_path / "README.md", "# hi\n")
    # should be skipped entirely
    _write(tmp_path / "node_modules" / "pkg" / "index.js", "module.exports = {}\n")
    _write(tmp_path / ".git" / "config", "[core]\n")

    result = scan_repository(tmp_path)

    assert result.file_count == 4  # main.py, utils.py, App.tsx, README.md
    assert result.language_breakdown["Python"] == 2
    assert result.language_breakdown["TypeScript"] == 1
    assert result.language_breakdown["Markdown"] == 1
    assert "node_modules" not in "".join(result.analyzable_file_paths)


def test_scan_skips_binary_file_despite_analyzable_extension(tmp_path):
    binary_path = tmp_path / "weird.py"
    binary_path.parent.mkdir(parents=True, exist_ok=True)
    binary_path.write_bytes(b"\x00\x01\x02\xff\xfe not really python")

    result = scan_repository(tmp_path)

    assert result.file_count == 0
    assert result.skipped_file_count == 1


def test_scan_empty_directory(tmp_path):
    result = scan_repository(tmp_path)
    assert result.file_count == 0
    assert result.language_breakdown == {}
