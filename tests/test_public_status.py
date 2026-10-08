"""The public status feed must fail closed and never leak arbitrary source data."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest

from tools.build_public_status import build_public_status, WORKFLOWS, PUBLIC_SCHEMA

SHA = "a" * 40
OTHER = "b" * 40
NOW = datetime(2026, 10, 8, 12, tzinfo=timezone.utc)


def sample(*, status: str = "healthy", kind: str = "main_ci_success"):
    source = {
        "schema": "hello-github-project-health/v1",
        "snapshot_kind": kind,
        "status": status,
        "head_sha": SHA,
        "generated_at": (NOW - timedelta(hours=1)).isoformat(),
        "version": "0.3.0",
        "release": {
            "tag": "v0.3.0", "target_commit": OTHER,
            "assets": {
                "hello-github.pyz": {"digest": "sha256:" + "f" * 64},
                "hello-github.cdx.json": {"digest": "private-value-must-not-leak"},
                "hello-github-recovery.zip": {},
            },
        },
        "checks": {"current_main_ci": True, "release_alignment": True},
        "workflow_evidence": {},
        "secret": "top-secret-not-for-publication",
    }
    for i, name in enumerate(WORKFLOWS, start=1):
        source["workflow_evidence"][name] = {
            "id": i, "head_sha": SHA if name == "workspace-ci" else OTHER,
            "state": "current" if name == "workspace-ci" else "historical",
            "conclusion": "success",
            "observed_at": (NOW - timedelta(days=2)).isoformat(),
            "token": "never-publish-me",
        }
    return source


class PublicStatusTests(unittest.TestCase):
    def build(self, source, *, head=SHA, run=998, now=NOW):
        return build_public_status(source, main_sha=head, source_run_id=run, now=now)

    def test_healthy_snapshot_emits_explicit_allowed_public_fields(self):
        payload = self.build(sample())
        self.assertEqual(payload["schema"], PUBLIC_SCHEMA)
        self.assertEqual(payload["status"], "healthy")
        self.assertIsNone(payload["reason"])
        self.assertEqual(payload["source_run_id"], 998)
        self.assertEqual(payload["version"], "0.3.0")
        self.assertEqual(payload["release"]["tag"], "v0.3.0")
        self.assertTrue(payload["release"]["has_sbom"])
        self.assertTrue(payload["release"]["has_recovery_bundle"])
        self.assertEqual(payload["workflows"]["workspace-ci"]["run_id"], 1)
        self.assertEqual(
            payload["expires_at"],
            (NOW - timedelta(hours=1) + timedelta(days=30)).isoformat(),
        )
        rendered = json.dumps(payload)
        for marker in ("top-secret-not-for-publication", "never-publish-me",
                       "private-value-must-not-leak", '"token"', '"secret"'):
            self.assertNotIn(marker, rendered)

    def test_missing_source_is_unknown_not_healthy(self):
        payload = self.build(None, run=0)
        self.assertEqual(payload["status"], "unknown")
        self.assertEqual(payload["reason"], "missing_snapshot")
        self.assertIsNone(payload["source_run_id"])

    def test_expired_source_cannot_be_refreshed_by_deploying_again(self):
        source = sample()
        source["generated_at"] = (NOW - timedelta(days=31)).isoformat()
        result = self.build(source)
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["reason"], "expired_snapshot")
        self.assertLess(result["expires_at"], result["published_at"])

    def test_head_mismatch_is_unknown(self):
        self.assertEqual(self.build(sample(), head=OTHER)["reason"], "head_mismatch")

    def test_invalid_schema_timestamp_and_bad_ci_fail_closed(self):
        for corruption, reason in (
            (lambda x: x.update(schema="unknown"), "invalid_schema"),
            (lambda x: x.update(generated_at="not-an-iso-time"), "invalid_timestamp"),
            (lambda x: x.update(generated_at=(NOW + timedelta(hours=2)).isoformat()), "invalid_timestamp"),
            (lambda x: x["workflow_evidence"]["workspace-ci"].update(id="999"), "invalid_ci"),
            (lambda x: x["checks"].update(current_main_ci=False), "inconsistent_snapshot"),
            (lambda x: x.update(status="surprise"), "invalid_status"),
        ):
            source = sample()
            corruption(source)
            with self.subTest(reason=reason):
                public = self.build(source)
                self.assertEqual(public["status"], "unknown")
                self.assertEqual(public["reason"], reason)

    def test_failed_ci_snapshot_preserves_degraded_without_inventing_results(self):
        source = sample(status="degraded", kind="ci_failure")
        source["version"] = None
        source["release"] = {"tag": None, "assets": {}}
        source["workflow_evidence"] = {
            "workspace-ci": {
                "id": 101, "run_number": 3, "event": "push",
                "head_sha": SHA, "conclusion": "failure"
            }
        }
        payload = self.build(source)
        self.assertEqual(payload["status"], "degraded")
        self.assertEqual(payload["workflows"]["workspace-ci"]["state"], "failed")
        self.assertIsNone(payload["workflows"]["cold-start-audit"])
        self.assertIsNone(payload["release"]["tag"])

    def test_healthy_with_stale_workflow_cannot_be_trusted(self):
        source = sample()
        source["workflow_evidence"]["cold-start-audit"]["state"] = "stale"
        payload = self.build(source)
        self.assertEqual(payload["status"], "unknown")
        self.assertEqual(payload["reason"], "inconsistent_snapshot")

    def test_invalid_nested_evidence_types_do_not_crash(self):
        for field, value in (("state", []), ("conclusion", {}),
                             ("id", False), ("head_sha", None)):
            with self.subTest(field=field):
                source = sample()
                source["workflow_evidence"]["workspace-ci"][field] = value
                result = self.build(source)
                self.assertEqual(result["status"], "unknown")
                self.assertEqual(result["reason"], "invalid_ci")

    def test_invalid_kind_does_not_crash(self):
        source = sample()
        source["snapshot_kind"] = []
        self.assertEqual(self.build(source)["reason"], "invalid_schema")

    def test_invalid_expected_main_sha_is_rejected(self):
        with self.assertRaises(ValueError):
            self.build(sample(), head="bad")

    def test_public_status_workflow_wiring_and_no_untrusted_checkout(self):
        root = Path(__file__).resolve().parents[1]
        wf = (root / ".github/workflows/pages.yml").read_text(encoding="utf-8")
        self.assertIn('workflows: ["project-health"]', wf)
        self.assertIn('ref: main', wf)
        self.assertIn("actions: read", wf)
        self.assertIn("github.event.workflow_run.name == 'project-health'", wf)
        self.assertIn('sort_by(.id) | last', wf)
        self.assertIn('select(.head_sha == $sha', wf)
        self.assertIn('tools/build_public_status.py', wf)
        self.assertIn("github.event.workflow_run.name == 'project-health'", wf)
        self.assertIn('path: dist/site', wf)
        self.assertIn('public status feed matches allowlisted JSON byte-for-byte', wf)
        self.assertNotIn("ref: ${{ github.event.workflow_run.head_sha }}", wf)


if __name__ == "__main__":
    unittest.main()
