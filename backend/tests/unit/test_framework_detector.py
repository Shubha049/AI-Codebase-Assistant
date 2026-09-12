import json

from app.services.framework_detection.detector import detect_frameworks_and_build_systems


def _write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def test_detects_pip_and_fastapi_from_requirements_txt(tmp_path):
    _write(tmp_path / "requirements.txt", "fastapi==0.115.0\nuvicorn==0.30.6\n")
    result = detect_frameworks_and_build_systems(tmp_path)
    assert "pip" in result.build_systems
    names = {f.name for f in result.frameworks}
    assert "FastAPI" in names


def test_ignores_comments_and_blank_lines_in_requirements_txt(tmp_path):
    _write(tmp_path / "requirements.txt", "# a comment\n\nflask==3.0.0\n")
    result = detect_frameworks_and_build_systems(tmp_path)
    names = {f.name for f in result.frameworks}
    assert "Flask" in names


def test_detects_npm_and_react_from_package_json(tmp_path):
    _write(
        tmp_path / "package.json",
        json.dumps({"dependencies": {"react": "^18.3.1"}, "devDependencies": {"vite": "^5.0.0"}}),
    )
    result = detect_frameworks_and_build_systems(tmp_path)
    assert "npm" in result.build_systems
    names = {f.name for f in result.frameworks}
    assert {"React", "Vite"} <= names


def test_detects_nested_package_json_one_level_deep(tmp_path):
    _write(
        tmp_path / "frontend" / "package.json",
        json.dumps({"dependencies": {"vue": "^3.0.0"}}),
    )
    result = detect_frameworks_and_build_systems(tmp_path)
    names = {f.name for f in result.frameworks}
    assert "Vue" in names


def test_malformed_package_json_does_not_crash(tmp_path):
    _write(tmp_path / "package.json", "{ this is not valid json")
    result = detect_frameworks_and_build_systems(tmp_path)
    assert result.frameworks == []


def test_unrelated_dependency_name_does_not_false_positive(tmp_path):
    """A package with an unrelated name shouldn't be mistaken for a
    known framework via substring matching."""
    _write(tmp_path / "requirements.txt", "django-extensions-totally-unofficial==1.0\n")
    result = detect_frameworks_and_build_systems(tmp_path)
    names = {f.name for f in result.frameworks}
    assert "Django" not in names


def test_no_manifests_present_returns_empty_not_error(tmp_path):
    result = detect_frameworks_and_build_systems(tmp_path)
    assert result.build_systems == []
    assert result.frameworks == []


def test_evidence_is_traceable_to_specific_file(tmp_path):
    _write(tmp_path / "requirements.txt", "fastapi==0.115.0\n")
    result = detect_frameworks_and_build_systems(tmp_path)
    assert result.frameworks[0].evidence_file == "requirements.txt"
    assert "fastapi" in result.frameworks[0].evidence


def test_finds_manifest_nested_under_wrapping_directory(tmp_path):
    """Regression test: a GitHub-zip-style wrapping folder plus a
    monorepo subfolder puts package.json 2 levels deep — the original
    depth-0/depth-1-only search missed this, found via a real failing
    integration test, not anticipated in advance."""
    _write(
        tmp_path / "myrepo" / "frontend" / "package.json",
        json.dumps({"dependencies": {"react": "^18.3.1"}}),
    )
    result = detect_frameworks_and_build_systems(tmp_path)
    names = {f.name for f in result.frameworks}
    assert "React" in names


def test_does_not_descend_into_vendor_directories(tmp_path):
    """A package.json belonging to a vendored dependency inside
    node_modules must never be mistaken for the project's own manifest."""
    _write(
        tmp_path / "node_modules" / "some-lib" / "package.json",
        json.dumps({"dependencies": {"vue": "^3.0.0"}}),
    )
    result = detect_frameworks_and_build_systems(tmp_path)
    assert result.frameworks == []
