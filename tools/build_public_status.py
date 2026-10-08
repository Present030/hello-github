"""Publish an allowlisted, anonymous-safe status document for GitHub Pages.

This is a publication boundary: never copy arbitrary source JSON into Pages.
The browser must also check expires_at rather than trusting a static label.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
from typing import Any

SOURCE_SCHEMA = "hello-github-project-health/v1"
PUBLIC_SCHEMA = "hello-github-public-status/v1"
MAX_SNAPSHOT_AGE = timedelta(days=30)
FUTURE_TOLERANCE = timedelta(minutes=5)
SHA = re.compile(r"[0-9a-f]{40}\Z")
TAG = re.compile(r"v[0-9]+\.[0-9]+\.[0-9]+\Z")

WORKFLOWS = (
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
STATES = {"current", "historical", "stale", "unknown", "failed"}
CONCLUSIONS = {"success", "failure", "cancelled", "timed_out", "skipped", "action_required"}
KINDS = {"main_ci_success", "ci_failure"}


def timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(timezone.utc) if parsed.tzinfo else None


def clean_evidence(value: Any, *, failed_ci: bool = False) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    run_id = value.get("id")
    state = value.get("state")
    conclusion = value.get("conclusion")
    if failed_ci and state is None and isinstance(conclusion, str) and conclusion in CONCLUSIONS - {"success"}:
        state = "failed"
    observed = timestamp(value.get("observed_at"))
    head = value.get("head_sha")
    if (
        type(run_id) is not int or run_id <= 0
        or not isinstance(state, str) or state not in STATES
        or not isinstance(conclusion, str) or conclusion not in CONCLUSIONS
        or not isinstance(head, str) or not SHA.fullmatch(head)
    ):
        return None
    return {
        "run_id": run_id,
        "state": state,
        "conclusion": conclusion,
        "head_sha": head,
        "observed_at": observed.isoformat() if observed else None,
    }


def build_public_status(
    snapshot: dict[str, Any] | None,
    *,
    main_sha: str,
    source_run_id: int,
    now: datetime | None = None,
) -> dict[str, Any]:
    if not SHA.fullmatch(main_sha):
        raise ValueError("main_sha must be a full lowercase Git SHA")
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    now = now.astimezone(timezone.utc)

    # The fallback is safe to publish even when Actions history/artifact
    # downloads fail: it reports unknown rather than reusing older green data.
    public: dict[str, Any] = {
        "schema": PUBLIC_SCHEMA,
        "status": "unknown",
        "reason": "missing_snapshot",
        "published_at": now.isoformat(),
        "expires_at": None,
        "source_generated_at": None,
        "source_run_id": None,
        "head_sha": main_sha,
        "version": None,
        "release": {"tag": None, "has_sbom": None, "has_recovery_bundle": None},
        "checks": {"current_main_ci": None, "release_alignment": None},
        "workflows": {name: None for name in WORKFLOWS},
    }
    if snapshot is None:
        return public
    if not isinstance(snapshot, dict) or source_run_id <= 0:
        public["reason"] = "invalid_source"
        return public

    generated = timestamp(snapshot.get("generated_at"))
    if snapshot.get("schema") != SOURCE_SCHEMA or not isinstance(snapshot.get("snapshot_kind"), str) or snapshot["snapshot_kind"] not in KINDS:
        public["reason"] = "invalid_schema"
        return public
    if snapshot.get("head_sha") != main_sha:
        public["reason"] = "head_mismatch"
        return public
    if generated is None or generated > now + FUTURE_TOLERANCE:
        public["reason"] = "invalid_timestamp"
        return public

    public["source_generated_at"] = generated.isoformat()
    public["source_run_id"] = source_run_id
    public["expires_at"] = (generated + MAX_SNAPSHOT_AGE).isoformat()
    if now - generated > MAX_SNAPSHOT_AGE:
        public["reason"] = "expired_snapshot"
        return public

    status = snapshot.get("status")
    kind = snapshot["snapshot_kind"]
    if not isinstance(status, str) or status not in {"healthy", "degraded"}:
        public["reason"] = "invalid_status"
        return public
    if (kind == "ci_failure" and status != "degraded") or (
        kind == "main_ci_success" and status == "healthy"
        and snapshot.get("checks", {}).get("current_main_ci") is not True
    ):
        public["reason"] = "inconsistent_snapshot"
        return public

    evidence = snapshot.get("workflow_evidence")
    if not isinstance(evidence, dict):
        public["reason"] = "invalid_evidence"
        return public
    public["workflows"] = {
        name: clean_evidence(
            evidence.get(name),
            failed_ci=(kind == "ci_failure" and name == "workspace-ci"),
        )
        for name in WORKFLOWS
    }
    ci = public["workflows"]["workspace-ci"]
    if ci is None or ci["head_sha"] != main_sha or ci["conclusion"] not in CONCLUSIONS:
        public["reason"] = "invalid_ci"
        return public
    if kind == "ci_failure" and ci["conclusion"] == "success":
        public["reason"] = "inconsistent_snapshot"
        return public
    if status == "healthy" and (
        kind != "main_ci_success"
        or ci["conclusion"] != "success" or ci["state"] != "current"
        or any(
            e is None or e["state"] not in {"current", "historical"}
            for e in public["workflows"].values()
        )
    ):
        public["reason"] = "inconsistent_snapshot"
        return public

    checks = snapshot.get("checks")
    if isinstance(checks, dict):
        for key in public["checks"]:
            if type(checks.get(key)) is bool:
                public["checks"][key] = checks[key]

    version = snapshot.get("version")
    if isinstance(version, str) and TAG.fullmatch("v" + version):
        public["version"] = version
    release = snapshot.get("release")
    if isinstance(release, dict):
        tag = release.get("tag")
        assets = release.get("assets")
        if isinstance(tag, str) and TAG.fullmatch(tag) and isinstance(assets, dict):
            public["release"] = {
                "tag": tag,
                "has_sbom": "hello-github.cdx.json" in assets,
                "has_recovery_bundle": "hello-github-recovery.zip" in assets,
            }

    public["status"] = status
    public["reason"] = None
    return public


def main() -> int:
    parser = argparse.ArgumentParser(description="Render public-safe Pages health JSON")
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--main-sha", required=True)
    parser.add_argument("--source-run-id", type=int, default=0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    snapshot = None
    if args.snapshot is not None:
        try:
            snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            snapshot = None
    doc = build_public_status(
        snapshot,
        main_sha=args.main_sha,
        source_run_id=args.source_run_id,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(doc, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
        encoding="utf-8", newline="\n",
    )
    print(f"PUBLIC_STATUS={doc['status']} reason={doc['reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
