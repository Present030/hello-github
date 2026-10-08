"""Release readiness is a strict prerequisite for publishing VERSION links."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tools.check_release_readiness import REQUIRED_ASSETS, assess_release_readiness

SHA = "a" * 40
OTHER = "b" * 40


def release(tag: str = "v0.3.0") -> dict:
    return {
        "tag_name": tag,
        "draft": False,
        "prerelease": False,
        "target_commitish": SHA,
        "assets": [
            {"name": name, "state": "uploaded", "size": 100,
             "digest": "sha256:" + "f" * 64}
            for name in sorted(REQUIRED_ASSETS)
        ],
    }


def runs(*, head: str = SHA, result: str = "success") -> dict:
    return {
        "workflow_runs": [
            {"id": 100, "name": "workspace-ci", "status": "completed",
             "conclusion": "success", "head_sha": SHA, "event": "push"},
            {"id": 101, "name": "release", "status": "completed",
             "conclusion": result, "head_sha": head, "event": "push"},
        ],
    }


class ReleaseReadinessTests(unittest.TestCase):
    def assess(self, metadata=None, history=None, *, version="0.3.0"):
        return assess_release_readiness(
            version=version,
            release=release() if metadata is None else metadata,
            runs_payload=runs() if history is None else history,
        )

    def test_ready_requires_matching_formal_release_and_successful_run(self):
        result = self.assess()
        self.assertTrue(result["ready"])
        self.assertEqual(result["tag"], "v0.3.0")
        self.assertEqual(result["verified_release_run_id"], 101)
        self.assertEqual(result["reason"], "verified")

    def test_missing_or_wrong_version_does_not_publish(self):
        self.assertEqual(self.assess(metadata={})["reason"], "release_version_mismatch")
        self.assertEqual(self.assess(version="0.4.0")["reason"], "release_version_mismatch")
        self.assertEqual(
            assess_release_readiness(version="0.4.0", release=None, runs_payload=runs())["reason"],
            "release_missing",
        )

    def test_draft_or_prerelease_rejected(self):
        for field in ("draft", "prerelease"):
            with self.subTest(field=field):
                item = release()
                item[field] = True
                self.assertEqual(self.assess(metadata=item)["reason"], "release_not_published")

    def test_tag_target_must_be_a_full_sha(self):
        for bad in (OTHER[:12], "main", None):
            with self.subTest(bad=bad):
                item = release()
                item["target_commitish"] = bad
                self.assertEqual(self.assess(metadata=item)["reason"], "release_target_invalid")

    def test_required_assets_must_all_exist(self):
        for name in REQUIRED_ASSETS:
            with self.subTest(name=name):
                item = release()
                item["assets"] = [a for a in item["assets"] if a["name"] != name]
                result = self.assess(metadata=item)
                self.assertFalse(result["ready"])
                self.assertEqual(result["reason"], "release_assets_incomplete")

    def test_assets_require_positive_size_uploaded_state_and_digest(self):
        for change in (
            {"size": 0}, {"size": False}, {"state": "starter"},
            {"digest": "sha256:not-a-hash"}, {"digest": None},
        ):
            with self.subTest(change=change):
                item = release()
                item["assets"][0].update(change)
                self.assertEqual(self.assess(metadata=item)["reason"], "release_assets_invalid")

    def test_duplicate_asset_name_fails_closed(self):
        item = release()
        item["assets"].append(dict(item["assets"][0]))
        self.assertEqual(self.assess(metadata=item)["reason"], "release_assets_invalid")

    def test_release_run_must_be_completed_and_successful(self):
        for change in (
            {"conclusion": "failure"}, {"conclusion": None},
            {"status": "in_progress"}, {"event": "pull_request"},
            {"name": "workspace-ci"}, {"head_sha": OTHER},
        ):
            with self.subTest(change=change):
                history = runs()
                history["workflow_runs"][1].update(change)
                item = self.assess(history=history)
                self.assertFalse(item["ready"])
                self.assertEqual(item["reason"], "release_verification_pending")

    def test_paginated_runs_and_distractor_latest_run(self):
        history = [
            {"workflow_runs": [runs()["workflow_runs"][1]]},
            {"workflow_runs": [
                {"id": 200, "name": "release", "head_sha": OTHER,
                 "status": "completed", "conclusion": "success", "event": "push"},
            ]},
        ]
        self.assertEqual(self.assess(history=history)["verified_release_run_id"], 101)

    def test_api_unavailable_means_pending_not_ready(self):
        for missing in (None, {}, [], {"workflow_runs": []}, "not-json"):
            with self.subTest(missing=missing):
                self.assertEqual(self.assess(history=missing)["reason"],
                                 "release_verification_pending")

    def test_malformed_version_is_rejected(self):
        with self.assertRaises(ValueError):
            self.assess(version="v0.3")

    def test_cli_pending_is_clean_and_never_fabricates_success(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as folder:
            temp = Path(folder)
            (temp / "VERSION").write_text("0.4.0\n", encoding="utf-8")
            output = temp / "readiness.json"
            call = subprocess.run(
                [sys.executable, str(root / "tools/check_release_readiness.py"),
                 "--version-file", str(temp / "VERSION"),
                 "--release-json", str(temp / "missing-release.json"),
                 "--runs-json", str(temp / "missing-runs.json"),
                 "--output", str(output)],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(call.returncode, 0, call.stderr)
            result = json.loads(output.read_text(encoding="utf-8"))
            self.assertFalse(result["ready"])
            self.assertEqual(result["tag"], "v0.4.0")
            self.assertEqual(result["reason"], "release_missing")

    def test_pages_never_deploys_until_release_gate_is_ready(self):
        root = Path(__file__).resolve().parents[1]
        wf = (root / ".github/workflows/pages.yml").read_text(encoding="utf-8")
        self.assertIn('workflows: ["project-health", "release"]', wf)
        self.assertIn("jobs:\n  release-ready:", wf)
        self.assertIn("    needs: release-ready", wf)
        self.assertIn("if: \${{ needs.release-ready.outputs.ready == 'true' }}", wf)
        self.assertIn("tools/check_release_readiness.py", wf)
        self.assertIn("github.event.workflow_run.name == 'release'", wf)
        self.assertIn("github.event.workflow_run.conclusion == 'success'", wf)
        self.assertIn("main_sha: \${{ steps.verify.outputs.main_sha }}", wf)
        self.assertIn('test "$(git rev-parse HEAD)" = "$VERIFIED_MAIN_SHA"', wf)
        self.assertIn("      actions: read\n      contents: read", wf)


if __name__ == "__main__":
    unittest.main()
