"""Runtime report helpers."""

from __future__ import annotations

import platform

from . import __version__

MESSAGE = "Hello from a persistent GitHub workspace!"


def build_report() -> dict[str, str]:
    """Return a small, non-sensitive runtime fingerprint."""
    return {
        "message": MESSAGE,
        "version": __version__,
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "system": platform.system(),
        "machine": platform.machine(),
    }
