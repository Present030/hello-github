import unittest

from hello_github.report import MESSAGE, build_report


class CIContractTest(unittest.TestCase):
    def test_runtime_message_matches_public_contract(self) -> None:
        self.assertEqual(build_report()["message"], MESSAGE)


if __name__ == "__main__":
    unittest.main()
