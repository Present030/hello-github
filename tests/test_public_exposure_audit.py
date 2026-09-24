"""Tests for public exposure auditing."""

from __future__ import annotations

import unittest

from tools.audit_public_exposure import scan_path, scan_text


class PublicExposureAuditTests(unittest.TestCase):
    def test_private_key_is_blocking(self) -> None:
        marker = "-----BEGIN " + "PRIVATE KEY-----"
        findings = scan_text(marker, "fixture.txt")
        self.assertTrue(
            any(item.severity == "BLOCK" and item.rule == "private-key" for item in findings)
        )

    def test_github_token_is_blocking_without_echoing_value(self) -> None:
        token = "gh" + "p_" + ("A" * 36)
        findings = scan_text(f"token={token}", "fixture.txt")
        self.assertTrue(any(item.rule == "github-token" for item in findings))
        self.assertTrue(all(token not in item.location for item in findings))

    def test_real_email_is_advisory(self) -> None:
        findings = scan_text("contact alice@company.invalid", "fixture.txt")
        self.assertTrue(
            any(item.severity == "ADVISORY" and item.rule == "email-address" for item in findings)
        )

    def test_github_noreply_email_is_allowed(self) -> None:
        findings = scan_text(
            "123+user@users.noreply.github.com",
            "fixture.txt",
        )
        self.assertFalse(any(item.rule == "email-address" for item in findings))

    def test_private_ip_is_advisory(self) -> None:
        findings = scan_text("host=192.168.1.5", "fixture.txt")
        self.assertTrue(any(item.rule == "private-ip-address" for item in findings))

    def test_sensitive_filename_is_advisory(self) -> None:
        findings = scan_path(".env", b"MODE=test\n")
        self.assertTrue(any(item.rule == "sensitive-filename" for item in findings))


if __name__ == "__main__":
    unittest.main()
