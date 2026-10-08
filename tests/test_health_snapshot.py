from __future__ import annotations

import unittest
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import textwrap

from tools.build_health_snapshot import build_snapshot, CRITICAL_WORKFLOWS


HEAD = "a" * 40
RELEASE_TARGET = "b" * 40


def release() -> dict[str, object]:
    return {
        "tag_name": "v1.2.3",
        "target_commitish": RELEASE_TARGET,
        "assets": [
            {
                "name": "hello-github.pyz",
                "size": 123,
                "digest": "sha256:" + "c" * 64,
            }
        ],
    }


def runs(*, ci_head: str = HEAD, failed: str | None = None) -> dict[str, object]:
    items = []
    for index, name in enumerate(CRITICAL_WORKFLOWS, start=1):
        items.append(
            {
                "id": 100 + index,
                "name": name,
                "status": "completed",
                "conclusion": "failure" if name == failed else "success",
                "run_number": index,
                "event": "push",
                "head_sha": ci_head if name == "workspace-ci" else "d" * 40,
            }
        )
    return {"workflow_runs": items}


class HealthSnapshotTests(unittest.TestCase):
    def test_healthy_snapshot_requires_current_ci_and_evidence(self) -> None:
        snapshot = build_snapshot(
            version="1.2.3",
            head_sha=HEAD,
            release=release(),
            runs_payload=runs(),
        )
        self.assertEqual(snapshot["status"], "healthy")
        self.assertTrue(snapshot["checks"]["release_alignment"])
        self.assertTrue(snapshot["checks"]["current_main_ci"])

    def test_current_ci_event_overrides_stale_api_listing(self) -> None:
        snapshot = build_snapshot(
            version="1.2.3",
            head_sha=HEAD,
            release=release(),
            runs_payload=runs(ci_head="e" * 40),
            current_ci={
                "id": 999,
                "run_number": 42,
                "event": "push",
                "head_sha": HEAD,
                "conclusion": "success",
            },
        )
        self.assertEqual(snapshot["status"], "healthy")
        self.assertTrue(snapshot["checks"]["current_main_ci"])
        self.assertEqual(snapshot["workflow_evidence"]["workspace-ci"]["id"], 999)


    def test_paginated_runs_find_older_critical_workflow(self) -> None:
        first_page = runs()
        first_page["workflow_runs"] = [
            run
            for run in first_page["workflow_runs"]
            if run["name"] != "recovery-probe"
        ]
        recovery_probe = next(
            run
            for run in runs()["workflow_runs"]
            if run["name"] == "recovery-probe"
        )
        snapshot = build_snapshot(
            version="1.2.3",
            head_sha=HEAD,
            release=release(),
            runs_payload=[
                first_page,
                {"workflow_runs": [recovery_probe]},
            ],
        )
        self.assertEqual(snapshot["status"], "healthy")
        self.assertEqual(
            snapshot["workflow_evidence"]["recovery-probe"]["conclusion"],
            "success",
        )

    def test_release_drift_degrades_snapshot(self) -> None:
        payload = release()
        payload["tag_name"] = "v9.9.9"
        snapshot = build_snapshot(
            version="1.2.3",
            head_sha=HEAD,
            release=payload,
            runs_payload=runs(),
        )
        self.assertEqual(snapshot["status"], "degraded")
        self.assertFalse(snapshot["checks"]["release_alignment"])

    def test_stale_current_ci_degrades_snapshot(self) -> None:
        snapshot = build_snapshot(
            version="1.2.3",
            head_sha=HEAD,
            release=release(),
            runs_payload=runs(ci_head="e" * 40),
        )
        self.assertEqual(snapshot["status"], "degraded")
        self.assertFalse(snapshot["checks"]["current_main_ci"])

    def test_failed_critical_workflow_degrades_snapshot(self) -> None:
        snapshot = build_snapshot(
            version="1.2.3",
            head_sha=HEAD,
            release=release(),
            runs_payload=runs(failed="recovery-bundle"),
        )
        self.assertEqual(snapshot["status"], "degraded")



class FailedCIEventWorkflowTests(unittest.TestCase):
    """Execute the exact inline no-checkout failure recorder with synthetic events."""

    def setUp(self) -> None:
        workflow = (
            Path(__file__).resolve().parents[1]
            / ".github/workflows/project-health.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("  ci-failure-snapshot:", workflow)
        section = workflow.split("  ci-failure-snapshot:", 1)[1]
        self.assertIn(
            "github.event.workflow_run.conclusion != 'success'", section
        )
        self.assertIn("github.event.workflow_run.head_branch == 'main'", section)
        self.assertIn("github.event.workflow_run.event == 'push'", section)
        self.assertNotIn("actions/checkout@", section)
        self.assertIn("name: project-health", section)
        self.assertIn("run: exit 1", section)

        match = re.search(
            r"          python - <<'PY'\n(.*?)\n          PY",
            section,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(match)
        assert match is not None
        self.script = textwrap.dedent(match.group(1))

    def run_event(
        self,
        *,
        conclusion: str,
        event_name: str = "push",
        head_branch: str = "main",
    ) -> tuple[subprocess.CompletedProcess[str], dict[str, object] | None]:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            event = {
                "repository": {"full_name": "Present030/hello-github"},
                "workflow_run": {
                    "id": 123456,
                    "run_number": 17,
                    "event": event_name,
                    "head_branch": head_branch,
                    "head_sha": HEAD,
                    "conclusion": conclusion,
                },
            }
            event_path = root / "event.json"
            event_path.write_text(json.dumps(event), encoding="utf-8")
            env = {
                **os.environ,
                "GITHUB_EVENT_PATH": str(event_path),
                "GITHUB_REPOSITORY": "Present030/hello-github",
            }
            completed = subprocess.run(
                [sys.executable, "-c", self.script],
                cwd=root,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            snapshot_path = root / "project-health.json"
            snapshot = (
                json.loads(snapshot_path.read_text(encoding="utf-8"))
                if snapshot_path.exists() else None
            )
            return completed, snapshot

    def test_failure_and_cancellation_generate_degraded_evidence(self) -> None:
        for conclusion in ("failure", "cancelled", "timed_out"):
            with self.subTest(conclusion=conclusion):
                process, snapshot = self.run_event(conclusion=conclusion)
                self.assertEqual(process.returncode, 0, process.stderr)
                self.assertIsNotNone(snapshot)
                assert snapshot is not None
                self.assertEqual(snapshot["schema"], "hello-github-project-health/v1")
                self.assertEqual(snapshot["status"], "degraded")
                self.assertEqual(snapshot["snapshot_kind"], "ci_failure")
                self.assertEqual(snapshot["head_sha"], HEAD)
                self.assertIsNone(snapshot["version"])
                self.assertFalse(snapshot["checks"]["current_main_ci"])
                self.assertEqual(snapshot["checks"]["state_drift_audit"], "not_run")
                self.assertEqual(
                    snapshot["workflow_evidence"]["workspace-ci"]["conclusion"],
                    conclusion,
                )
                self.assertEqual(snapshot["workflow_evidence"]["workspace-ci"]["id"], 123456)
                self.assertEqual(
                    snapshot["degraded_reasons"], [f"main_ci_{conclusion}"]
                )
                self.assertIn("PROJECT_HEALTH=degraded", process.stdout)

    def test_rejects_success_and_non_main_push_events(self) -> None:
        for kwargs in (
            {"conclusion": "success"},
            {"conclusion": "failure", "event_name": "pull_request"},
            {"conclusion": "failure", "head_branch": "feature"},
        ):
            with self.subTest(kwargs=kwargs):
                process, snapshot = self.run_event(**kwargs)
                self.assertNotEqual(process.returncode, 0)
                self.assertIsNone(snapshot)




if __name__ == "__main__":
    unittest.main()
