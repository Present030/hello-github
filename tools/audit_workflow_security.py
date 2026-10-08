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
    "project-health.yml": {"actions": "read", "contents": "read"},
    "release-integrity.yml": {"contents": "read"},
    "permission-probe.yml": {"contents": "read", "issues": "write"},
    "cold-start-audit.yml": {"contents": "read"},
    "pages.yml": {
        "actions": "read",
        "contents": "read",
        "pages": "write",
        "id-token": "write",
    },
    "formal-release-attestation.yml": {"contents": "read"},
    "attestation-probe.yml": {
        "attestations": "write",
        "contents": "read",
        "id-token": "write",
    },
}

# Only these jobs may override their workflow-level GITHUB_TOKEN permissions.
# All other jobs must inherit the explicitly audited workflow-level permissions.
EXPECTED_JOB_PERMISSIONS: dict[str, dict[str, dict[str, str]]] = {
    "release.yml": {
        "attest": {
            "attestations": "write",
            "contents": "read",
            "id-token": "write",
        },
        "verify-provenance": {"contents": "read"},
    },
    "formal-release-attestation.yml": {
        "sign-published": {
            "attestations": "write",
            "contents": "read",
            "id-token": "write",
        },
        "independent-verify": {"contents": "read"},
    },
    "cold-start-audit.yml": {
        "site-cold-start": {"contents": "read", "pages": "read"},
    },
    "pages.yml": {
        "release-ready": {"actions": "read", "contents": "read"},
    },
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



def _job_permission_overrides(
    text: str,
) -> list[tuple[str, dict[str, str] | None]]:
    """Read block-style job permissions; reject unsupported/dynamic forms.

    The repository uses literal, two-space-indented job identifiers and
    four-space-indented job fields. A None mapping marks an unsafe or
    unparseable declaration rather than accepting a permissive default.
    """
    lines = text.splitlines()
    overrides: list[tuple[str, dict[str, str] | None]] = []
    in_jobs = False
    job: str | None = None

    for index, line in enumerate(lines):
        if line == "jobs:":
            in_jobs = True
            job = None
            continue
        if not in_jobs:
            continue
        if line.strip() and not line.startswith((" ", "#")):
            in_jobs = False
            job = None
            continue

        job_match = re.fullmatch(r"  ([A-Za-z0-9_-]+):\s*(?:#.*)?", line)
        if job_match:
            job = job_match.group(1)
            continue
        if re.match(r"^  \S", line) and not line.lstrip().startswith("#"):
            # Inline/aliased job definitions cannot be inspected safely.
            overrides.append(("<unsupported-job-declaration>", None))
            job = None
            continue

        if not re.match(r"^    permissions\s*:", line):
            continue

        if job is None or line != "    permissions:":
            overrides.append((job or "<unknown>", None))
            continue

        mapping: dict[str, str] = {}
        valid = True
        for child in lines[index + 1 :]:
            if not child.strip() or child.lstrip().startswith("#"):
                continue
            indentation = len(child) - len(child.lstrip(" "))
            if indentation <= 4:
                break
            match = re.fullmatch(
                r"      ([A-Za-z0-9-]+): (read|write|none)(?:\s+#.*)?",
                child,
            )
            if match is None or match.group(1) in mapping:
                valid = False
                break
            mapping[match.group(1)] = match.group(2)

        overrides.append((job, mapping if valid else None))

    return overrides


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
    expected_job_permissions: dict[str, dict[str, str]] | None = None,
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

    permitted_overrides = expected_job_permissions or {}
    observed_overrides: set[str] = set()
    for job, actual in _job_permission_overrides(text):
        if job in observed_overrides:
            errors.append(f"{relative}: duplicate job-level permissions for {job}")
        observed_overrides.add(job)

        expected = permitted_overrides.get(job)
        if expected is None:
            errors.append(
                f"{relative}: unauthorized job-level permissions override in {job}"
            )
        elif actual != expected:
            errors.append(
                f"{relative}: job {job} permissions {actual!r} != policy "
                f"{expected!r}"
            )

    for job in permitted_overrides.keys() - observed_overrides:
        errors.append(f"{relative}: required job-level permissions missing for {job}")

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

    if re.search(r"(?m)^\s{2}workflow_run:\s*$", text):
        if path.name == "pages.yml":
            # Pages consumes trusted project-health outcomes (including failed
            # main CI), never a generic PR or user-selected workflow artifact.
            required_guards = (
                'workflows: ["project-health", "release"]',
                "github.event.workflow_run.name == 'project-health'",
                "github.event.workflow_run.event == 'workflow_run'",
                "github.event.workflow_run.name == 'release'",
                "github.event.workflow_run.event == 'push'",
                "github.event.workflow_run.conclusion == 'success'",
                "github.event.workflow_run.head_branch == 'main'",
                "needs.release-ready.outputs.ready == 'true'",
                "tools/check_release_readiness.py",
            )
        else:
            required_guards = (
                "github.event.workflow_run.event == 'push'",
                "github.event.workflow_run.head_branch == 'main'",
                "github.event.workflow_run.conclusion == 'success'",
            )
        for guard in required_guards:
            if guard not in text:
                errors.append(f"{relative}: workflow_run lacks required guard: {guard}")

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
                expected_job_permissions=EXPECTED_JOB_PERMISSIONS.get(name, {}),
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
        "PASS: workflow and job permissions, Issue gates, shell interpolation, "
        "triggers, and official Action pins satisfy policy"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
