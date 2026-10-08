"""Check exact published formal Release subjects before signing or verification.

The GitHub Release objects are not automatically trustworthy. Require exact
filenames, uploaded metadata, SHA256 on actual downloaded bytes, and a tag
target matching the manifest. No Release writes and no certificate handling.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from typing import Any

REQUIRED_ASSETS = frozenset({
    "hello-github.pyz",
    "hello-github.cdx.json",
    "hello-github-recovery.zip",
    "release-manifest.txt",
    "runtime-report.json",
})
SHA = re.compile(r"[0-9a-f]{40}\Z")
DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
SEMVER = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+\Z")


def verify_release_assets(
    *,
    version: str,
    metadata: dict[str, Any],
    directory: Path,
    expected_target: str | None = None,
) -> dict[str, Any]:
    if not SEMVER.fullmatch(version):
        raise ValueError("invalid VERSION")
    if not isinstance(metadata, dict):
        raise ValueError("release metadata must be an object")
    tag = f"v{version}"
    if metadata.get("tag_name") != tag:
        raise ValueError("release tag does not match VERSION")
    if metadata.get("draft") is not False or metadata.get("prerelease") is not False:
        raise ValueError("Release is not a final published version")
    target = metadata.get("target_commitish")
    if not isinstance(target, str) or not SHA.fullmatch(target):
        raise ValueError("Release target is not a commit SHA")
    if expected_target is not None and target != expected_target:
        raise ValueError("Release target differs from expected build commit")

    actual_names = {path.name for path in directory.iterdir() if path.is_file()}
    if actual_names != REQUIRED_ASSETS:
        raise ValueError("downloaded Release asset set differs from the five formal assets")
    if not isinstance(metadata.get("assets"), list):
        raise ValueError("release assets metadata is absent")
    remote_assets: dict[str, Any] = {}
    for item in metadata["assets"]:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            raise ValueError("invalid Release asset metadata")
        name = item["name"]
        if name in remote_assets:
            raise ValueError("duplicate Release asset name")
        remote_assets[name] = item
    if set(remote_assets) != REQUIRED_ASSETS:
        raise ValueError("Release metadata asset set differs from the five formal assets")

    hashes: dict[str, str] = {}
    for name in sorted(REQUIRED_ASSETS):
        item = remote_assets[name]
        size, digest = item.get("size"), item.get("digest")
        if (
            item.get("state") != "uploaded"
            or type(size) is not int or size <= 0
            or not isinstance(digest, str) or not DIGEST.fullmatch(digest)
        ):
            raise ValueError(f"{name}: missing uploaded state, size or SHA256")
        content = (directory / name).read_bytes()
        observed = "sha256:" + hashlib.sha256(content).hexdigest()
        if len(content) != size or observed != digest:
            raise ValueError(f"{name}: downloaded bytes do not match Release metadata")
        hashes[name] = observed

    manifest = (directory / "release-manifest.txt").read_text(encoding="utf-8")
    manifest_lines = manifest.splitlines()
    for field in (f"tag={tag}", f"version={version}", f"commit={target}"):
        if manifest_lines.count(field) != 1:
            raise ValueError(f"Release manifest field mismatches: {field}")

    report = json.loads((directory / "runtime-report.json").read_text(encoding="utf-8"))
    if not isinstance(report, dict) or report.get("version") != version:
        raise ValueError("runtime report version mismatch")
    sbom = json.loads((directory / "hello-github.cdx.json").read_text(encoding="utf-8"))
    if not isinstance(sbom, dict) or sbom.get("bomFormat") != "CycloneDX":
        raise ValueError("not a CycloneDX SBOM")
    component = sbom.get("metadata", {}).get("component", {})
    if not isinstance(component, dict) or component.get("version") != version:
        raise ValueError("SBOM version mismatch")
    hashes_in_sbom = component.get("hashes")
    if not isinstance(hashes_in_sbom, list) or not any(
        isinstance(item, dict)
        and item.get("alg") == "SHA-256"
        and item.get("content") == hashes["hello-github.pyz"].removeprefix("sha256:")
        for item in hashes_in_sbom
    ):
        raise ValueError("SBOM executable SHA256 mismatch")

    return {"version": version, "tag": tag, "target": target, "digests": hashes}


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify five formal Release subjects")
    parser.add_argument("--version-file", type=Path, default=Path("VERSION"))
    parser.add_argument("--release-json", type=Path, required=True)
    parser.add_argument("--release-dir", type=Path, required=True)
    parser.add_argument("--expected-target")
    args = parser.parse_args()
    result = verify_release_assets(
        version=args.version_file.read_text(encoding="utf-8").strip(),
        metadata=json.loads(args.release_json.read_text(encoding="utf-8")),
        directory=args.release_dir,
        expected_target=args.expected_target,
    )
    print(
        f"PASS: {result['tag']} five downloaded Release subjects match "
        f"GitHub SHA256 digests, VERSION, SBOM, and manifest; target={result['target']}"
    )
    for name, digest in result["digests"].items():
        print(f"RELEASE_SUBJECT {name} {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
