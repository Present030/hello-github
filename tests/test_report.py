from __future__ import annotations

import json
import subprocess
import sys
import unittest

from hello_github.report import MESSAGE, build_report


class ReportTests(unittest.TestCase):
    def test_report_contains_expected_fields(self) -> None:
        report = build_report()
        self.assertEqual(report["message"], MESSAGE)
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


if __name__ == "__main__":
    unittest.main()
