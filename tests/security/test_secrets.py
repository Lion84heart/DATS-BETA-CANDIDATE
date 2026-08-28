"""Tests for secret scanning."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

import unittest

from security.secrets import SecretScanner


class TestSecretScanner(unittest.TestCase):
    """Tests for secret detection."""

    def test_aws_key_detected(self):
        """AWS access key detected."""
        scanner = SecretScanner()
        text = "api_key = 'AKIAIOSFODNN7EXAMPLE'"
        findings = scanner.scan_text(text)
        self.assertTrue(any(f.rule_name == "aws_access_key" for f in findings))

    def test_private_key_detected(self):
        """Private key detected."""
        scanner = SecretScanner()
        text = "-----BEGIN RSA PRIVATE KEY-----\nMII..."
        findings = scanner.scan_text(text)
        self.assertTrue(any(f.rule_name == "private_key" for f in findings))

    def test_jwt_detected(self):
        """JWT token detected."""
        scanner = SecretScanner()
        text = "token = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0In0.abc123'"
        findings = scanner.scan_text(text)
        self.assertTrue(any(f.rule_name == "jwt_token" for f in findings))

    def test_no_false_positive_on_safe_text(self):
        """Safe text produces no findings."""
        scanner = SecretScanner()
        text = "This is a normal sentence about trading."
        findings = scanner.scan_text(text)
        self.assertEqual(len(findings), 0)

    def test_skip_example_comments(self):
        """Example secrets skipped."""
        scanner = SecretScanner()
        text = "password = 'fakepassword123'  # example"
        findings = scanner.scan_text(text)
        self.assertEqual(len(findings), 0)

    def test_scan_file(self):
        """Scan file on disk."""
        scanner = SecretScanner()
        test_file = Path("/tmp/test_secret_scan.py")
        test_file.write_text("api_key = 'AKIAIOSFODNN7EXAMPLE'\n")
        findings = scanner.scan_file(test_file)
        self.assertGreater(len(findings), 0)
        test_file.unlink()

    def test_scan_directory(self):
        """Scan directory recursively."""
        scanner = SecretScanner()
        test_dir = Path("/tmp/test_scan_dir")
        test_dir.mkdir(exist_ok=True)
        (test_dir / "config.py").write_text("secret = 'ghp_1234567890abcdef1234567890abcdef1234'\n")
        findings = list(scanner.scan_directory(test_dir))
        self.assertTrue(any(f.rule_name == "github_token" for f in findings))
        import shutil
        shutil.rmtree(test_dir)

    def test_mask_secret(self):
        """Secret masking works."""
        masked = SecretScanner.mask_secret("supersecretpassword", 4, 4)
        self.assertTrue(masked.startswith("supe"))
        self.assertTrue(masked.endswith("word"))
        self.assertIn("*", masked)

    def test_mask_short(self):
        """Short secret fully masked."""
        masked = SecretScanner.mask_secret("abc")
        self.assertEqual(masked, "***")

    def test_rule_count(self):
        """Rules loaded."""
        scanner = SecretScanner()
        self.assertGreater(scanner.rule_count, 0)

    def test_finding_severity(self):
        """Finding has severity."""
        scanner = SecretScanner()
        findings = scanner.scan_text("-----BEGIN PRIVATE KEY-----\n")
        self.assertEqual(findings[0].severity, "CRITICAL")


if __name__ == "__main__":
    unittest.main(verbosity=2)
