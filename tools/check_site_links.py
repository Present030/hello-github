"""Verify that links published on the GitHub Pages site are reachable."""

from __future__ import annotations

import argparse
import time
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

ALLOWED_HOSTS = {
    "github.com",
    "present030.github.io",
}

ALLOWED_HOST_SUFFIXES = (
    ".githubusercontent.com",
    ".githubassets.com",
)


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        if tag.lower() != "a":
            return
        for key, value in attrs:
            if key.lower() == "href" and value:
                self.links.append(value)


def extract_links(html: str) -> list[str]:
    parser = LinkParser()
    parser.feed(html)
    return list(dict.fromkeys(parser.links))


def host_allowed(hostname: str | None) -> bool:
    if not hostname:
        return False
    lowered = hostname.lower()
    return lowered in ALLOWED_HOSTS or lowered.endswith(ALLOWED_HOST_SUFFIXES)


def normalize_links(html: str, *, page_url: str) -> list[str]:
    normalized: list[str] = []
    for href in extract_links(html):
        url = urllib.parse.urljoin(page_url, href)
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme != "https":
            raise ValueError(f"link must use https: {href!r}")
        if not host_allowed(parsed.hostname):
            raise ValueError(f"link host is outside the allowed GitHub domains: {parsed.hostname}")
        normalized.append(url)
    return normalized


def fetch(url: str, *, attempts: int = 3) -> tuple[int, str]:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "hello-github-link-verifier",
                "Cache-Control": "no-cache",
                "Range": "bytes=0-0",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                response.read(1)
                final_url = response.geturl()
                final_host = urllib.parse.urlparse(final_url).hostname
                if not host_allowed(final_host):
                    raise RuntimeError(
                        f"redirect escaped allowed GitHub domains: {final_host}"
                    )
                return response.status, final_url
        except Exception as exc:
            last_error = exc
            if attempt < attempts:
                time.sleep(2)

    assert last_error is not None
    raise last_error


def verify_links(html: str, *, page_url: str) -> list[tuple[str, int]]:
    links = normalize_links(html, page_url=page_url)
    if not links:
        raise ValueError("site contains no links to verify")

    results: list[tuple[str, int]] = []
    for index, url in enumerate(links, start=1):
        status, final_url = fetch(url)
        if status < 200 or status >= 400:
            raise RuntimeError(f"link {index} returned HTTP {status}")
        final_host = urllib.parse.urlparse(final_url).hostname or "unknown"
        print(f"PASS: link {index}/{len(links)} reachable via {final_host} (HTTP {status})")
        results.append((url, status))
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--page-url", required=True)
    parser.add_argument(
        "--html",
        type=Path,
        help="optional local HTML file; otherwise fetch the public page",
    )
    args = parser.parse_args()

    if args.html is None:
        status, final_url = fetch(args.page_url)
        if status < 200 or status >= 400:
            raise RuntimeError(f"page returned HTTP {status}")
        request = urllib.request.Request(
            final_url,
            headers={
                "User-Agent": "hello-github-link-verifier",
                "Cache-Control": "no-cache",
            },
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            html = response.read().decode("utf-8")
    else:
        html = args.html.read_text(encoding="utf-8")

    results = verify_links(html, page_url=args.page_url)
    print(f"PASS: verified {len(results)} published links")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
