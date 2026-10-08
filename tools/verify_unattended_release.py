"""Periodic Release provenance policy and safe offline recovery verifier.

The source SHA256 checks and signer verification must run *before* invoking
this recovery verifier, because its archive includes executable Python code.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
from zipfile import ZipFile

if __package__:
    from .verify_formal_release_assets import SEMVER
else:
    from verify_formal_release_assets import SEMVER

RECOVERY_MEMBERS = frozenset({
    "CHECKSUMS.sha256",
    "RECOVERY.md",
    "recovery.json",
    "verify.py",
    "release/hello-github.pyz",
    "release/release-manifest.txt",
    "release/runtime-report.json",
    "sbom/hello-github.cdx.json",
})
COPIED_ASSETS = {
    "release/hello-github.pyz": "hello-github.pyz",
    "release/release-manifest.txt": "release-manifest.txt",
    "release/runtime-report.json": "runtime-report.json",
    "sbom/hello-github.cdx.json": "hello-github.cdx.json",
}
MAX_MEMBER_SIZE = 20 * 1024 * 1024


def expected_signer(version: str) -> str:
    """Historical 0.3.0 witness is NOT its original build provenance."""
    if not SEMVER.fullmatch(version):
        raise ValueError("VERSION must be a semantic version")
    if version == "0.3.0":
        return "formal-release-attestation.yml"
    if tuple(map(int, version.split("."))) > (0, 3, 0):
        return "release.yml"
    raise ValueError("no accepted attestation policy for pre-0.3.0 releases")


def verify_recovery(
    *,
    release_dir: Path,
    target_dir: Path,
    version: str,
    target_commit: str,
    repository: str,
) -> None:
    if not SEMVER.fullmatch(version) or not re.fullmatch(r"[0-9a-f]{40}", target_commit):
        raise ValueError("invalid version or Release target")
    bundle = release_dir / "hello-github-recovery.zip"
    with ZipFile(bundle) as archive:
        members = archive.infolist()
        names = [member.filename for member in members]
        if len(names) != len(RECOVERY_MEMBERS) or set(names) != RECOVERY_MEMBERS:
            raise ValueError("recovery bundle has missing, duplicate or extra entries")
        for member in members:
            path = PurePosixPath(member.filename)
            if (path.is_absolute() or ".." in path.parts
                or member.file_size > MAX_MEMBER_SIZE
                or (member.external_attr >> 16) & 0o170000 == 0o120000):
                raise ValueError(f"unsafe recovery bundle member: {member.filename}")
        archive.extractall(target_dir)

    recovery = json.loads((target_dir / "recovery.json").read_text(encoding="utf-8"))
    if (
        recovery.get("schema") != "hello-github-recovery-bundle/v1"
        or recovery.get("repository") != repository
        or recovery.get("version") != version
        or recovery.get("release") != {
            "tag": "v" + version,
            "target_commit": target_commit,
        }
    ):
        raise ValueError("recovery bundle identity does not match formal Release")

    for inside, outside in COPIED_ASSETS.items():
        if (target_dir / inside).read_bytes() != (release_dir / outside).read_bytes():
            raise ValueError(f"recovery bundle does not match published {outside}")

    completed = subprocess.run(
        [sys.executable, str(target_dir / "verify.py")],
        cwd=target_dir,
        capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=45, check=False,
    )
    if completed.returncode != 0 or "PASS: recovery bundle" not in completed.stdout:
        raise ValueError(
            "recovery verifier failed: " + completed.stdout[-800:] + completed.stderr[-800:]
        )
    print(completed.stdout.strip())
    print("PASS: offline recovery contains the exact published assets and runs successfully")


def main() -> int:
    parser = argparse.ArgumentParser(description="Periodic Release recovery and signer policy")
    parser.add_argument("--version-file", type=Path, default=Path("VERSION"))
    parser.add_argument("--signer-only", action="store_true")
    parser.add_argument("--release-dir", type=Path)
    parser.add_argument("--release-json", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--repository")
    args = parser.parse_args()

    version = args.version_file.read_text(encoding="utf-8").strip()
    if args.signer_only:
        print(expected_signer(version))
        return 0
    if not all((args.release_dir, args.release_json, args.output_dir, args.repository)):
        parser.error("offline recovery requires --release-dir, --release-json, --output-dir and --repository")
    release = json.loads(args.release_json.read_text(encoding="utf-8"))
    verify_recovery(
        release_dir=args.release_dir,
        target_dir=args.output_dir,
        version=version,
        target_commit=release["target_commitish"],
        repository=args.repository,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
