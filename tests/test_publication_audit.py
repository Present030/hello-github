"""Publication audit is separate from historical privacy heuristics."""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from tools.audit_public_exposure import audit_public_directory


def make_site(root: Path):
    root.mkdir(exist_ok=True)
    (root / "index.html").write_text("<!doctype html><html>hello</html>", encoding="utf-8")
    (root / "status.json").write_text('{"status": "unknown"}', encoding="utf-8")


class PublicationExposureTests(unittest.TestCase):
    def test_clean_generated_site(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "site"
            make_site(root)
            self.assertEqual(audit_public_directory(root), [])

    def test_unexpected_private_asset_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "site"
            make_site(root)
            (root / "notes.txt").write_text("unexpected public content", encoding="utf-8")
            findings = audit_public_directory(root)
            self.assertTrue(any(x.severity == "BLOCK" and x.rule == "unexpected-public-asset"
                                for x in findings))

    def test_missing_and_unreadable_assets_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "site"
            make_site(root)
            (root / "status.json").unlink()
            self.assertTrue(any(x.rule == "missing-public-asset"
                                for x in audit_public_directory(root)))
            (root / "status.json").write_bytes(b"\x00invalid")
            self.assertTrue(any(x.rule == "unscannable-public-asset"
                                for x in audit_public_directory(root)))

    def test_real_token_format_blocks_without_echo(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "site"
            make_site(root)
            value = "gh" + "p_" + ("Z" * 40)
            (root / "status.json").write_text('{"token": "' + value + '"}', encoding="utf-8")
            findings = audit_public_directory(root)
            self.assertTrue(any(x.severity == "BLOCK" and x.rule == "github-token"
                                for x in findings))
            self.assertTrue(all(value not in x.location for x in findings))

    def test_privacy_indicators_stay_non_blocking(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "site"
            make_site(root)
            (root / "status.json").write_text('{"host": "192.' + '168.1.5"}', encoding="utf-8")
            findings = audit_public_directory(root)
            self.assertTrue(any(x.rule == "private-ip-address" and x.severity == "ADVISORY"
                                for x in findings))
            self.assertFalse(any(x.severity == "BLOCK" for x in findings))

    def test_pages_checks_generated_payload_before_upload(self):
        root = Path(__file__).resolve().parents[1]
        page = (root / ".github/workflows/pages.yml").read_text(encoding="utf-8")
        build = page.index("      - name: Render allowlisted public status")
        audit = page.index("      - name: Audit final Pages upload directory")
        upload = page.index("      - name: Upload Pages artifact")
        self.assertLess(build, audit)
        self.assertLess(audit, upload)
        self.assertIn("python tools/audit_public_exposure.py --public-dir dist/site", page)


if __name__ == "__main__":
    unittest.main()
