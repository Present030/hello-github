"""Audit repository content for secrets and likely private information.

High-confidence secret findings are blocking. Privacy indicators are advisory.
Matched values are never printed.
"""

from __future__ import annotations

import argparse
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
MAX_TEXT_BYTES = 2 * 1024 * 1024

SAFE_EMAIL_DOMAINS = {
    "example.com",
    "example.org",
    "example.net",
    "users.noreply.github.com",
}

SAFE_HOME_NAMES = {
    "runner",
    "oai",
    "root",
}

BLOCK_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "private-key",
        re.compile(
            r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"
        ),
    ),
    (
        "github-token",
        re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    ),
    (
        "github-fine-grained-token",
        re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    ),
    (
        "aws-access-key",
        re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    ),
    (
        "google-api-key",
        re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
    ),
    (
        "stripe-live-secret",
        re.compile(r"\bsk_live_[0-9A-Za-z]{16,}\b"),
    ),
    (
        "slack-token",
        re.compile(r"\bxox[baprs]-[0-9A-Za-z-]{10,}\b"),
    ),
    (
        "openai-api-key",
        re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"),
    ),
    (
        "credential-in-url",
        re.compile(
            r"\b[a-zA-Z][a-zA-Z0-9+.-]*://"
            r"[^/\s:@]+:[^@\s/]+@"
        ),
    ),
)

EMAIL_RE = re.compile(
    r"\b[A-Za-z0-9.!#$%&'*+/=?^_\x60{|}~-]+@"
    r"([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)\b"
)
WINDOWS_HOME_RE = re.compile(r"(?i)\b[A-Z]:\\Users\\([^\\/\r\n]+)")
POSIX_HOME_RE = re.compile(r"(?<![A-Za-z0-9_])/(?:home|Users)/([^/\s]+)")
PRIVATE_IPV4_RE = re.compile(
    r"\b(?:10(?:\.\d{1,3}){3}|"
    r"192\.168(?:\.\d{1,3}){2}|"
    r"172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2})\b"
)
SENSITIVE_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(?:password|passwd|api[_-]?key|secret|access[_-]?token|auth[_-]?token)"
    r"\b\s*[:=]\s*[\"']?([^\s\"'\$\{\}]{8,})"
)

SENSITIVE_PATH_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)(?:^|/)(?:\.env(?:\..+)?|id_(?:rsa|dsa|ecdsa|ed25519))$"),
    re.compile(r"(?i)(?:^|/)(?:credentials|secrets?)(?:\.[^/]+)?$"),
    re.compile(r"(?i)\.(?:p12|pfx|key)$"),
)


@dataclass(frozen=True)
class Finding:
    severity: str
    rule: str
    location: str


def _decode_text(data: bytes) -> str | None:
    if len(data) > MAX_TEXT_BYTES or b"\x00" in data:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def scan_text(text: str, location: str) -> list[Finding]:
    findings: list[Finding] = []
    lines = text.splitlines()

    for line_number, line in enumerate(lines, start=1):
        line_location = f"{location}:{line_number}"

        for rule, pattern in BLOCK_PATTERNS:
            if pattern.search(line):
                findings.append(Finding("BLOCK", rule, line_location))

        for match in EMAIL_RE.finditer(line):
            if match.group(1).lower() not in SAFE_EMAIL_DOMAINS:
                findings.append(Finding("ADVISORY", "email-address", line_location))
                break

        windows_match = WINDOWS_HOME_RE.search(line)
        if windows_match and windows_match.group(1).lower() not in SAFE_HOME_NAMES:
            findings.append(Finding("ADVISORY", "local-user-path", line_location))

        posix_match = POSIX_HOME_RE.search(line)
        if posix_match and posix_match.group(1).lower() not in SAFE_HOME_NAMES:
            findings.append(Finding("ADVISORY", "local-user-path", line_location))

        if PRIVATE_IPV4_RE.search(line):
            findings.append(Finding("ADVISORY", "private-ip-address", line_location))

        if SENSITIVE_ASSIGNMENT_RE.search(line):
            findings.append(
                Finding("ADVISORY", "credential-shaped-assignment", line_location)
            )

    return findings


def scan_path(path: str, data: bytes, *, location_prefix: str = "") -> list[Finding]:
    location = f"{location_prefix}{path}"
    findings: list[Finding] = []

    if any(pattern.search(path) for pattern in SENSITIVE_PATH_PATTERNS):
        findings.append(Finding("ADVISORY", "sensitive-filename", location))

    text = _decode_text(data)
    if text is not None:
        findings.extend(scan_text(text, location))
    return findings


def tracked_files(root: Path = ROOT) -> Iterable[tuple[str, bytes]]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        check=True,
        stdout=subprocess.PIPE,
    )
    for raw_path in result.stdout.split(b"\x00"):
        if not raw_path:
            continue
        path = raw_path.decode("utf-8", errors="surrogateescape")
        yield path, (root / path).read_bytes()


def history_blobs(root: Path = ROOT) -> Iterable[tuple[str, bytes]]:
    result = subprocess.run(
        ["git", "rev-list", "--objects", "--all"],
        cwd=root,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    seen: set[str] = set()
    for line in result.stdout.splitlines():
        object_id, _, path = line.partition(" ")
        if not path or object_id in seen:
            continue
        seen.add(object_id)

        object_type = subprocess.run(
            ["git", "cat-file", "-t", object_id],
            cwd=root,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        ).stdout.strip()
        if object_type != "blob":
            continue

        size = int(
            subprocess.run(
                ["git", "cat-file", "-s", object_id],
                cwd=root,
                check=True,
                text=True,
                stdout=subprocess.PIPE,
            ).stdout.strip()
        )
        if size > MAX_TEXT_BYTES:
            continue

        data = subprocess.run(
            ["git", "cat-file", "blob", object_id],
            cwd=root,
            check=True,
            stdout=subprocess.PIPE,
        ).stdout
        yield f"{object_id[:12]}:{path}", data


def commit_metadata_findings(root: Path = ROOT) -> list[Finding]:
    result = subprocess.run(
        [
            "git",
            "log",
            "--all",
            "--format=%H%x00%ae%x00%ce",
        ],
        cwd=root,
        check=True,
        stdout=subprocess.PIPE,
    )
    findings: list[Finding] = []
    for raw_line in result.stdout.splitlines():
        parts = raw_line.decode("utf-8", errors="replace").split("\x00")
        if len(parts) != 3:
            continue
        commit, author_email, committer_email = parts
        for role, email in (("author", author_email), ("committer", committer_email)):
            domain = email.rsplit("@", 1)[-1].lower() if "@" in email else ""
            if email and domain not in SAFE_EMAIL_DOMAINS:
                findings.append(
                    Finding(
                        "ADVISORY",
                        f"commit-{role}-email",
                        f"commit:{commit[:12]}",
                    )
                )
    return findings


def deduplicate(findings: Iterable[Finding]) -> list[Finding]:
    return sorted(
        set(findings),
        key=lambda item: (item.severity, item.rule, item.location),
    )


def run_audit(*, history: bool, root: Path = ROOT) -> list[Finding]:
    findings: list[Finding] = []

    if history:
        for location, data in history_blobs(root):
            findings.extend(
                scan_path(location, data, location_prefix="history:")
            )
        findings.extend(commit_metadata_findings(root))
    else:
        for path, data in tracked_files(root):
            findings.extend(scan_path(path, data))

    return deduplicate(findings)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--history",
        action="store_true",
        help="scan all reachable Git blobs and commit email metadata",
    )
    parser.add_argument(
        "--fail-on-advisory",
        action="store_true",
        help="also fail for privacy advisories",
    )
    args = parser.parse_args()

    findings = run_audit(history=args.history)
    blockers = [item for item in findings if item.severity == "BLOCK"]
    advisories = [item for item in findings if item.severity == "ADVISORY"]

    for item in findings:
        print(f"{item.severity}: {item.rule} at {item.location}")

    print(
        f"Exposure audit summary: blockers={len(blockers)} "
        f"advisories={len(advisories)} history={args.history}"
    )

    if blockers:
        print("FAIL: high-confidence secret material detected; matched values are hidden.")
        return 1
    if advisories and args.fail_on_advisory:
        print("FAIL: privacy advisories detected; matched values are hidden.")
        return 2

    print("PASS: no high-confidence secret material detected.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
