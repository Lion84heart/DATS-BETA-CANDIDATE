"""Secret pattern detection and scanning.

Identifies hardcoded credentials, API keys, and tokens in source code
and configuration to prevent accidental exposure.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


@dataclass(frozen=True)
class SecretFinding:
    """A detected potential secret."""

    rule_name: str
    file_path: str
    line_number: int
    snippet: str
    severity: str  # CRITICAL, HIGH, MEDIUM, LOW


class SecretScanner:
    """Scan files and text for potential secret leaks.

    Uses regex patterns to detect common secret formats without
    exposing actual secret values in output.
    """

    # Patterns that indicate secrets (case-insensitive where appropriate)
    PATTERNS: list[tuple[str, str, str]] = [
        # (rule_name, regex_pattern, severity)
        ("aws_access_key", r"AKIA[0-9A-Z]{16}", "CRITICAL"),
        ("aws_secret_key", r"['\"\s][0-9a-zA-Z/+]{40}['\"\s]", "CRITICAL"),
        ("github_token", r"gh[pousr]_[A-Za-z0-9_]{36}", "CRITICAL"),
        ("api_key_generic", r"(?i)(api[_-]?key|apikey)\s*[:=]\s*['\"][a-z0-9]{16,}['\"]", "HIGH"),
        ("private_key", r"-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----", "CRITICAL"),
        ("jwt_token", r"eyJ[A-Za-z0-9_-]*\.eyJ[A-Za-z0-9_-]*\.[A-Za-z0-9_-]*", "HIGH"),
        ("bearer_token", r"(?i)bearer\s+[a-z0-9_\-\.]{20,}", "HIGH"),
        ("password_assignment", r"(?i)(password|passwd|pwd)\s*[:=]\s*['\"][^'\"]{8,}['\"]", "MEDIUM"),
        ("secret_assignment", r"(?i)(secret|token)\s*[:=]\s*['\"][a-z0-9]{16,}['\"]", "HIGH"),
        ("database_url", r"(?i)(mongodb|postgres|mysql)://[^:]+:[^@]+@", "HIGH"),
        ("slack_token", r"xox[baprs]-[0-9]{10,13}-[0-9]{10,13}[a-zA-Z0-9-]*", "CRITICAL"),
        ("hex_secret", r"(?i)['\"][0-9a-f]{32,64}['\"]\s*\)?\s*#\s*secret", "MEDIUM"),
    ]

    # Lines to skip (comments that are examples/fake)
    SKIP_PATTERNS = [
        re.compile(r"(?i)#\s*example"),
        re.compile(r"(?i)#\s*fake"),
        re.compile(r"(?i)#\s*test"),
        re.compile(r"(?i)#\s*mock"),
        re.compile(r"(?i)#\s*placeholder"),
        re.compile(r"(?i)\b(EXAMPLE|DEMO|FAKE|TEST|MOCK|PLACEHOLDER)\b"),
    ]

    def __init__(self):
        self._compiled: list[tuple[str, re.Pattern, str]] = [
            (name, re.compile(pattern), sev) for name, pattern, sev in self.PATTERNS
        ]

    def scan_text(self, text: str, file_path: str = "<text>") -> list[SecretFinding]:
        """Scan a text body for secrets.

        Args:
            text: Text to scan.
            file_path: Source identifier for findings.

        Returns:
            List of secret findings (may be empty).
        """
        findings: list[SecretFinding] = []
        lines = text.split("\n")

        for line_num, line in enumerate(lines, start=1):
            if self._should_skip_line(line):
                continue

            for rule_name, pattern, severity in self._compiled:
                match = pattern.search(line)
                if match:
                    # Truncate snippet to avoid exposing secret
                    snippet = match.group(0)
                    if len(snippet) > 40:
                        snippet = snippet[:20] + "..." + snippet[-10:]
                    findings.append(
                        SecretFinding(
                            rule_name=rule_name,
                            file_path=file_path,
                            line_number=line_num,
                            snippet=snippet,
                            severity=severity,
                        )
                    )

        return findings

    def scan_file(self, file_path: str | Path) -> list[SecretFinding]:
        """Scan a single file for secrets.

        Args:
            file_path: Path to file.

        Returns:
            List of secret findings.
        """
        path = Path(file_path)
        if not path.exists() or path.stat().st_size > 1_000_000:
            return []  # Skip large files

        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except (OSError, UnicodeDecodeError):
            return []

        return self.scan_text(text, str(path))

    def scan_directory(
        self,
        directory: str | Path,
        extensions: set[str] | None = None,
        exclude_dirs: set[str] | None = None,
    ) -> Iterator[SecretFinding]:
        """Recursively scan a directory for secrets.

        Args:
            directory: Root directory to scan.
            extensions: File extensions to scan (e.g., {".py", ".yml"}).
            exclude_dirs: Directory names to skip.

        Yields:
            SecretFinding for each detected secret.
        """
        directory = Path(directory)
        extensions = extensions or {".py", ".yaml", ".yml", ".json", ".toml", ".cfg", ".ini", ".sh"}
        exclude_dirs = exclude_dirs or {"__pycache__", ".git", ".pytest_cache", "node_modules", ".venv"}

        for path in directory.rglob("*"):
            if not path.is_file():
                continue
            if any(part in exclude_dirs for part in path.parts):
                continue
            if path.suffix.lower() not in extensions:
                continue

            findings = self.scan_file(path)
            for finding in findings:
                yield finding

    def _should_skip_line(self, line: str) -> bool:
        """Check if a line should be skipped (example/fake)."""
        return any(pattern.search(line) for pattern in self.SKIP_PATTERNS)

    @property
    def rule_count(self) -> int:
        """Number of scanning rules."""
        return len(self.PATTERNS)

    @staticmethod
    def mask_secret(value: str, visible_prefix: int = 4, visible_suffix: int = 4) -> str:
        """Mask a secret value, showing only prefix and suffix.

        Args:
            value: Secret to mask.
            visible_prefix: Characters to show at start.
            visible_suffix: Characters to show at end.

        Returns:
            Masked string.
        """
        if len(value) <= visible_prefix + visible_suffix:
            return "*" * len(value)
        return value[:visible_prefix] + "*" * (len(value) - visible_prefix - visible_suffix) + value[-visible_suffix:]
