"""Exercise the actual inline website script with a minimal DOM and fake HTTP.

No browser framework or third-party JS package is required. Cross-browser
and full deployed-site tests remain a separate ROADMAP item.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import unittest

from tools.render_site import render

ROOT = Path(__file__).resolve().parents[1]
SHA = "a" * 40
OTHER = "b" * 40
NOW = datetime(2026, 10, 8, 12, tzinfo=timezone.utc)

NODE_HARNESS = r"""
const vm = require("node:vm");
const fs = require("node:fs");
const payload = JSON.parse(process.env.TEST_PAYLOAD);
const src = fs.readFileSync(0, "utf8");
let clock = payload.clock;
const intervals = [];
const events = {};
const nodes = {};
function node(id) {
  if (!nodes[id]) {
    nodes[id] = {
      textContent: id === "version-value" ? "v0.3.0" : "",
      hidden: true, href: null,
      removeAttribute(key) { if (key === "href") this.href = null; }
    };
  }
  return nodes[id];
}
class ClockDate extends Date {
  static now() { return clock; }
}
const document = {
  hidden: false,
  getElementById: node,
  addEventListener(name, fn) { events[name] = fn; }
};
const fakeFetch = async (_uri, options) => {
  if (payload.network_error) throw new Error("network offline");
  if (!options || options.cache !== "no-store") throw new Error("cache not disabled");
  return {
    ok: !payload.http_error,
    json: async () => payload.document
  };
};
const context = {
  document, fetch: fakeFetch, Date: ClockDate,
  setInterval(fn, ms) { intervals.push({fn, ms}); },
  console,
};
vm.runInNewContext(src, context, {timeout: 2000});
setImmediate(() => {
  if (payload.advance_ms) {
    clock += payload.advance_ms;
    const expiryCheck = intervals.find(x => x.ms === 60000);
    if (expiryCheck) expiryCheck.fn();
  }
  const names = ["ci", "release", "recovery", "sbom"];
  const cards = Object.fromEntries(names.map(n => [n, {
    value: node(n + "-value").textContent,
    detail: node(n + "-detail").textContent,
    href: node(n + "-evidence").href,
    hidden: node(n + "-evidence").hidden
  }]));
  process.stdout.write(JSON.stringify({
    overview: node("status-overview").textContent,
    meta: node("status-meta").textContent,
    cards,
    source: {hidden: node("health-evidence").hidden, href: node("health-evidence").href},
    intervals: intervals.map(x=>x.ms)
  }));
});
"""


def snapshot(*, status: str = "healthy") -> dict[str, object]:
    generated = NOW - timedelta(hours=1)
    names = ("workspace-ci", "release-integrity", "cold-start-audit", "sbom-probe")
    workflow = {}
    for index, name in enumerate(names, 1):
        workflow[name] = {
            "run_id": 100 + index,
            "state": "current" if name == "workspace-ci" else "historical",
            "conclusion": "success",
            "head_sha": SHA if name == "workspace-ci" else OTHER,
            "observed_at": (NOW - timedelta(days=3)).isoformat(),
        }
    return {
        "schema": "hello-github-public-status/v1",
        "status": status,
        "head_sha": SHA,
        "source_run_id": 345,
        "source_generated_at": generated.isoformat(),
        "expires_at": (generated + timedelta(days=30)).isoformat(),
        "version": "0.3.0",
        "checks": {"current_main_ci": status == "healthy", "release_alignment": True},
        "release": {
            "tag": "v0.3.0",
            "has_recovery_bundle": True,
            "has_sbom": True,
        },
        "workflows": workflow,
    }


class LiveStatusCardsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        template = (ROOT / "site/index.html").read_text(encoding="utf-8")
        cls.html = render(template, "0.3.0")
        match = re.search(r"<script>\s*(.*?)\s*</script>", cls.html, re.DOTALL)
        if match is None:
            raise AssertionError("website has no inline status renderer")
        cls.script = match.group(1)
        cls.node = shutil.which("node")

    def run_script(self, data=None, **flags) -> dict:
        if self.node is None:
            self.skipTest("Node.js is not installed; browser script runtime test skipped")
        payload = {"clock": int(NOW.timestamp() * 1000), "document": data, **flags}
        process = subprocess.run(
            [self.node, "-e", NODE_HARNESS],
            input=self.script,
            text=True,
            capture_output=True,
            env={**os.environ, "TEST_PAYLOAD": json.dumps(payload)},
            check=False,
            timeout=15,
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        return json.loads(process.stdout)

    def test_healthy_is_evidence_backed_not_optimistic(self) -> None:
        result = self.run_script(snapshot())
        self.assertIn("健康", result["overview"])
        self.assertEqual(result["cards"]["ci"]["value"], "通过")
        self.assertEqual(result["cards"]["release"]["value"], "历史验证")
        self.assertEqual(result["cards"]["recovery"]["value"], "历史通过")
        self.assertEqual(result["cards"]["sbom"]["value"], "已包含")
        self.assertIn("历史提交", result["cards"]["release"]["detail"])
        self.assertEqual(
            result["cards"]["ci"]["href"],
            "https://github.com/Present030/hello-github/actions/runs/101",
        )
        self.assertEqual(
            result["source"]["href"],
            "https://github.com/Present030/hello-github/actions/runs/345",
        )
        self.assertEqual(result["intervals"], [300000, 60000])

    def test_ci_failure_can_be_shown_without_optimistic_success(self) -> None:
        data = snapshot(status="degraded")
        data["version"] = None
        data["workflows"]["workspace-ci"].update(state="failed", conclusion="failure")
        data["release"] = {"tag": None, "has_recovery_bundle": None, "has_sbom": None}
        result = self.run_script(data)
        self.assertIn("异常", result["overview"])
        self.assertEqual(result["cards"]["ci"]["value"], "未通过")
        self.assertEqual(result["cards"]["release"]["value"], "未知")
        self.assertEqual(result["cards"]["sbom"]["value"], "未知")

    def test_http_and_network_errors_fail_closed(self) -> None:
        for flags in ({"network_error": True}, {"http_error": True}):
            with self.subTest(flags=flags):
                result = self.run_script(snapshot(), **flags)
                self.assertIn("未知", result["overview"])
                self.assertTrue(result["source"]["hidden"])
                self.assertTrue(all(card["value"] == "未知" for card in result["cards"].values()))

    def test_expired_feed_or_open_tab_aging_resets_cards(self) -> None:
        data = snapshot()
        result = self.run_script(data, advance_ms=31 * 86400000)
        self.assertIn("未知", result["overview"])
        self.assertTrue(all(card["value"] == "未知" for card in result["cards"].values()))
        data["expires_at"] = (NOW - timedelta(seconds=1)).isoformat()
        self.assertIn("未知", self.run_script(data)["overview"])

    def test_mismatched_version_and_unknown_feed_fail_closed(self) -> None:
        data = snapshot()
        data["version"] = "9.9.9"
        self.assertIn("未知", self.run_script(data)["overview"])
        data = snapshot()
        data["status"] = "unknown"
        self.assertIn("未知", self.run_script(data)["overview"])

    def test_missing_evidence_cannot_be_labeled_success(self) -> None:
        data = snapshot()
        data["workflows"].pop("release-integrity")
        data["workflows"]["cold-start-audit"] = None
        data["checks"]["current_main_ci"] = None
        result = self.run_script(data)
        self.assertEqual(result["cards"]["ci"]["value"], "未知")
        self.assertEqual(result["cards"]["release"]["value"], "未知")
        self.assertEqual(result["cards"]["recovery"]["value"], "未知")

    def test_sbom_reflects_release_asset_not_historic_probe(self) -> None:
        data = snapshot()
        data["release"]["has_sbom"] = False
        result = self.run_script(data)
        self.assertEqual(result["cards"]["sbom"]["value"], "未包含")

    def test_static_markup_is_accessible_and_has_no_hardcoded_green_labels(self) -> None:
        self.assertIn('aria-live="polite"', self.html)
        self.assertIn('href="./status.json"', self.html)
        self.assertIn('id="version-value">v0.3.0', self.html)
        for phrase in ('>Passing</span>', '>Verified</span>',
                       '>Ready</span>', '>Included</span>'):
            self.assertNotIn(phrase, self.html)


if __name__ == "__main__":
    unittest.main()
