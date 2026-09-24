from __future__ import annotations

import unittest

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


if __name__ == "__main__":
    unittest.main()
