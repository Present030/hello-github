from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from tools.build_sbom import build_sbom, write_sbom


class SbomTests(unittest.TestCase):
    def test_sbom_describes_artifact_and_runtime_dependencies(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact = Path(tmp) / "hello-github.pyz"
            artifact.write_bytes(b"example-artifact")
            document = build_sbom(artifact=artifact, version="1.2.3")

        component = document["metadata"]["component"]
        expected_digest = hashlib.sha256(b"example-artifact").hexdigest()

        self.assertEqual(document["bomFormat"], "CycloneDX")
        self.assertEqual(document["specVersion"], "1.6")
        self.assertEqual(component["name"], "hello-github")
        self.assertEqual(component["version"], "1.2.3")
        self.assertEqual(component["purl"], "pkg:generic/hello-github@1.2.3")
        self.assertEqual(
            component["hashes"],
            [{"alg": "SHA-256", "content": expected_digest}],
        )
        self.assertIn(
            {
                "name": "hello-github:runtime-dependencies",
                "value": "python-standard-library-only",
            },
            component["properties"],
        )
        self.assertEqual(document["components"], [])

    def test_output_is_byte_for_byte_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "hello-github.pyz"
            artifact.write_bytes(b"stable")
            first = root / "first.cdx.json"
            second = root / "second.cdx.json"

            write_sbom(artifact=artifact, version="1.2.3", output=first)
            write_sbom(artifact=artifact, version="1.2.3", output=second)

            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertEqual(json.loads(first.read_text(encoding="utf-8"))["version"], 1)

    def test_empty_version_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact = Path(tmp) / "hello-github.pyz"
            artifact.write_bytes(b"x")
            with self.assertRaises(ValueError):
                build_sbom(artifact=artifact, version="   ")


if __name__ == "__main__":
    unittest.main()
