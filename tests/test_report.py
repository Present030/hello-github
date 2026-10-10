from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

from hello_github import __version__
from hello_github.report import MESSAGE, build_report

ROOT = Path(__file__).resolve().parents[1]


class ReportTests(unittest.TestCase):
    def test_package_version_matches_repository_version(self) -> None:
        expected = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        self.assertEqual(__version__, expected)

    def test_report_contains_expected_fields(self) -> None:
        report = build_report()
        self.assertEqual(report["message"], MESSAGE)
        self.assertEqual(report["version"], __version__)
        self.assertTrue(report["python"])
        self.assertTrue(report["implementation"])
        self.assertTrue(report["system"])
        self.assertTrue(report["machine"])

    def test_json_cli_is_machine_readable(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "hello_github", "--json"],
            check=True,
            capture_output=True,
            text=True,
        )
        report = json.loads(completed.stdout)
        self.assertEqual(report["message"], MESSAGE)
        self.assertEqual(report["version"], __version__)

    def test_version_cli_matches_repository_version(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "hello_github", "--version"],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.stdout.strip(), __version__)


    def test_field_cli_rejects_unknown_field_without_traceback(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "hello_github", "--field", "nonexistent-field"],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(completed.stdout, "")
        self.assertNotIn("Traceback", completed.stderr)
        self.assertIn("--field", completed.stderr)
        self.assertIn("nonexistent-field", completed.stderr)

    def test_field_cli_rejects_json_conflict(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "hello_github", "--field", "python", "--json"],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(completed.stdout, "")
        self.assertIn("--field", completed.stderr)
        self.assertIn("--json", completed.stderr)


if __name__ == "__main__":
    unittest.main()
