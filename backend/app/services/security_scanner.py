from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from app.db.models import SecurityCategory, SecuritySeverity


@dataclass(frozen=True)
class Rule:
    id: str
    category: SecurityCategory
    severity: SecuritySeverity
    title: str
    pattern: re.Pattern[str]
    description: str
    remediation: str
    confidence: str = "high"


# Conservative static-analysis rules. These intentionally report suspicious
# constructs, not proven CVEs. Dependency vulnerability databases are outside
# this offline scanner's scope and are never implied by these findings.
RULES = (
    Rule("SEC001", SecurityCategory.SECRET, SecuritySeverity.CRITICAL,
         "Hardcoded credential", re.compile(r"(?i)(?:api[_-]?key|secret[_-]?key|access[_-]?token|password|passwd)\s*[:=]\s*[\"'][^\"']{8,}[\"']"),
         "A credential-like value appears to be hardcoded in source code.",
         "Move the secret to a secret manager or environment variable and rotate the exposed credential."),
    Rule("SEC002", SecurityCategory.SECRET, SecuritySeverity.CRITICAL,
         "Private key material", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
         "Private key material was found in repository contents.",
         "Remove the key from source control, rotate it, and store it in a secret manager."),
    Rule("SEC003", SecurityCategory.SECRET, SecuritySeverity.HIGH,
         "Cloud credential pattern", re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
         "The file contains a pattern matching an AWS access key identifier.",
         "Rotate the credential immediately and use workload identity or a secret manager."),
    Rule("SEC004", SecurityCategory.CODE_INJECTION, SecuritySeverity.HIGH,
         "Dynamic code execution", re.compile(r"(?m)\b(?:eval|exec)\s*\("),
         "Dynamic code execution can execute attacker-controlled input when data reaches the call.",
         "Avoid dynamic execution; use explicit parsing or a safe dispatch table."),
    Rule("SEC005", SecurityCategory.COMMAND_INJECTION, SecuritySeverity.HIGH,
         "Shell command execution", re.compile(r"(?m)\b(?:os\.system|os\.popen)\s*\(|subprocess\.(?:run|Popen|call|check_output)\([^\n]*\bshell\s*=\s*True"),
         "Shell execution is dangerous when command components can be influenced by untrusted input.",
         "Prefer argument arrays with shell=False and validate/allowlist inputs."),
    Rule("SEC006", SecurityCategory.SQL_INJECTION, SecuritySeverity.HIGH,
         "Potential SQL string interpolation", re.compile(r"(?i)(?:execute|executemany)\s*\(\s*(?:f[\"']|[\"'][^\"']*[+%])"),
         "SQL appears to be constructed with string interpolation or concatenation.",
         "Use parameterized queries or the ORM's bound-parameter APIs."),
    Rule("SEC007", SecurityCategory.INSECURE_DESERIALIZATION, SecuritySeverity.HIGH,
         "Unsafe pickle deserialization", re.compile(r"(?m)\bpickle\.(?:load|loads)\s*\("),
         "Pickle can execute arbitrary code while deserializing untrusted data.",
         "Use a safe data format such as JSON and validate its schema."),
    Rule("SEC008", SecurityCategory.WEAK_CRYPTO, SecuritySeverity.MEDIUM,
         "Weak cryptographic hash", re.compile(r"(?i)\b(?:hashlib\.)?(?:md5|sha1)\s*\("),
         "MD5/SHA-1 are unsuitable for modern security-sensitive hashing.",
         "Use SHA-256 or a password-specific KDF such as Argon2/bcrypt for passwords."),
    Rule("SEC009", SecurityCategory.TLS, SecuritySeverity.MEDIUM,
         "TLS certificate verification disabled", re.compile(r"(?i)\bverify\s*=\s*False\b"),
         "TLS certificate verification is disabled and can enable man-in-the-middle attacks.",
         "Enable certificate verification; configure a trusted CA instead of disabling verification."),
    Rule("SEC010", SecurityCategory.INSECURE_CONFIG, SecuritySeverity.MEDIUM,
         "Debug mode enabled", re.compile(r"(?m)\b(?:debug|DEBUG)\s*=\s*(?:True|true|1)\b"),
         "Debug mode may expose stack traces, configuration, or sensitive runtime information.",
         "Disable debug mode in production and control it through environment-specific configuration."),
    Rule("SEC011", SecurityCategory.CODE_INJECTION, SecuritySeverity.MEDIUM,
         "Potential unsafe YAML loading", re.compile(r"(?m)\byaml\.load\s*\("),
         "Unsafe YAML loading can construct arbitrary Python objects depending on the loader/version.",
         "Use yaml.safe_load for untrusted YAML and validate the resulting structure."),
)


@dataclass(frozen=True)
class SecurityFindingResult:
    rule_id: str
    category: SecurityCategory
    severity: SecuritySeverity
    title: str
    description: str
    file_path: str
    line_number: int
    evidence: str
    remediation: str
    confidence: str


def scan_text(file_path: str, text: str) -> list[SecurityFindingResult]:
    findings: list[SecurityFindingResult] = []
    for rule in RULES:
        for match in rule.pattern.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            line_text = text.splitlines()[line - 1].strip()[:500] if text.splitlines() else ""
            # Never persist the full secret value. Evidence is redacted for
            # credential-like rules to reduce accidental secret leakage.
            evidence = line_text
            if rule.category == SecurityCategory.SECRET:
                evidence = re.sub(r"([:=]\s*[\"'])([^\"']+)([\"'])", r"\1***REDACTED***\3", evidence)
            findings.append(SecurityFindingResult(
                rule.id, rule.category, rule.severity, rule.title, rule.description,
                file_path, line, evidence, rule.remediation, rule.confidence,
            ))
    return findings


def scan_repository_files(root: Path, file_paths: list[str]) -> tuple[list[SecurityFindingResult], int]:
    findings: list[SecurityFindingResult] = []
    scanned = 0
    for rel in file_paths:
        path = root / rel
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        scanned += 1
        findings.extend(scan_text(rel, text))
    return findings, scanned
