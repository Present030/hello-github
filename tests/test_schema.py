from __future__ import annotations

import unittest

from hello_github.schema import missing_report_fields


class SchemaTests(unittest.TestCase):
    def test_complete_report_has_no_missing_fields(self) -> None:
        report = {
            "message": "ok",
            "version": "0.2.1",
            "python": "3.13.15",
            "implementation": "CPython",
            "system": "Linux",
            "machine": "x86_64",
        }
        self.assertEqual(missing_report_fields(report), [])

    def test_repeated_calls_do_not_share_mutable_state(self) -> None:
        complete = {
            "message": "ok",
            "version": "0.2.1",
            "python": "3.13.15",
            "implementation": "CPython",
            "system": "Linux",
            "machine": "x86_64",
        }
        partial = {"message": "ok"}
        expected = ["version", "python", "implementation", "system", "machine"]

        self.assertEqual(missing_report_fields(complete), [])
        self.assertEqual(missing_report_fields(partial), expected)
        self.assertEqual(missing_report_fields(partial), expected)


if __name__ == "__main__":
    unittest.main()
