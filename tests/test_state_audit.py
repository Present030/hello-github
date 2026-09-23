from __future__ import annotations

import tempfile
from pathlib import Path
import unittest

from tools.audit_state import audit_state


VERSION = "1.2.3"
TAG = "v1.2.3"
TARGET = "a" * 40
DIGEST = "b" * 64
ACTION_SHA = "c" * 40


def make_repo(root: Path) -> None:
    (root / ".github" / "workflows").mkdir(parents=True)
    (root / "VERSION").write_text(VERSION + "\n", encoding="utf-8")
    (root / "README.md").write_text(
        f"Latest verified release: **{TAG}**.\n"
        f"SHA-256: {DIGEST}\n",
        encoding="utf-8",
    )
    (root / "PROJECT_STATE.md").write_text(
        f"- Current application version: `{VERSION}`.\n"
        f"- Latest verified release: `{TAG}`.\n"
        f"- `{TAG}` target commit: `{TARGET}`.\n"
        f"- Executable SHA-256: `{DIGEST}`.\n",
        encoding="utf-8",
    )
    (root / ".github" / "workflows" / "ci.yml").write_text(
        f"steps:\n  - uses: actions/checkout@{ACTION_SHA} # pinned\n",
        encoding="utf-8",
    )


def release_payload() -> dict[str, object]:
    return {
        "tag_name": TAG,
        "target_commitish": TARGET,
        "assets": [
            {
                "name": "hello-github.pyz",
                "digest": f"sha256:{DIGEST}",
            }
        ],
    }


class StateAuditTests(unittest.TestCase):
    def test_healthy_state_has_no_findings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_repo(root)
            self.assertEqual(audit_state(root, release_payload()), [])

    def test_detects_release_tag_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_repo(root)
            release = release_payload()
            release["tag_name"] = "v9.9.9"
            findings = audit_state(root, release)
            self.assertTrue(any("Release tag mismatch" in item for item in findings))

    def test_detects_documented_digest_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_repo(root)
            (root / "README.md").write_text(
                f"Latest verified release: **{TAG}**.\nSHA-256: {'d' * 64}\n",
                encoding="utf-8",
            )
            findings = audit_state(root, release_payload())
            self.assertTrue(any("README.md" in item and "SHA-256" in item for item in findings))

    def test_detects_movable_action_tag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_repo(root)
            (root / ".github" / "workflows" / "ci.yml").write_text(
                "steps:\n  - uses: actions/checkout@v7\n",
                encoding="utf-8",
            )
            findings = audit_state(root, release_payload())
            self.assertIn(
                ".github/workflows/ci.yml uses unpinned actions/checkout@v7",
                findings,
            )


if __name__ == "__main__":
    unittest.main()
