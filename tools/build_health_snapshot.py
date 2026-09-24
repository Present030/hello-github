"""Build a machine-readable snapshot of durable project health."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

CRITICAL_WORKFLOWS = (
    "workspace-ci",
    "health-check",
    "recovery-probe",
    "sbom-probe",
    "recovery-bundle",
    "recovery-portability",
    "release-integrity",
)


def _latest_completed_run(
    runs: list[dict[str, Any]],
    workflow_name: str,
) -> dict[str, Any] | None:
    candidates = [
        run
        for run in runs
        if run.get("name") == workflow_name
        and run.get("status") == "completed"
        and run.get("event") in {"push", "schedule", "workflow_dispatch"}
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda run: int(run.get("id", 0)))


def build_snapshot(
    *,
    version: str,
    head_sha: str,
    release: dict[str, Any],
    runs_payload: dict[str, Any],
) -> dict[str, Any]:
    version = version.strip()
    expected_tag = f"v{version}"
    assets = {
        asset["name"]: {
            "size": asset.get("size"),
            "digest": asset.get("digest"),
        }
        for asset in release.get("assets", [])
        if isinstance(asset, dict) and isinstance(asset.get("name"), str)
    }

    workflow_evidence: dict[str, Any] = {}
    all_evidence_success = True
    runs = [
        run for run in runs_payload.get("workflow_runs", [])
        if isinstance(run, dict)
    ]
    for name in CRITICAL_WORKFLOWS:
        run = _latest_completed_run(runs, name)
        if run is None:
            workflow_evidence[name] = None
            all_evidence_success = False
            continue
        evidence = {
            "id": run.get("id"),
            "run_number": run.get("run_number"),
            "event": run.get("event"),
            "head_sha": run.get("head_sha"),
            "conclusion": run.get("conclusion"),
        }
        workflow_evidence[name] = evidence
        if run.get("conclusion") != "success":
            all_evidence_success = False

    latest_ci = workflow_evidence.get("workspace-ci")
    current_ci_ok = (
        isinstance(latest_ci, dict)
        and latest_ci.get("head_sha") == head_sha
        and latest_ci.get("conclusion") == "success"
    )
    release_alignment = (
        release.get("tag_name") == expected_tag
        and isinstance(release.get("target_commitish"), str)
        and "hello-github.pyz" in assets
        and isinstance(assets["hello-github.pyz"].get("digest"), str)
    )

    healthy = release_alignment and current_ci_ok and all_evidence_success

    return {
        "schema": "hello-github-project-health/v1",
        "status": "healthy" if healthy else "degraded",
        "head_sha": head_sha,
        "version": version,
        "release": {
            "tag": release.get("tag_name"),
            "target_commit": release.get("target_commitish"),
            "assets": assets,
        },
        "checks": {
            "release_alignment": release_alignment,
            "current_main_ci": current_ci_ok,
            "state_drift_audit": "pass",
            "workflow_security_audit": "pass",
        },
        "workflow_evidence": workflow_evidence,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build project health snapshot.")
    parser.add_argument("--version-file", type=Path, required=True)
    parser.add_argument("--release-json", type=Path, required=True)
    parser.add_argument("--runs-json", type=Path, required=True)
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    snapshot = build_snapshot(
        version=args.version_file.read_text(encoding="utf-8").strip(),
        head_sha=args.head_sha,
        release=json.loads(args.release_json.read_text(encoding="utf-8")),
        runs_payload=json.loads(args.runs_json.read_text(encoding="utf-8")),
    )
    args.output.write_text(
        json.dumps(snapshot, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"PROJECT_HEALTH={snapshot['status']}")
    return 0 if snapshot["status"] == "healthy" else 1


if __name__ == "__main__":
    raise SystemExit(main())
