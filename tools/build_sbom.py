"""Generate a deterministic CycloneDX SBOM for a hello-github artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def build_sbom(*, artifact: Path, version: str) -> dict[str, object]:
    """Return a deterministic CycloneDX 1.6 SBOM for *artifact*."""
    version = version.strip()
    if not version:
        raise ValueError("version must not be empty")

    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    purl = f"pkg:generic/hello-github@{version}"

    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "version": 1,
        "metadata": {
            "component": {
                "type": "application",
                "bom-ref": purl,
                "name": "hello-github",
                "version": version,
                "purl": purl,
                "hashes": [
                    {
                        "alg": "SHA-256",
                        "content": digest,
                    }
                ],
                "properties": [
                    {
                        "name": "hello-github:runtime-dependencies",
                        "value": "python-standard-library-only",
                    }
                ],
            }
        },
        "components": [],
    }


def write_sbom(*, artifact: Path, version: str, output: Path) -> Path:
    """Write the deterministic SBOM and return its path."""
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    document = build_sbom(artifact=artifact.resolve(), version=version)
    output.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return output


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate a deterministic CycloneDX SBOM for hello-github."
    )
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    output = write_sbom(
        artifact=args.artifact,
        version=args.version,
        output=args.output,
    )
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
