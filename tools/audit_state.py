"""Audit durable repository state for machine-detectable drift."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

ACTION_USE_RE = re.compile(
    r"^\s*(?:-\s*)?uses:\s*(actions/[A-Za-z0-9_.-]+)@([^\s#]+)",
    re.MULTILINE,
)
FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def _require_fragment(
    errors: list[str],
    *,
    label: str,
    content: str,
    fragment: str,
) -> None:
    if fragment not in content:
        errors.append(f"{label} is missing expected text: {fragment}")


def audit_state(root: Path, release: dict[str, Any]) -> list[str]:
    """Return human-readable drift findings; an empty list means healthy."""
    errors: list[str] = []

    version = (root / "VERSION").read_text(encoding="utf-8").strip()
    readme = (root / "README.md").read_text(encoding="utf-8")
    project_state = (root / "PROJECT_STATE.md").read_text(encoding="utf-8")
    expected_tag = f"v{version}"

    release_tag = release.get("tag_name")
    if release_tag != expected_tag:
        errors.append(
            f"latest Release tag mismatch: VERSION expects {expected_tag}, got {release_tag!r}"
        )

    assets = {
        asset.get("name"): asset
        for asset in release.get("assets", [])
        if isinstance(asset, dict)
    }
    zipapp = assets.get("hello-github.pyz")
    if zipapp is None:
        errors.append("latest Release is missing hello-github.pyz")
        digest = None
    else:
        digest_value = zipapp.get("digest")
        if not isinstance(digest_value, str) or not digest_value.startswith("sha256:"):
            errors.append(
                "hello-github.pyz is missing a GitHub sha256 digest in Release metadata"
            )
            digest = None
        else:
            digest = digest_value.removeprefix("sha256:")

    _require_fragment(
        errors,
        label="README.md",
        content=readme,
        fragment=f"Latest verified release: **{expected_tag}**.",
    )
    _require_fragment(
        errors,
        label="PROJECT_STATE.md",
        content=project_state,
        fragment=f"- Current application version: `{version}`.",
    )
    _require_fragment(
        errors,
        label="PROJECT_STATE.md",
        content=project_state,
        fragment=f"- Latest verified release: `{expected_tag}`.",
    )

    release_target = release.get("target_commitish")
    if isinstance(release_target, str) and release_target:
        _require_fragment(
            errors,
            label="PROJECT_STATE.md",
            content=project_state,
            fragment=f"- `{expected_tag}` target commit: `{release_target}`.",
        )
    else:
        errors.append("latest Release metadata has no target_commitish")

    if digest is not None:
        _require_fragment(
            errors,
            label="README.md",
            content=readme,
            fragment=f"SHA-256: {digest}",
        )
        _require_fragment(
            errors,
            label="PROJECT_STATE.md",
            content=project_state,
            fragment=f"- Executable SHA-256: `{digest}`.",
        )

    workflow_dir = root / ".github" / "workflows"
    action_uses = 0
    for workflow in sorted(
        [*workflow_dir.glob("*.yml"), *workflow_dir.glob("*.yaml")]
    ):
        content = workflow.read_text(encoding="utf-8")
        for match in ACTION_USE_RE.finditer(content):
            action_uses += 1
            action_name, ref = match.groups()
            if FULL_SHA_RE.fullmatch(ref) is None:
                relative = workflow.relative_to(root).as_posix()
                errors.append(
                    f"{relative} uses unpinned {action_name}@{ref}"
                )

    if action_uses == 0:
        errors.append("no official actions/* uses were found to audit")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit durable repository state.")
    parser.add_argument(
        "--release-json",
        type=Path,
        required=True,
        help="GitHub latest Release JSON payload",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="repository root",
    )
    args = parser.parse_args()

    release = json.loads(args.release_json.read_text(encoding="utf-8"))
    errors = audit_state(args.root.resolve(), release)
    if errors:
        print("STATE DRIFT DETECTED:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("PASS: VERSION, documentation, Release metadata, and Action pins agree")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
