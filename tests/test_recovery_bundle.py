from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from tools.build_recovery_bundle import build_recovery_bundle


TAG = "v1.2.3"
TARGET = "a" * 40
FIXED_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


def make_test_zipapp(path: Path) -> None:
    info = ZipInfo("__main__.py", FIXED_TIMESTAMP)
    info.create_system = 3
    info.compress_type = ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    source = (
        "import sys\n"
        "if sys.argv[1:] == ['--version']:\n"
        "    print('1.2.3')\n"
        "else:\n"
        "    print('test app')\n"
    ).encode("utf-8")
    with ZipFile(path, "w") as archive:
        archive.writestr(info, source, compress_type=ZIP_DEFLATED, compresslevel=9)


def make_inputs(root: Path) -> tuple[Path, Path]:
    release = root / "release-input"
    release.mkdir()
    make_test_zipapp(release / "hello-github.pyz")
    (release / "release-manifest.txt").write_text(
        "tag=v1.2.3\nversion=1.2.3\ncommit=" + TARGET + "\n",
        encoding="utf-8",
    )
    (release / "runtime-report.json").write_text(
        '{"version":"1.2.3"}\n',
        encoding="utf-8",
    )
    sbom = root / "hello-github.cdx.json"
    sbom.write_text(
        '{"bomFormat":"CycloneDX","specVersion":"1.6"}\n',
        encoding="utf-8",
    )
    return release, sbom


class RecoveryBundleTests(unittest.TestCase):
    def test_bundle_is_deterministic_and_self_verifying(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            release, sbom = make_inputs(root)
            first = root / "first.zip"
            second = root / "second.zip"

            for output in (first, second):
                build_recovery_bundle(
                    release_dir=release,
                    sbom=sbom,
                    repository="example/hello-github",
                    tag=TAG,
                    target_commit=TARGET,
                    output=output,
                )

            self.assertEqual(first.read_bytes(), second.read_bytes())

            extracted = root / "extracted"
            with ZipFile(first) as archive:
                archive.extractall(extracted)
                self.assertEqual(
                    sorted(archive.namelist()),
                    [
                        "CHECKSUMS.sha256",
                        "RECOVERY.md",
                        "recovery.json",
                        "release/hello-github.pyz",
                        "release/release-manifest.txt",
                        "release/runtime-report.json",
                        "sbom/hello-github.cdx.json",
                        "verify.py",
                    ],
                )

            metadata = json.loads(
                (extracted / "recovery.json").read_text(encoding="utf-8")
            )
            artifact = extracted / "release" / "hello-github.pyz"
            self.assertEqual(metadata["version"], "1.2.3")
            self.assertEqual(metadata["release"]["tag"], TAG)
            self.assertEqual(metadata["release"]["target_commit"], TARGET)
            self.assertEqual(
                metadata["artifacts"]["release/hello-github.pyz"]["sha256"],
                hashlib.sha256(artifact.read_bytes()).hexdigest(),
            )

            completed = subprocess.run(
                [sys.executable, str(extracted / "verify.py")],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertIn("PASS: recovery bundle v1.2.3 verified", completed.stdout)

            with (extracted / "RECOVERY.md").open("a", encoding="utf-8") as stream:
                stream.write("\nTAMPERED\n")
            tampered = subprocess.run(
                [sys.executable, str(extracted / "verify.py")],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(tampered.returncode, 0)
            self.assertIn("checksum mismatch for RECOVERY.md", tampered.stderr)

    def test_rejects_invalid_target_commit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            release, sbom = make_inputs(root)
            with self.assertRaises(ValueError):
                build_recovery_bundle(
                    release_dir=release,
                    sbom=sbom,
                    repository="example/hello-github",
                    tag=TAG,
                    target_commit="not-a-sha",
                    output=root / "bundle.zip",
                )


if __name__ == "__main__":
    unittest.main()
