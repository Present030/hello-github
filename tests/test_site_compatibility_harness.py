"""Stable contract for the browser/mobile/keyboard compatibility gate."""
from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class CompatibilityHarnessTests(unittest.TestCase):
    def test_required_ci_includes_real_browser_compatibility(self):
        ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn("browser E2E (Chrome + Firefox)", ci)
        self.assertIn(
            "python tools/check_site_compatibility.py --site dist/site/index.html",
            ci,
        )
        self.assertIn("      - browser-e2e", ci)
        self.assertIn("needs.browser-e2e.result", ci)

    def test_site_preserves_keyboard_and_screen_reader_landmarks(self):
        html = (ROOT / "site/index.html").read_text(encoding="utf-8")
        self.assertIn('<html lang="zh-CN">', html)
        self.assertIn('<a class="skip-link" href="#content">', html)
        self.assertIn('<main id="content">', html)
        self.assertIn('role="status" aria-live="polite"', html)
        self.assertIn("a:focus-visible", html)
        self.assertIn("grid-template-columns: repeat(auto-fit, minmax(min(180px, 100%), 1fr))", html)
        for name in ("ci", "release", "recovery", "sbom"):
            self.assertIn(f'id="{name}-evidence" aria-label=', html)
        self.assertIn('aria-label="查看项目健康快照运行记录"', html)
        self.assertIn('aria-label="项目链接"', html)

    def test_browser_driver_is_stdlib_only_and_checks_real_tab(self):
        source = (ROOT / "tools/check_site_compatibility.py").read_text(encoding="utf-8")
        self.assertIn("from urllib.request import", source)
        self.assertIn("def keyboard(", source)
        self.assertIn("browser.key(TAB)", source)
        self.assertIn("return document.activeElement", source)
        for width in (320, 375, 768):
            self.assertIn(str(width), source)
        self.assertIn('scenario("firefox"', source)
        self.assertIn('("HTTP 503"', source)
        self.assertIn('("malformed JSON"', source)


if __name__ == "__main__":
    unittest.main()
