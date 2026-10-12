"""Render the static website from repository-owned state."""

from __future__ import annotations

import argparse
from pathlib import Path

VERSION_TOKEN = "{{VERSION}}"


def read_version(path: Path) -> str:
    version = path.read_text(encoding="utf-8").strip()
    parts = version.split(".")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        raise ValueError(f"VERSION must be semantic version X.Y.Z; got: {version!r}")
    return version


def render(template: str, version: str) -> str:
    if VERSION_TOKEN not in template:
        raise ValueError(f"template is missing {VERSION_TOKEN}")
    rendered = template.replace(VERSION_TOKEN, version)
    if VERSION_TOKEN in rendered:
        raise ValueError("version token remained after rendering")
    return rendered


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--template", type=Path, default=Path("site/index.html"))
    parser.add_argument("--version-file", type=Path, default=Path("VERSION"))
    parser.add_argument("--output", type=Path, default=Path("dist/site/index.html"))
    args = parser.parse_args()

    version = read_version(args.version_file)
    template = args.template.read_text(encoding="utf-8")
    rendered = render(template, version)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8", newline="\n")
    print(f"Rendered {args.output} for v{version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
