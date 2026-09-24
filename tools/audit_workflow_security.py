"""Static security policy checks for GitHub Actions workflows."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = ROOT / ".github" / "workflows"

FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
ACTION_USE_RE = re.compile(
    r"^\s*(?:-\s*)?uses:\s*(actions/[A-Za-z0-9_.-]+)@([^\s#]+)",
    re.MULTILINE,
)
DIRECT_SHELL_CONTEXT_RE = re.compile(
    r"\$\{\{\s*(?:github\.event\.|github\.head_ref\b|github\.base_ref\b|secrets\.)"
)

EXPECTED_PERMISSIONS: dict[str, dict[str, str]] = {
    "ci.yml": {"contents": "read"},
    "release.yml": {"contents": "write"},
    "issue-worker.yml": {"contents": "read", "issues": "write"},
    "cache-probe.yml": {
        "actions": "write",
        "contents": "read",
        "issues": "write",
    },
    "health-check.yml": {"contents": "read", "issues": "write"},
    "recovery-probe.yml": {"contents": "read"},
    "sbom-probe.yml": {"contents": "read"},
    "recovery-bundle.yml": {"contents": "read"},
    "recovery-portability.yml": {"contents": "read"},
}

BANNED_TRIGGERS = ("pull_request_target",)


def _top_level_permissions(text: str) -> dict[str, str] | None:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line == "permissions:":
            permissions: dict[str, str] = {}
            for child in lines[index + 1 :]:
                if not child.strip():
                    continue
                if not child.startswith("  "):
                    break
                match = re.fullmatch(
                    r"  ([A-Za-z0-9-]+):\s*(read|write|none)\s*",
                    child,
                )
                if match is None:
                    return {}
                key, value = match.groups()
                permissions[key] = value
            return permissions
        if line.startswith("permissions:"):
            return {}
    return None


def _run_blocks(text: str) -> list[str]:
    lines = text.splitlines()
    blocks: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        match = re.match(r"^(\s*)(?:-\s+)?run:\s*(.*)$", line)
        if match is None:
            index += 1
            continue

        indent = len(match.group(1))
        value = match.group(2)
        if value not in ("|", ">", "|-", ">-"):
            blocks.append(value)
            index += 1
            continue

        index += 1
        block_lines: list[str] = []
        while index < len(lines):
            candidate = lines[index]
            if candidate.strip():
                candidate_indent = len(candidate) - len(candidate.lstrip())
                if candidate_indent <= indent:
                    break
            block_lines.append(candidate)
            index += 1
        blocks.append("\n".join(block_lines))
    return blocks


def audit_workflow(
    path: Path,
    *,
    expected_permissions: dict[str, str],
    root: Path = ROOT,
) -> list[str]:
    text = path.read_text(encoding="utf-8")
    relative = path.relative_to(root).as_posix()
    errors: list[str] = []

    for trigger in BANNED_TRIGGERS:
        if re.search(rf"(?m)^\s*{re.escape(trigger)}\s*:", text):
            errors.append(f"{relative}: banned trigger {trigger}")

    actual_permissions = _top_level_permissions(text)
    if actual_permissions is None:
        errors.append(f"{relative}: missing explicit top-level permissions")
    elif actual_permissions != expected_permissions:
        errors.append(
            f"{relative}: permissions {actual_permissions!r} != policy "
            f"{expected_permissions!r}"
        )

    for action_name, ref in ACTION_USE_RE.findall(text):
        if FULL_SHA_RE.fullmatch(ref) is None:
            errors.append(f"{relative}: unpinned official Action {action_name}@{ref}")

    if re.search(r"\$\{\{\s*github\.event\.issue\.body\b", text):
        errors.append(f"{relative}: Issue body must never enter workflow expressions")

    for block in _run_blocks(text):
        match = DIRECT_SHELL_CONTEXT_RE.search(block)
        if match is not None:
            errors.append(
                f"{relative}: untrusted/sensitive expression is interpolated directly "
                f"inside run: {match.group(0)}"
            )

    if re.search(r"(?m)^\s{2}issues:\s*$", text):
        if "github.actor == github.repository_owner" not in text:
            errors.append(f"{relative}: Issue trigger lacks repository-owner gate")
        if "github.event.issue.title" not in text:
            errors.append(f"{relative}: Issue trigger lacks exact-title gate")

    return errors


def audit_repository(root: Path = ROOT) -> list[str]:
    workflow_dir = root / ".github" / "workflows"
    errors: list[str] = []
    seen: set[str] = set()

    for path in sorted([*workflow_dir.glob("*.yml"), *workflow_dir.glob("*.yaml")]):
        name = path.name
        seen.add(name)
        expected = EXPECTED_PERMISSIONS.get(name)
        if expected is None:
            errors.append(
                f"{path.relative_to(root).as_posix()}: no security permission policy entry"
            )
            continue

        errors.extend(
            audit_workflow(
                path,
                expected_permissions=expected,
                root=root,
            )
        )

    missing = sorted(set(EXPECTED_PERMISSIONS) - seen)
    for name in missing:
        errors.append(f".github/workflows/{name}: policy entry has no workflow file")

    return errors


def main() -> int:
    errors = audit_repository()
    if errors:
        print("WORKFLOW SECURITY AUDIT FAILED:")
        for error in errors:
            print(f"- {error}")
        return 1

    print(
        "PASS: workflow permissions, Issue gates, shell interpolation, "
        "triggers, and official Action pins satisfy policy"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
