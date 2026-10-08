"""Regression coverage for scheduled five-asset attestation and recovery checks."""

from __future__ import annotations

from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest
from zipfile import ZIP_DEFLATED, ZipFile

from tools.build_recovery_bundle import build_recovery_bundle
from tools.verify_unattended_release import (
    expected_signer, verify_recovery,
    RECOVERY_MEMBERS,
)

TARGET = "a" * 40
REPOSITORY = "Present030/hello-github"


class UnattendedReleaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.release = self.root / "formal-release"
        self.release.mkdir()
        with ZipFile(self.release / "hello-github.pyz", "w", ZIP_DEFLATED) as archive:
            archive.writestr("__main__.py", 'import sys\nprint("0.3.0")\n')
        (self.release / "release-manifest.txt").write_text(
            f"tag=v0.3.0\nversion=0.3.0\ncommit={TARGET}\n", encoding="utf-8"
        )
        (self.release / "runtime-report.json").write_text(
            '{"version":"0.3.0"}\n', encoding="utf-8"
        )
        sbom = self.root / "sbom.json"
        sbom.write_text('{"bomFormat":"CycloneDX"}\n', encoding="utf-8")
        (self.release / "hello-github.cdx.json").write_bytes(sbom.read_bytes())
        self.bundle = self.release / "hello-github-recovery.zip"
        build_recovery_bundle(
            release_dir=self.release,
            sbom=sbom,
            repository=REPOSITORY,
            tag="v0.3.0",
            target_commit=TARGET,
            output=self.bundle,
        )

    def verify(self, **overrides) -> None:
        options = {
            "release_dir": self.release,
            "target_dir": self.root / "offline-output",
            "version": "0.3.0",
            "target_commit": TARGET,
            "repository": REPOSITORY,
        }
        options.update(overrides)
        verify_recovery(**options)

    def repack(self, *, replace=None, omit=None, extra=None, duplicate=None) -> None:
        with ZipFile(self.bundle) as original:
            payload = {n: original.read(n) for n in original.namelist()}
        if replace is not None:
            payload.update(replace)
        if omit is not None:
            payload.pop(omit)
        if extra is not None:
            payload.update(extra)
        with ZipFile(self.bundle, "w", ZIP_DEFLATED) as rebuilt:
            for name, value in payload.items():
                rebuilt.writestr(name, value)
            if duplicate:
                rebuilt.writestr(duplicate, payload[duplicate])

    def test_offline_recovery_is_verified_from_published_files(self):
        self.verify()
        self.assertTrue((self.root / "offline-output" / "verify.py").is_file())

    def test_real_cli_with_relative_output_path(self):
        # The earlier weekly run failed because the relative output folder was
        # prefixed twice when the extracted verifier inherited its own cwd.
        (self.root / "VERSION").write_text("0.3.0\\n", encoding="utf-8")
        (self.root / "metadata.json").write_text(
            json.dumps({"target_commitish": TARGET}), encoding="utf-8"
        )
        command = Path(__file__).resolve().parents[1] / "tools/verify_unattended_release.py"
        process = subprocess.run(
            [
                sys.executable, str(command),
                "--version-file", "VERSION",
                "--release-dir", "formal-release",
                "--release-json", "metadata.json",
                "--output-dir", "verified-offline-recovery",
                "--repository", REPOSITORY,
            ],
            cwd=self.root, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=45, check=False,
        )
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        self.assertIn("PASS: offline recovery contains", process.stdout)
        self.assertTrue((self.root / "verified-offline-recovery" / "verify.py").is_file())

    def test_legacy_witness_and_future_build_signer_cannot_mix(self):
        self.assertEqual(expected_signer("0.3.0"), "formal-release-attestation.yml")
        for version in ("0.3.1", "0.4.0", "1.0.0"):
            self.assertEqual(expected_signer(version), "release.yml")
        for version in ("0.2.1", "bad", "v0.3.0"):
            with self.assertRaises(ValueError):
                expected_signer(version)

    def test_missing_or_extra_archive_member_fails_closed(self):
        original = self.bundle.read_bytes()
        self.repack(omit="verify.py")
        with self.assertRaisesRegex(ValueError, "missing, duplicate or extra"):
            self.verify()
        self.bundle.write_bytes(original)
        self.repack(extra={"unexpected.txt": b"x"})
        with self.assertRaisesRegex(ValueError, "missing, duplicate or extra"):
            self.verify()

    def test_duplicate_archive_member_fails_closed(self):
        self.repack(duplicate="verify.py")
        with self.assertRaisesRegex(ValueError, "missing, duplicate or extra"):
            self.verify()

    def test_archive_path_traversal_fails_closed(self):
        self.repack(omit="verify.py", extra={"../outside.py": b"x"})
        with self.assertRaisesRegex(ValueError, "missing, duplicate or extra|unsafe"):
            self.verify()

    def test_recovery_identity_mismatch_is_detected(self):
        for override in (
            {"repository": "attacker/other"},
            {"target_commit": "b" * 40},
            {"version": "0.3.1"},
        ):
            with self.subTest(override=override):
                with self.assertRaisesRegex(ValueError, "identity"):
                    self.verify(**override)

    def test_embedded_asset_tampering_is_detected(self):
        self.repack(replace={"release/hello-github.pyz": b"changed"})
        with self.assertRaisesRegex(ValueError, "does not match published"):
            self.verify()

    def test_published_asset_tampering_is_detected(self):
        (self.release / "hello-github.pyz").write_bytes(b"changed-after-bundle")
        with self.assertRaisesRegex(ValueError, "does not match published"):
            self.verify()

    def test_actual_recovery_verifier_must_pass(self):
        self.repack(replace={"CHECKSUMS.sha256": b"deadbeef  bogus.txt\n"})
        with self.assertRaisesRegex(ValueError, "recovery verifier failed"):
            self.verify()

    def test_weekly_workflow_covers_all_assets_signer_and_recovery(self):
        root = Path(__file__).resolve().parents[1]
        script = (root / ".github/workflows/health-check.yml").read_text(encoding="utf-8")
        self.assertIn('cron: "17 3 * * 1"', script)
        self.assertIn("tools/verify_formal_release_assets.py", script)
        self.assertIn("tools/verify_unattended_release.py --signer-only", script)
        self.assertIn("gh attestation verify", script)
        self.assertIn(' --signer-workflow "$GITHUB_REPOSITORY/.github/workflows/$signer"', script)
        self.assertIn("tools/verify_unattended_release.py \\", script)
        self.assertIn("PASS: unattended five-asset provenance and offline recovery", script)
        self.assertIn("Open or update health-check failure Issue", script)
        self.assertIn("Close recovered health-check Issue", script)
        for name in ("hello-github.pyz", "hello-github.cdx.json",
                     "hello-github-recovery.zip", "release-manifest.txt", "runtime-report.json"):
            self.assertIn(name, script)
        self.assertEqual(len(RECOVERY_MEMBERS), 8)


if __name__ == "__main__":
    unittest.main()
