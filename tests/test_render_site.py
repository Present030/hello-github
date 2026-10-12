"""Tests for the static website renderer."""

from __future__ import annotations

import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from tools.render_site import main, read_version, render


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

    def test_renderer_copies_self_contained_game(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            template = source / "index.html"
            template.write_text("v{{VERSION}}", encoding="utf-8")
            (source / "game.html").write_text("<html>pixel game</html>", encoding="utf-8")
            (source / "cultivation.html").write_text("<html>text cultivation</html>", encoding="utf-8")
            version = root / "VERSION"
            version.write_text("0.3.0\n", encoding="utf-8")
            output = root / "published" / "index.html"
            with patch("sys.argv", ["render_site.py", "--template", str(template),
                                     "--version-file", str(version), "--output", str(output)]):
                self.assertEqual(main(), 0)
            self.assertEqual(output.read_text(encoding="utf-8"), "v0.3.0")
            self.assertEqual(output.with_name("game.html").read_text(encoding="utf-8"),
                             "<html>pixel game</html>")
            self.assertEqual(output.with_name("cultivation.html").read_text(encoding="utf-8"),
                             "<html>text cultivation</html>")

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
