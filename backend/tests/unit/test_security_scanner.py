from app.services.security_scanner import scan_text


def test_detects_and_redacts_hardcoded_secret():
    findings = scan_text("app.py", 'API_KEY = "super-secret-value-123"\n')
    assert any(f.rule_id == "SEC001" for f in findings)
    assert all("super-secret-value-123" not in f.evidence for f in findings)


def test_detects_command_execution():
    findings = scan_text("run.py", "import os\nos.system(user_input)\n")
    assert any(f.rule_id == "SEC005" for f in findings)


def test_detects_unsafe_deserialization_and_weak_crypto():
    findings = scan_text("x.py", "pickle.loads(data)\nhashlib.md5(value)\n")
    ids = {f.rule_id for f in findings}
    assert {"SEC007", "SEC008"}.issubset(ids)


def test_clean_code_has_no_findings():
    assert scan_text("safe.py", "import hashlib\nhashlib.sha256(value)\n") == []
