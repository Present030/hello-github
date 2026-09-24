"""Tests for the static website renderer."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.render_site import read_version, render


class RenderSiteTests(unittest.TestCase):
    def test_render_replaces_version_everywhere(self) -> None:
        template = "version=v{{VERSION}} release=/tag/v{{VERSION}}"
        self.assertEqual(
            render(template, "1.2.3"),
            "version=v1.2.3 release=/tag/v1.2.3",
        )

    def test_render_requires_version_token(self) -> None:
        with self.assertRaisesRegex(ValueError, "missing"):
            render("no token here", "1.2.3")

    def test_read_version_accepts_semver_triplet(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "VERSION"
            path.write_text("4.5.6\n", encoding="utf-8")
            self.assertEqual(read_version(path), "4.5.6")

    def test_read_version_rejects_invalid_value(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "VERSION"
            path.write_text("v4.5\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "semantic version"):
                read_version(path)


if __name__ == "__main__":
    unittest.main()
