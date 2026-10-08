"""Adversarial checks for the exact five published attestation subjects."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from tools.build_sbom import build_sbom
from tools.verify_formal_release_assets import (
    REQUIRED_ASSETS, verify_release_assets,
)

SHA = "a" * 40


def make_fixture(root: Path) -> dict:
    blobs = {
        "hello-github.pyz": b"reproducible-pyz",
        "hello-github-recovery.zip": b"reproducible-recovery",
        "runtime-report.json": b'{"version":"0.3.0"}\n',
        "release-manifest.txt": (
            f"tag=v0.3.0\nversion=0.3.0\ncommit={SHA}\n"
        ).encode("utf-8"),
    }
    for name, content in blobs.items():
        (root / name).write_bytes(content)
    sbom = build_sbom(artifact=root / "hello-github.pyz", version="0.3.0")
    (root / "hello-github.cdx.json").write_text(
        json.dumps(sbom), encoding="utf-8"
    )
    assert set(path.name for path in root.iterdir()) == REQUIRED_ASSETS
    return {
        "tag_name": "v0.3.0",
        "target_commitish": SHA,
        "draft": False,
        "prerelease": False,
        "assets": [
            {
                "name": name, "state": "uploaded",
                "size": (root / name).stat().st_size,
                "digest": "sha256:" + hashlib.sha256((root / name).read_bytes()).hexdigest(),
            }
            for name in sorted(REQUIRED_ASSETS)
        ],
    }


class ReleaseSubjectValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.metadata = make_fixture(self.root)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def verify(self, **kwargs):
        return verify_release_assets(
            version="0.3.0", metadata=self.metadata, directory=self.root, **kwargs
        )

    def test_five_exact_subjects_have_valid_digests(self):
        evidence = self.verify(expected_target=SHA)
        self.assertEqual(set(evidence["digests"]), REQUIRED_ASSETS)
        self.assertEqual(evidence["target"], SHA)
        self.assertEqual(evidence["tag"], "v0.3.0")

    def test_reject_tampered_bytes_for_each_of_five_files(self):
        for name in sorted(REQUIRED_ASSETS):
            with self.subTest(name=name):
                path = self.root / name
                original = path.read_bytes()
                path.write_bytes(original + b"tamp")
                with self.assertRaisesRegex(ValueError, "downloaded bytes"):
                    self.verify()
                path.write_bytes(original)

    def test_reject_missing_and_extra_subjects(self):
        path = self.root / "hello-github.pyz"
        original = path.read_bytes()
        path.unlink()
        with self.assertRaisesRegex(ValueError, "asset set"):
            self.verify()
        path.write_bytes(original)
        extra = self.root / "unexpected.txt"
        extra.write_text("extra", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "asset set"):
            self.verify()

    def test_reject_malformed_release_metadata_and_duplicates(self):
        self.metadata["assets"].append(dict(self.metadata["assets"][0]))
        with self.assertRaisesRegex(ValueError, "duplicate"):
            self.verify()

    def test_reject_failed_asset_upload_and_bad_digest(self):
        for change in (
            {"state": "starter"}, {"digest": None}, {"size": False},
        ):
            with self.subTest(change=change):
                item = self.metadata["assets"][0]
                original = dict(item)
                item.update(change)
                with self.assertRaisesRegex(ValueError, "missing uploaded"):
                    self.verify()
                item.clear()
                item.update(original)

    def test_reject_release_target_version_and_draft_drift(self):
        with self.assertRaisesRegex(ValueError, "expected build commit"):
            self.verify(expected_target="b" * 40)
        self.metadata["tag_name"] = "v0.4.0"
        with self.assertRaisesRegex(ValueError, "tag does not match"):
            self.verify()
        self.metadata["tag_name"] = "v0.3.0"
        self.metadata["draft"] = True
        with self.assertRaisesRegex(ValueError, "not a final"):
            self.verify()

    def test_reject_manifest_version_mismatch_even_when_digest_valid(self):
        path = self.root / "release-manifest.txt"
        path.write_text("tag=v0.3.0\nversion=9.9.9\ncommit=" + SHA + "\n", encoding="utf-8")
        for item in self.metadata["assets"]:
            if item["name"] == path.name:
                item["size"] = path.stat().st_size
                item["digest"] = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
        with self.assertRaisesRegex(ValueError, "manifest field"):
            self.verify()

    def test_reject_sbom_executable_mismatch_even_when_digest_valid(self):
        path = self.root / "hello-github.cdx.json"
        content = json.loads(path.read_text(encoding="utf-8"))
        content["metadata"]["component"]["hashes"][0]["content"] = "f" * 64
        path.write_text(json.dumps(content), encoding="utf-8")
        for item in self.metadata["assets"]:
            if item["name"] == path.name:
                item["size"] = path.stat().st_size
                item["digest"] = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
        with self.assertRaisesRegex(ValueError, "SBOM executable SHA256"):
            self.verify()

    def test_release_workflow_requires_two_distinct_provenance_jobs(self):
        root = Path(__file__).resolve().parents[1]
        text = (root / ".github/workflows/release.yml").read_text(encoding="utf-8")
        self.assertIn("  attest:\n    needs: release", text)
        self.assertIn("  verify-provenance:\n    needs: attest", text)
        self.assertIn("subject-path: 'published-release/*'", text)
        self.assertIn("tools/verify_formal_release_assets.py", text)
        self.assertIn('signer-workflow "$GITHUB_REPOSITORY/.github/workflows/release.yml"', text)

    def test_posthoc_witness_does_not_modify_published_release(self):
        root = Path(__file__).resolve().parents[1]
        text = (root / ".github/workflows/formal-release-attestation.yml").read_text(encoding="utf-8")
        self.assertIn("  independent-verify:\n    needs: sign-published", text)
        self.assertIn("subject-path: 'published-release/*'", text)
        self.assertIn("tools/check_release_readiness.py", text)
        self.assertIn('signer-workflow "$GITHUB_REPOSITORY/.github/workflows/formal-release-attestation.yml"', text)
        self.assertNotIn("gh release create", text)
        self.assertNotIn("gh release upload", text)
        self.assertNotIn("contents: write", text)


if __name__ == "__main__":
    unittest.main()
