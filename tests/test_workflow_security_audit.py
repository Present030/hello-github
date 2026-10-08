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
        job_permissions: dict[str, dict[str, str]] | None = None,
    ) -> list[str]:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = write_workflow(root, "test.yml", content)
            return security.audit_workflow(
                path,
                expected_permissions=permissions or {"contents": "read"},
                expected_job_permissions=job_permissions or {},
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

    def test_pages_requires_both_trusted_triggers_and_release_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = """name: Deploy website to GitHub Pages
on:
  workflow_run:
    workflows: ["project-health", "release"]
    types: [completed]
permissions:
  actions: read
  contents: read
  pages: write
  id-token: write
jobs:
  release-ready:
    if: ${{ github.event.workflow_run.name == 'project-health' && github.event.workflow_run.event == 'workflow_run' && github.event.workflow_run.head_branch == 'main' || github.event.workflow_run.name == 'release' && github.event.workflow_run.event == 'push' && github.event.workflow_run.conclusion == 'success' }}
    permissions:
      actions: read
      contents: read
    steps:
      - run: echo safe
  deploy:
    needs: release-ready
    if: ${{ needs.release-ready.outputs.ready == 'true' }}
    runs-on: ubuntu-latest
    steps:
      - run: python tools/check_release_readiness.py
"""
            path = write_workflow(root, "pages.yml", payload)
            permissions = {
                "actions": "read", "contents": "read",
                "pages": "write", "id-token": "write",
            }
            job_permissions = {
                "release-ready": {"actions": "read", "contents": "read"},
            }
            self.assertEqual(
                security.audit_workflow(
                    path, expected_permissions=permissions,
                    expected_job_permissions=job_permissions, root=root,
                ),
                [],
            )
            for name, unsafe in (
                ("missing main gate", payload.replace(
                    "github.event.workflow_run.head_branch == 'main'",
                    "github.event.workflow_run.head_branch != 'main'",
                )),
                ("missing Release success", payload.replace(
                    "github.event.workflow_run.conclusion == 'success'",
                    "github.event.workflow_run.conclusion != 'success'",
                )),
                ("missing readiness check", payload.replace(
                    "needs.release-ready.outputs.ready == 'true'",
                    "needs.release-ready.outputs.ready != 'true'",
                )),
                ("elevated readiness token", payload.replace(
                    "    permissions:\n      actions: read\n      contents: read",
                    "    permissions:\n      actions: write\n      contents: read",
                )),
            ):
                with self.subTest(name=name):
                    path.write_text(unsafe, encoding="utf-8")
                    findings = security.audit_workflow(
                        path, expected_permissions=permissions,
                        expected_job_permissions=job_permissions, root=root,
                    )
                    self.assertTrue(findings, name)

    def test_workflow_run_requires_main_push_success_guards(self) -> None:
        findings = self.audit(
            """name: unsafe
on:
  workflow_run:
    workflows: ["workspace-ci"]
    types: [completed]
permissions:
  actions: read
  contents: read
jobs:
  snapshot:
    runs-on: ubuntu-latest
    steps:
      - run: echo unsafe
""",
            permissions={"actions": "read", "contents": "read"},
        )
        self.assertTrue(any("workflow_run lacks required guard" in item for item in findings))

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


    def test_accepts_explicitly_allowed_job_permissions(self) -> None:
        content = """name: cold-start
on:
  push:
permissions:
  contents: read
jobs:
  cold-start:
    runs-on: ubuntu-latest
    steps:
      - run: echo safe
  site-cold-start:
    permissions:
      contents: read
      pages: read
    runs-on: ubuntu-latest
    steps:
      - run: echo safe
"""
        self.assertEqual(
            self.audit(
                content,
                job_permissions={
                    "site-cold-start": {"contents": "read", "pages": "read"}
                },
            ),
            [],
        )

    def test_rejects_unapproved_job_permissions_override(self) -> None:
        findings = self.audit(
            """name: unsafe
on:
  push:
permissions:
  contents: read
jobs:
  unexpected:
    permissions:
      contents: write
    runs-on: ubuntu-latest
    steps:
      - run: echo unsafe
"""
        )
        self.assertTrue(
            any("unauthorized job-level permissions override" in item for item in findings)
        )

    def test_rejects_job_permission_escalation(self) -> None:
        content = """name: unsafe
on:
  push:
permissions:
  contents: read
jobs:
  site-cold-start:
    permissions:
      contents: write
      pages: read
    runs-on: ubuntu-latest
    steps:
      - run: echo unsafe
"""
        findings = self.audit(
            content,
            job_permissions={
                "site-cold-start": {"contents": "read", "pages": "read"}
            },
        )
        self.assertTrue(
            any("job site-cold-start permissions" in item and "!= policy" in item
                for item in findings)
        )

    def test_rejects_extra_job_token_scope(self) -> None:
        content = """name: unsafe
on:
  push:
permissions:
  contents: read
jobs:
  site-cold-start:
    permissions:
      contents: read
      pages: read
      actions: write
    runs-on: ubuntu-latest
    steps:
      - run: echo unsafe
"""
        findings = self.audit(
            content,
            job_permissions={
                "site-cold-start": {"contents": "read", "pages": "read"}
            },
        )
        self.assertTrue(any("job site-cold-start permissions" in x for x in findings))

    def test_rejects_unsupported_or_duplicate_job_permissions(self) -> None:
        boilerplate = """name: unsafe
on:
  push:
permissions:
  contents: read
jobs:
  site-cold-start:
{declaration}
    runs-on: ubuntu-latest
    steps:
      - run: echo unsafe
"""
        variants = (
            "    permissions: write-all",
            "    permissions: ${{ github.event_name }}",
            "    permissions: {contents: read, pages: read}",
            "    permissions:\n      contents: read\n      contents: read\n      pages: read",
            "    permissions:\n      contents: read\n      pages: read\n    permissions:\n      contents: read\n      pages: read",
        )
        for declaration in variants:
            with self.subTest(declaration=declaration):
                findings = self.audit(
                    boilerplate.format(declaration=declaration),
                    job_permissions={
                        "site-cold-start": {"contents": "read", "pages": "read"}
                    },
                )
                self.assertTrue(
                    any("job site-cold-start permissions" in item or
                        "duplicate job-level permissions" in item
                        for item in findings)
                )

    def test_rejects_unsupported_inline_job_definition(self) -> None:
        findings = self.audit(
            """name: unsafe
on:
  push:
permissions:
  contents: read
jobs:
  unexpected: {permissions: {contents: write}, runs-on: ubuntu-latest}
"""
        )
        self.assertTrue(
            any("unauthorized job-level permissions override" in item for item in findings)
        )

    def test_requires_approved_job_permission_declaration(self) -> None:
        findings = self.audit(
            """name: unsafe
on:
  push:
permissions:
  contents: read
jobs:
  site-cold-start:
    runs-on: ubuntu-latest
    steps:
      - run: echo unsafe
""",
            job_permissions={
                "site-cold-start": {"contents": "read", "pages": "read"}
            },
        )
        self.assertTrue(
            any("required job-level permissions missing" in item for item in findings)
        )

    def test_ignores_permission_like_text_inside_run_block(self) -> None:
        findings = self.audit(
            """name: safe
on:
  push:
permissions:
  contents: read
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: |
          echo '    permissions:'
          echo '      contents: write'
"""
        )
        self.assertEqual(findings, [])



if __name__ == "__main__":
    unittest.main()
