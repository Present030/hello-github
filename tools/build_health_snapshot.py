"""Build a machine-readable, freshness-aware snapshot of durable project health."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any

# Freshness is an operational policy, not proof that a historic run tested
# current code. Probe runs do not automatically rerun for every main commit.
MAX_EVIDENCE_AGE_DAYS = 30
FUTURE_CLOCK_SKEW = timedelta(minutes=5)

CRITICAL_WORKFLOWS = (
    "workspace-ci",
    "health-check",
    "recovery-probe",
    "sbom-probe",
    "recovery-bundle",
    "recovery-portability",
    "release-integrity",
    "cold-start-audit",
    "Deploy website to GitHub Pages",
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


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if result.tzinfo is None:
        return None
    return result.astimezone(timezone.utc)


def _assess_run(
    run: dict[str, Any] | None,
    *,
    head_sha: str,
    now: datetime,
) -> dict[str, Any] | None:
    if run is None:
        return None

    # The relevant commit is the triggering run's head, not the historical
    # release tag or the latest commit at snapshot generation time.
    run_head = run.get("head_sha")
    relation = (
        "current_main" if run_head == head_sha
        else "historical_commit" if isinstance(run_head, str) and len(run_head) == 40
        else "unknown"
    )
    raw_time = run.get("updated_at") or run.get("created_at")
    observed = _parse_timestamp(raw_time)
    if observed is None or observed > now + FUTURE_CLOCK_SKEW:
        freshness, age_seconds = "unknown", None
    else:
        age_seconds = max(0, int((now - observed).total_seconds()))
        freshness = (
            "stale" if now - observed > timedelta(days=MAX_EVIDENCE_AGE_DAYS)
            else "fresh"
        )

    conclusion = run.get("conclusion")
    if relation == "unknown" or freshness == "unknown" or not isinstance(conclusion, str):
        state = "unknown"
    elif conclusion != "success":
        state = "failed"
    elif freshness == "stale":
        state = "stale"
    elif relation == "current_main":
        state = "current"
    else:
        state = "historical"

    return {
        "id": run.get("id"),
        "run_number": run.get("run_number"),
        "event": run.get("event"),
        "head_sha": run_head,
        "conclusion": conclusion,
        "observed_at": observed.isoformat() if observed is not None else None,
        "age_seconds": age_seconds,
        "relation": relation,
        "freshness": freshness,
        "state": state,
    }


def build_snapshot(
    *,
    version: str,
    head_sha: str,
    release: dict[str, Any],
    runs_payload: dict[str, Any] | list[dict[str, Any]],
    current_ci: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now must have timezone information")
    now = now.astimezone(timezone.utc)

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

    payloads = runs_payload if isinstance(runs_payload, list) else [runs_payload]
    runs = [
        run
        for payload in payloads
        if isinstance(payload, dict)
        for run in payload.get("workflow_runs", [])
        if isinstance(run, dict)
    ]
    workflow_evidence: dict[str, Any] = {}
    for name in CRITICAL_WORKFLOWS:
        if name == "workspace-ci" and current_ci is not None:
            run = current_ci
        else:
            run = _latest_completed_run(runs, name)
        workflow_evidence[name] = _assess_run(run, head_sha=head_sha, now=now)

    current_ci_evidence = workflow_evidence["workspace-ci"]
    current_ci_ok = (
        isinstance(current_ci_evidence, dict)
        and current_ci_evidence["state"] == "current"
        and current_ci_evidence.get("event") == "push"
    )

    release_alignment = (
        release.get("tag_name") == expected_tag
        and isinstance(release.get("target_commitish"), str)
        and len(release["target_commitish"]) == 40
        and "hello-github.pyz" in assets
        and isinstance(assets["hello-github.pyz"].get("digest"), str)
        and assets["hello-github.pyz"]["digest"].startswith("sha256:")
    )
    all_evidence_acceptable = all(
        evidence is not None and evidence["state"] in {"current", "historical"}
        for evidence in workflow_evidence.values()
    )
    healthy = release_alignment and current_ci_ok and all_evidence_acceptable

    degraded_reasons = []
    if not release_alignment:
        degraded_reasons.append("release_alignment")
    if not current_ci_ok:
        degraded_reasons.append("current_main_ci")
    for name, evidence in workflow_evidence.items():
        if evidence is None or evidence["state"] in {"unknown", "failed", "stale"}:
            reason = evidence["state"] if evidence is not None else "unknown"
            degraded_reasons.append(f"workflow:{name}:{reason}")

    return {
        "schema": "hello-github-project-health/v1",
        "status": "healthy" if healthy else "degraded",
        "snapshot_kind": "main_ci_success",
        "generated_at": now.isoformat(),
        "head_sha": head_sha,
        "version": version,
        "evidence_policy": {
            "max_age_days": MAX_EVIDENCE_AGE_DAYS,
            "historical_success_is_current_proof": False,
        },
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
            "required_evidence_fresh": all_evidence_acceptable,
        },
        "workflow_evidence": workflow_evidence,
        "degraded_reasons": degraded_reasons,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build project health snapshot.")
    parser.add_argument("--version-file", type=Path, required=True)
    parser.add_argument("--release-json", type=Path, required=True)
    parser.add_argument("--runs-json", type=Path, required=True)
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--current-ci-run-id", type=int, required=True)
    parser.add_argument("--current-ci-run-number", type=int, required=True)
    parser.add_argument("--current-ci-event", required=True)
    parser.add_argument("--current-ci-conclusion", required=True)
    parser.add_argument("--current-ci-updated-at", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    snapshot = build_snapshot(
        version=args.version_file.read_text(encoding="utf-8").strip(),
        head_sha=args.head_sha,
        release=json.loads(args.release_json.read_text(encoding="utf-8")),
        runs_payload=json.loads(args.runs_json.read_text(encoding="utf-8")),
        current_ci={
            "id": args.current_ci_run_id,
            "run_number": args.current_ci_run_number,
            "event": args.current_ci_event,
            "head_sha": args.head_sha,
            "conclusion": args.current_ci_conclusion,
            "updated_at": args.current_ci_updated_at,
        },
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
