from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from hello_github.report import MESSAGE

ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "tools" / "build_zipapp.py"


class ZipappTests(unittest.TestCase):
    def test_build_is_reproducible_and_runnable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            first = tmp_path / "first.pyz"
            second = tmp_path / "second.pyz"

            subprocess.run(
                [sys.executable, str(BUILDER), "--output", str(first)],
                check=True,
                cwd=ROOT,
            )
            subprocess.run(
                [sys.executable, str(BUILDER), "--output", str(second)],
                check=True,
                cwd=ROOT,
            )

            self.assertEqual(first.read_bytes(), second.read_bytes())

            completed = subprocess.run(
                [sys.executable, str(first), "--json"],
                check=True,
                capture_output=True,
                text=True,
                cwd=tmp_path,
            )
            report = json.loads(completed.stdout)
            self.assertEqual(report["message"], MESSAGE)
            self.assertTrue(report["python"])
            self.assertTrue(report["system"])


if __name__ == "__main__":
    unittest.main()
