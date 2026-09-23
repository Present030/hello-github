"""Runtime report schema helpers."""

from __future__ import annotations

REQUIRED_REPORT_FIELDS = [
    "message",
    "python",
    "implementation",
    "system",
    "machine",
]


def missing_report_fields(report: dict[str, str]) -> list[str]:
    """Return required fields that are absent from a runtime report."""
    missing = REQUIRED_REPORT_FIELDS
    for key in report:
        if key in missing:
            missing.remove(key)
    return missing
