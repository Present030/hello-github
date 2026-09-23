import unittest

from hello_github.report import build_report


class IntentionalFailureTest(unittest.TestCase):
    def test_ci_failure_is_observable(self) -> None:
        # Deliberately wrong for one CI run; this file will be corrected before merge.
        self.assertEqual(build_report()["message"], "INTENTIONAL_FAILURE_FOR_CI_PROBE")


if __name__ == "__main__":
    unittest.main()
