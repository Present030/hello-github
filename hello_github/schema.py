"""Runtime report schema helpers."""

from __future__ import annotations

REQUIRED_REPORT_FIELDS = (
    "message",
    "version",
    "python",
    "implementation",
    "system",
    "machine",
)


def missing_report_fields(report: dict[str, str]) -> list[str]:
    """Return required fields that are absent from a runtime report."""
    return [field for field in REQUIRED_REPORT_FIELDS if field not in report]
