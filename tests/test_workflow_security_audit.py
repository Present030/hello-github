from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

import tools.audit_workflow_security as security


PIN = "a" * 40


def write_workflow(root: Path, name: str, content: str) -> Path:
    path = root / ".github" / "workflows" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


class WorkflowSecurityAuditTests(unittest.TestCase):
    def audit(
        self,
        content: str,
        *,
        permissions: dict[str, str] | None = None,
    ) -> list[str]:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = write_workflow(root, "test.yml", content)
            return security.audit_workflow(
                path,
                expected_permissions=permissions or {"contents": "read"},
                root=root,
            )

    def test_accepts_pinned_action_and_minimal_permissions(self) -> None:
        findings = self.audit(
            f"""name: safe
on:
  push:
permissions:
  contents: read
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@{PIN}
      - run: echo safe
"""
        )
        self.assertEqual(findings, [])

    def test_rejects_direct_issue_body_in_shell(self) -> None:
        findings = self.audit(
            f"""name: unsafe
on:
  push:
permissions:
  contents: read
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@{PIN}
      - run: echo "${{{{ github.event.issue.body }}}}"
"""
        )
        self.assertTrue(any("Issue body" in item for item in findings))
        self.assertTrue(any("directly inside run" in item for item in findings))

    def test_rejects_mutable_official_action_ref(self) -> None:
        findings = self.audit(
            """name: unsafe
on:
  push:
permissions:
  contents: read
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
"""
        )
        self.assertTrue(any("unpinned official Action" in item for item in findings))

    def test_rejects_pull_request_target(self) -> None:
        findings = self.audit(
            """name: unsafe
on:
  pull_request_target:
permissions:
  contents: read
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: echo unsafe
"""
        )
        self.assertTrue(any("banned trigger pull_request_target" in item for item in findings))

    def test_rejects_missing_or_excess_permissions(self) -> None:
        missing = self.audit(
            """name: unsafe
on:
  push:
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: echo unsafe
"""
        )
        self.assertTrue(any("missing explicit top-level permissions" in item for item in missing))

        excess = self.audit(
            """name: unsafe
on:
  push:
permissions:
  contents: write
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: echo unsafe
"""
        )
        self.assertTrue(any("permissions" in item and "!= policy" in item for item in excess))

    def test_issue_trigger_requires_owner_and_title_gates(self) -> None:
        findings = self.audit(
            """name: unsafe
on:
  issues:
    types: [opened]
permissions:
  contents: read
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: echo unsafe
"""
        )
        self.assertTrue(any("repository-owner gate" in item for item in findings))
        self.assertTrue(any("exact-title gate" in item for item in findings))


if __name__ == "__main__":
    unittest.main()
