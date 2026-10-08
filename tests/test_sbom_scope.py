"""Executable-only SBOM scope and static-import regression tests."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile

from tools.build_sbom import build_sbom
from tools.check_sbom_scope import check_sbom_scope, audit_zipapp_imports


def make_zipapp(path: Path, *, extra: dict[str, str] | None = None):
    members = {
        "__main__.py": "import hello_github\n",
        "hello_github/__init__.py": "from . import report\n",
        "hello_github/report.py": "import json\nfrom pathlib import Path\n",
    }
    if extra:
        members.update(extra)
    with ZipFile(path, "w") as archive:
        for name, content in members.items():
            archive.writestr(name, content)


class SbomScopeTests(unittest.TestCase):
    def test_valid_executable_only_sbom_and_static_imports(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifact = Path(tmp) / "hello-github.pyz"
            make_zipapp(artifact)
            sbom = build_sbom(artifact=artifact, version="1.2.3")
            self.assertEqual(check_sbom_scope(artifact=artifact, document=sbom), 3)

    def test_rejects_external_import(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifact = Path(tmp) / "hello-github.pyz"
            make_zipapp(artifact, extra={"hello_github/plugin.py": "import requests\n"})
            sbom = build_sbom(artifact=artifact, version="1.2.3")
            with self.assertRaisesRegex(ValueError, "non-stdlib static import"):
                check_sbom_scope(artifact=artifact, document=sbom)

    def test_rejects_unexpected_vendored_or_path_traversal_member(self):
        for name in ("vendor/package.py", "../outside.py", "vendor-1.0.dist-info/METADATA"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                artifact = Path(tmp) / "hello-github.pyz"
                make_zipapp(artifact, extra={name: "pass\n"})
                with self.assertRaisesRegex(ValueError, "unexpected zipapp member"):
                    audit_zipapp_imports(artifact)

    def test_rejects_forged_sbom_hash_scope_and_component_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifact = Path(tmp) / "hello-github.pyz"
            make_zipapp(artifact)
            correct = build_sbom(artifact=artifact, version="1.2.3")
            for field, bad in (
                ("components", [{"type": "library", "name": "invented"}]),
                ("hashes", [{"alg": "SHA-256", "content": "0" * 64}]),
                ("properties", [{"name": "other", "value": "unchecked"}]),
            ):
                with self.subTest(field=field):
                    forged = deepcopy(correct)
                    if field == "components":
                        forged["components"] = bad
                    else:
                        forged["metadata"]["component"][field] = bad
                    with self.assertRaisesRegex(ValueError, "scope|SHA-256"):
                        check_sbom_scope(artifact=artifact, document=forged)

    def test_rejects_invalid_zipapp(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifact = Path(tmp) / "hello-github.pyz"
            artifact.write_bytes(b"not a ZIP")
            with self.assertRaisesRegex(ValueError, "not a valid zipapp"):
                audit_zipapp_imports(artifact)


if __name__ == "__main__":
    unittest.main()
