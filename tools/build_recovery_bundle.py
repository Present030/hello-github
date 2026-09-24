"""Build a deterministic, self-verifying disaster recovery bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

FIXED_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
REQUIRED_RELEASE_FILES = (
    "hello-github.pyz",
    "release-manifest.txt",
    "runtime-report.json",
)

VERIFY_SCRIPT = r'''"""Verify an extracted hello-github recovery bundle."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    checksums = ROOT / "CHECKSUMS.sha256"
    for raw_line in checksums.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip():
            continue
        expected, relative = raw_line.split("  ", 1)
        actual = sha256(ROOT / relative)
        if actual != expected:
            raise SystemExit(
                f"checksum mismatch for {relative}: expected {expected}, got {actual}"
            )

    metadata = json.loads((ROOT / "recovery.json").read_text(encoding="utf-8"))
    artifact = ROOT / "release" / "hello-github.pyz"
    expected_artifact = metadata["artifacts"]["release/hello-github.pyz"]["sha256"]
    actual_artifact = sha256(artifact)
    if actual_artifact != expected_artifact:
        raise SystemExit("release artifact digest disagrees with recovery.json")

    completed = subprocess.run(
        [sys.executable, str(artifact), "--version"],
        check=True,
        capture_output=True,
        text=True,
    )
    actual_version = completed.stdout.strip()
    if actual_version != metadata["version"]:
        raise SystemExit(
            f"artifact version mismatch: expected {metadata['version']}, got {actual_version}"
        )

    print(
        f"PASS: recovery bundle {metadata['release']['tag']} verified; "
        f"artifact sha256={actual_artifact}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''.encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _zip_member(archive: ZipFile, name: str, data: bytes) -> None:
    info = ZipInfo(name, FIXED_TIMESTAMP)
    info.create_system = 3
    info.compress_type = ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    archive.writestr(info, data, compress_type=ZIP_DEFLATED, compresslevel=9)


def build_recovery_bundle(
    *,
    release_dir: Path,
    sbom: Path,
    repository: str,
    tag: str,
    target_commit: str,
    output: Path,
) -> Path:
    """Build a deterministic recovery ZIP from verified Release inputs."""
    release_dir = release_dir.resolve()
    sbom = sbom.resolve()
    output = output.resolve()

    if not tag.startswith("v") or len(tag) == 1:
        raise ValueError("tag must look like v<version>")
    if len(target_commit) != 40 or any(ch not in "0123456789abcdef" for ch in target_commit):
        raise ValueError("target_commit must be a lowercase 40-character Git SHA")

    version = tag[1:]
    payload: dict[str, bytes] = {}
    for name in REQUIRED_RELEASE_FILES:
        source = release_dir / name
        if not source.is_file():
            raise FileNotFoundError(source)
        payload[f"release/{name}"] = source.read_bytes()

    if not sbom.is_file():
        raise FileNotFoundError(sbom)
    payload["sbom/hello-github.cdx.json"] = sbom.read_bytes()

    artifacts = {
        name: {
            "sha256": _sha256(data),
            "size": len(data),
        }
        for name, data in sorted(payload.items())
    }

    metadata = {
        "schema": "hello-github-recovery-bundle/v1",
        "repository": repository,
        "version": version,
        "release": {
            "tag": tag,
            "target_commit": target_commit,
        },
        "artifacts": artifacts,
        "rebuild": {
            "checkout": f"git checkout {tag}",
            "command": "python tools/build_zipapp.py --output rebuilt/hello-github.pyz",
            "expected_zipapp_sha256": artifacts["release/hello-github.pyz"]["sha256"],
        },
    }
    recovery_json = (
        json.dumps(metadata, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")

    recovery_md = f"""# hello-github disaster recovery bundle

This bundle is an offline recovery anchor for `{repository}` release `{tag}`.

## Verify this bundle first

Run:

```text
python verify.py
```

A successful verification checks every entry listed in `CHECKSUMS.sha256`, confirms the
published zipapp digest against `recovery.json`, and executes the zipapp to verify version
`{version}`.

## Rebuild from Git history

With access to the repository:

```text
git checkout {tag}
python tools/build_zipapp.py --output rebuilt/hello-github.pyz
```

The rebuilt zipapp must have SHA-256:

```text
{artifacts["release/hello-github.pyz"]["sha256"]}
```

The authoritative release target commit is:

```text
{target_commit}
```

The recovery bundle intentionally does not duplicate the Git source tree. Git history plus
this bundle are the two recovery anchors.
""".encode("utf-8")

    members = {
        **payload,
        "RECOVERY.md": recovery_md,
        "recovery.json": recovery_json,
        "verify.py": VERIFY_SCRIPT,
    }
    checksums = "".join(
        f"{_sha256(data)}  {name}\n"
        for name, data in sorted(members.items())
    ).encode("utf-8")
    members["CHECKSUMS.sha256"] = checksums

    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "w") as archive:
        for name in sorted(members):
            _zip_member(archive, name, members[name])

    return output


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the deterministic hello-github recovery bundle."
    )
    parser.add_argument("--release-dir", type=Path, required=True)
    parser.add_argument("--sbom", type=Path, required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--target-commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    output = build_recovery_bundle(
        release_dir=args.release_dir,
        sbom=args.sbom,
        repository=args.repository,
        tag=args.tag,
        target_commit=args.target_commit,
        output=args.output,
    )
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
