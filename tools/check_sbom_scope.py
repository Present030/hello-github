"""Conservative scope gate for the CycloneDX zipapp SBOM.

The SBOM describes ONE executable, not Actions, dev tools or the Pages site.
This gate checks the archive layout and statically declared Python imports;
it does not claim to detect imports created dynamically at runtime.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import sys
from zipfile import BadZipFile, ZipFile

MAX_SOURCE_BYTES = 2 * 1024 * 1024
MAX_MEMBERS = 1000
VERSION_RE = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+\Z")


def audit_zipapp_imports(artifact: Path) -> int:
    """Return checked Python file count or raise on unexpected contents/imports."""
    try:
        with ZipFile(artifact) as archive:
            members = archive.infolist()
            if not members or len(members) > MAX_MEMBERS:
                raise ValueError("unexpected zipapp member count")
            seen: set[str] = set()
            for member in members:
                name = member.filename
                if (
                    name in seen
                    or name.startswith("/")
                    or "\\" in name
                    or ".." in name.split("/")
                    or not (
                        name == "__main__.py"
                        or re.fullmatch(r"hello_github/[A-Za-z_][A-Za-z0-9_]*\.py", name)
                    )
                    or member.file_size > MAX_SOURCE_BYTES
                    or member.is_dir()
                ):
                    raise ValueError(f"unexpected zipapp member: {name}")
                seen.add(name)
                try:
                    source = archive.read(member).decode("utf-8")
                    parsed = ast.parse(source, filename=name)
                except (UnicodeError, SyntaxError, RuntimeError, BadZipFile) as exc:
                    raise ValueError(f"invalid zipapp Python source: {name}") from exc
                for node in ast.walk(parsed):
                    target = None
                    if isinstance(node, ast.Import):
                        targets = [alias.name for alias in node.names]
                    elif isinstance(node, ast.ImportFrom):
                        targets = [node.module] if node.level == 0 and node.module else []
                    else:
                        continue
                    for item in targets:
                        root = item.partition(".")[0]
                        if root != "hello_github" and root not in sys.stdlib_module_names:
                            raise ValueError(f"non-stdlib static import in {name}: {root}")
            if "__main__.py" not in seen or "hello_github/__init__.py" not in seen:
                raise ValueError("zipapp is missing the entrypoint or application package")
            return len(seen)
    except BadZipFile as exc:
        raise ValueError("artifact is not a valid zipapp") from exc


def check_sbom_scope(*, artifact: Path, document: dict) -> int:
    """Fail closed on artifact, scope, or SBOM drift."""
    if not isinstance(document, dict):
        raise ValueError("SBOM must be a JSON object")
    metadata = document.get("metadata")
    component = metadata.get("component") if isinstance(metadata, dict) else None
    if not isinstance(component, dict):
        raise ValueError("SBOM application component missing")
    version = component.get("version")
    if not isinstance(version, str) or not VERSION_RE.fullmatch(version):
        raise ValueError("SBOM version invalid")
    purl = f"pkg:generic/hello-github@{version}"
    if (
        document.get("bomFormat") != "CycloneDX"
        or document.get("specVersion") != "1.6"
        or component.get("name") != "hello-github"
        or component.get("type") != "application"
        or component.get("bom-ref") != purl
        or component.get("purl") != purl
        or document.get("components") != []
        or component.get("properties") != [{
            "name": "hello-github:runtime-dependencies",
            "value": "python-standard-library-only",
        }]
    ):
        raise ValueError("SBOM scope or component metadata drift")
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    if component.get("hashes") != [{"alg": "SHA-256", "content": digest}]:
        raise ValueError("SBOM SHA-256 differs from zipapp")
    return audit_zipapp_imports(artifact)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check executable-only SBOM claims.")
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--sbom", type=Path, required=True)
    args = parser.parse_args()
    count = check_sbom_scope(
        artifact=args.artifact,
        document=json.loads(args.sbom.read_text(encoding="utf-8")),
    )
    print(f"PASS: executable-only SBOM scope; checked {count} Python ZIP members")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
