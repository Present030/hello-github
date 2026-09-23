from __future__ import annotations

import unittest

from hello_github.schema import missing_report_fields


class SchemaTests(unittest.TestCase):
    def test_complete_report_has_no_missing_fields(self) -> None:
        report = {
            "message": "ok",
            "python": "3.13.15",
            "implementation": "CPython",
            "system": "Linux",
            "machine": "x86_64",
        }
        self.assertEqual(missing_report_fields(report), [])


if __name__ == "__main__":
    unittest.main()
