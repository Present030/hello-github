"""Resolve the application version from one authoritative source."""

from __future__ import annotations

from pathlib import Path


def get_version() -> str:
    """Return the build-injected version or the source-tree VERSION."""
    try:
        from ._build_version import VERSION
    except ImportError:
        version_file = Path(__file__).resolve().parents[1] / "VERSION"
        if not version_file.is_file():
            raise RuntimeError("VERSION is unavailable outside the source tree or a built artifact")
        version = version_file.read_text(encoding="utf-8").strip()
    else:
        version = VERSION.strip()

    if not version:
        raise RuntimeError("VERSION must not be empty")
    return version
