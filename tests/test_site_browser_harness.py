"""Unit tests for the real-Chrome harness contract (Chrome itself runs in CI)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import urllib.error
import urllib.request
import unittest

from tools.check_site_browser import (
    fixture_status, serve_fixture, visible_text,
)

NOW = datetime(2026, 10, 8, 12, tzinfo=timezone.utc)


class BrowserHarnessTests(unittest.TestCase):
    def test_fixture_public_status_healthy_and_failed(self) -> None:
        good = fixture_status(NOW, "0.3.0")
        self.assertEqual(good["status"], "healthy")
        self.assertEqual(good["workflows"]["workspace-ci"]["state"], "current")
        self.assertEqual(good["release"]["tag"], "v0.3.0")
        bad = fixture_status(NOW, "0.3.0", failed=True)
        self.assertEqual(bad["status"], "degraded")
        self.assertEqual(bad["workflows"]["workspace-ci"]["state"], "failed")
        self.assertIsNone(bad["workflows"]["cold-start-audit"])

    def test_dom_inspection_reads_rendered_values(self) -> None:
        html = '<html><p id="status-overview">项目状态：健康（快照时）</p>' \
               '<span class="status-value" id="ci-value">通过</span></html>'
        self.assertIn("健康", visible_text(html, "status-overview"))
        self.assertEqual(visible_text(html, "ci-value"), "通过")
        with self.assertRaisesRegex(AssertionError, "lacks missing-id"):
            visible_text(html, "missing-id")

    def test_local_fixture_serves_only_site_and_status(self) -> None:
        server = serve_fixture(
            b"<html><body>page</body></html>", b'{"status":"unknown"}'
        )
        try:
            base = f"http://127.0.0.1:{server.server_port}"
            with urllib.request.urlopen(base + "/") as response:
                self.assertIn(b"page", response.read())
            with urllib.request.urlopen(base + "/status.json?checked=123") as response:
                self.assertEqual(json.load(response)["status"], "unknown")
                self.assertEqual(response.headers["Cache-Control"], "no-store")
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(base + "/secret")
            self.assertEqual(ctx.exception.code, 404)
        finally:
            server.shutdown()
            server.server_close()

    def test_expected_browser_job_is_required_in_gate(self) -> None:
        root = Path(__file__).resolve().parents[1]
        ci = (root / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        pages = (root / ".github/workflows/pages.yml").read_text(encoding="utf-8")
        cold = (root / ".github/workflows/cold-start-audit.yml").read_text(encoding="utf-8")
        self.assertIn("  browser-e2e:", ci)
        self.assertIn("      - browser-e2e", ci)
        self.assertIn('needs.browser-e2e.result', ci)
        self.assertIn("tools/check_site_browser.py --site dist/site/index.html", ci)
        self.assertIn('tools/check_site_browser.py --public-url "$PAGE_URL"', pages)
        self.assertIn("source/tools/check_site_browser.py", cold)
        self.assertIn("--site recovered-site/index.html", cold)
        self.assertIn('--public-url "$PAGES_URL"', cold)


if __name__ == "__main__":
    unittest.main()
