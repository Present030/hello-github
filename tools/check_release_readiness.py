"""Fail-closed Pages readiness gate for a fully verified formal Release.

A VERSION push may run concurrently with the release workflow. Pages must
never publish links to a tag/assets before the corresponding release run has
completed and verified them. A pending result is not a workflow failure.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Any

SHA = re.compile(r"[0-9a-f]{40}\Z")
DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+\Z")
REQUIRED_ASSETS = frozenset({
    "hello-github.pyz",
    "hello-github.cdx.json",
    "hello-github-recovery.zip",
    "release-manifest.txt",
    "runtime-report.json",
})


def _runs(payload: object) -> list[dict[str, Any]]:
    batches = payload if isinstance(payload, list) else [payload]
    return [
        run
        for batch in batches
        if isinstance(batch, dict)
        for run in batch.get("workflow_runs", [])
        if isinstance(run, dict)
    ]


def assess_release_readiness(
    *,
    version: str,
    release: object,
    runs_payload: object,
) -> dict[str, Any]:
    if not VERSION.fullmatch(version):
        raise ValueError("VERSION must be a semantic version triplet")
    tag = "v" + version
    answer: dict[str, Any] = {
        "ready": False,
        "tag": tag,
        "reason": "release_missing",
        "verified_release_run_id": None,
    }

    if not isinstance(release, dict):
        return answer
    if release.get("tag_name") != tag:
        answer["reason"] = "release_version_mismatch"
        return answer
    if release.get("draft") is not False or release.get("prerelease") is not False:
        answer["reason"] = "release_not_published"
        return answer
    target = release.get("target_commitish")
    if not isinstance(target, str) or not SHA.fullmatch(target):
        answer["reason"] = "release_target_invalid"
        return answer

    raw_assets = release.get("assets")
    if not isinstance(raw_assets, list):
        answer["reason"] = "release_assets_incomplete"
        return answer
    assets: dict[str, dict[str, Any]] = {}
    for asset in raw_assets:
        if not isinstance(asset, dict):
            continue
        name = asset.get("name")
        if not isinstance(name, str) or name in assets:
            answer["reason"] = "release_assets_invalid"
            return answer
        assets[name] = asset
    if not REQUIRED_ASSETS.issubset(assets):
        answer["reason"] = "release_assets_incomplete"
        return answer
    for name in REQUIRED_ASSETS:
        asset = assets[name]
        size, digest = asset.get("size"), asset.get("digest")
        if (
            asset.get("state") != "uploaded"
            or type(size) is not int or size <= 0
            or not isinstance(digest, str) or not DIGEST.fullmatch(digest)
        ):
            answer["reason"] = "release_assets_invalid"
            return answer

    successful_runs = [
        run
        for run in _runs(runs_payload)
        if run.get("name") == "release"
        and run.get("head_sha") == target
        and run.get("status") == "completed"
        and run.get("conclusion") == "success"
        and run.get("event") in {"push", "workflow_dispatch"}
        and type(run.get("id")) is int and run["id"] > 0
    ]
    if not successful_runs:
        answer["reason"] = "release_verification_pending"
        return answer

    successful = max(successful_runs, key=lambda run: run["id"])
    answer.update(
        ready=True,
        reason="verified",
        verified_release_run_id=successful["id"],
    )
    return answer


def _load(path: Path | None) -> object:
    if path is None:
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Release readiness for Pages")
    parser.add_argument("--version-file", type=Path, default=Path("VERSION"))
    parser.add_argument("--release-json", type=Path)
    parser.add_argument("--runs-json", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    result = assess_release_readiness(
        version=args.version_file.read_text(encoding="utf-8").strip(),
        release=_load(args.release_json),
        runs_payload=_load(args.runs_json),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(
        "RELEASE_READY=" + str(result["ready"]).lower()
        + " tag=" + result["tag"] + " reason=" + result["reason"]
        + " verified_run=" + str(result["verified_release_run_id"])
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
