"""Runtime report helpers."""

from __future__ import annotations

import platform

MESSAGE = "Hello from a persistent GitHub workspace!"


def build_report() -> dict[str, str]:
    """Return a small, non-sensitive runtime fingerprint."""
    return {
        "message": MESSAGE,
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "system": platform.system(),
        "machine": platform.machine(),
    }
