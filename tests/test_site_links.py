"""Tests for the GitHub Pages link integrity checker."""

from __future__ import annotations

import unittest

from tools.check_site_links import extract_links, host_allowed, normalize_links


class SiteLinkIntegrityTests(unittest.TestCase):
    def test_extract_links_preserves_order_and_deduplicates(self) -> None:
        html = (
            '<a href="https://github.com/a">A</a>'
            '<a href="https://github.com/b">B</a>'
            '<a href="https://github.com/a">A again</a>'
        )
        self.assertEqual(
            extract_links(html),
            ["https://github.com/a", "https://github.com/b"],
        )

    def test_known_github_hosts_are_allowed(self) -> None:
        self.assertTrue(host_allowed("github.com"))
        self.assertTrue(host_allowed("present030.github.io"))
        self.assertTrue(host_allowed("release-assets.githubusercontent.com"))
        self.assertFalse(host_allowed("example.com"))

    def test_relative_page_link_is_normalized(self) -> None:
        links = normalize_links(
            '<a href="./docs/">docs</a>',
            page_url="https://present030.github.io/hello-github/",
        )
        self.assertEqual(
            links,
            ["https://present030.github.io/hello-github/docs/"],
        )

    def test_non_https_link_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "https"):
            normalize_links(
                '<a href="http://github.com/Present030/hello-github">repo</a>',
                page_url="https://present030.github.io/hello-github/",
            )

    def test_external_host_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "outside"):
            normalize_links(
                '<a href="https://example.com/">outside</a>',
                page_url="https://present030.github.io/hello-github/",
            )


if __name__ == "__main__":
    unittest.main()
