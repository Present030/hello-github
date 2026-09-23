"""Build a deterministic, dependency-free Python zipapp."""

from __future__ import annotations

import argparse
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = ROOT / "hello_github"
VERSION_FILE = ROOT / "VERSION"
FIXED_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
ENTRYPOINT = (
    "from hello_github.__main__ import main\n"
    "raise SystemExit(main())\n"
).encode("utf-8")


def _write_member(archive: ZipFile, name: str, data: bytes) -> None:
    info = ZipInfo(name, FIXED_TIMESTAMP)
    info.create_system = 3
    info.compress_type = ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    archive.writestr(info, data, compress_type=ZIP_DEFLATED, compresslevel=9)


def _read_version() -> str:
    version = VERSION_FILE.read_text(encoding="utf-8").strip()
    if not version:
        raise RuntimeError("VERSION must not be empty")
    return version


def _read_normalized_source(source: Path) -> bytes:
    with source.open("r", encoding="utf-8", newline=None) as stream:
        return stream.read().encode("utf-8")


def build_zipapp(output: Path) -> Path:
    """Build the zipapp at *output* with stable ordering and metadata."""
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    members: dict[str, bytes] = {
        "__main__.py": ENTRYPOINT,
        "hello_github/_build_version.py": f"VERSION = {_read_version()!r}\n".encode("utf-8"),
    }
    for source in sorted(PACKAGE_ROOT.rglob("*.py")):
        relative = source.relative_to(ROOT).as_posix()
        if relative.endswith("/_build_version.py"):
            continue
        members[relative] = _read_normalized_source(source)

    with ZipFile(output, "w") as archive:
        for name in sorted(members):
            _write_member(archive, name, members[name])

    return output


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the deterministic hello-github zipapp.")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "dist" / "hello-github.pyz",
        help="output .pyz path",
    )
    args = parser.parse_args()
    output = build_zipapp(args.output)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
