"""Run real headless-Chrome smoke/E2E checks on the rendered and public site.

Only Python stdlib, locally served fixture JSON and preinstalled Chrome are used.
The browser executes the deployed HTML/JS; Node's mocked-DOM tests are separate.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from html import unescape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import threading
import urllib.request
from urllib.parse import urlparse

if __package__:
    from .build_public_status import WORKFLOWS, build_public_status
    from .render_site import read_version
else:
    from build_public_status import WORKFLOWS, build_public_status
    from render_site import read_version

HEAD = "a" * 40
OLD = "b" * 40


def chrome_binary() -> str:
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        resolved = shutil.which(name)
        if resolved:
            return resolved
    raise RuntimeError("Real browser E2E requires Chrome/Chromium on PATH")


def dump_dom(browser: str, url: str) -> str:
    with tempfile.TemporaryDirectory(prefix="hello-browser-") as profile:
        command = [
            browser, "--headless=new", "--no-sandbox", "--disable-gpu",
            "--disable-dev-shm-usage", "--disable-background-networking",
            "--no-first-run", "--no-default-browser-check",
            "--disable-extensions", "--hide-scrollbars",
            "--virtual-time-budget=5000", "--dump-dom",
            f"--user-data-dir={profile}", url,
        ]
        completed = subprocess.run(
            command, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=45, check=False,
        )
        if completed.returncode != 0 or "<html" not in completed.stdout.lower():
            raise AssertionError(
                f"Chrome did not render {url} (exit={completed.returncode})\n"
                + completed.stderr[-2500:] + "\n" + completed.stdout[-500:]
            )
        return completed.stdout


def visible_text(dom: str, element_id: str) -> str:
    # Inspect actual browser-produced DOM, not the original HTML template.
    pattern = (
        r'<(?:span|p)\b[^>]*\bid="' + re.escape(element_id)
        + r'"[^>]*>(.*?)</(?:span|p)>'
    )
    match = re.search(pattern, dom, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        raise AssertionError(f"Rendered browser DOM lacks {element_id}")
    return unescape(re.sub(r"<[^>]*>", "", match.group(1))).strip()


def fixture_status(now: datetime, version: str, *, failed: bool = False) -> dict:
    evidence = {
        name: {
            "id": index + 1, "run_number": 21, "event": "push",
            "head_sha": HEAD if name == "workspace-ci" else OLD,
            "conclusion": "success",
            "state": "current" if name == "workspace-ci" else "historical",
            "observed_at": (now - timedelta(hours=1)).isoformat(),
        }
        for index, name in enumerate(WORKFLOWS)
    }
    if failed:
        evidence = {
            "workspace-ci": {
                "id": 12345, "run_number": 22, "event": "push",
                "head_sha": HEAD, "conclusion": "failure",
            }
        }
    snapshot = {
        "schema": "hello-github-project-health/v1",
        "status": "degraded" if failed else "healthy",
        "snapshot_kind": "ci_failure" if failed else "main_ci_success",
        "generated_at": (now - timedelta(minutes=10)).isoformat(),
        "head_sha": HEAD,
        "version": None if failed else version,
        "release": (
            {"tag": None, "assets": {}} if failed else
            {"tag": "v" + version, "assets": {
                "hello-github.pyz": {},
                "hello-github.cdx.json": {},
                "hello-github-recovery.zip": {},
            }}
        ),
        "checks": {
            "current_main_ci": not failed,
            "release_alignment": True if not failed else None,
        },
        "workflow_evidence": evidence,
    }
    return build_public_status(snapshot, main_sha=HEAD, source_run_id=345, now=now)


class FixtureHandler(BaseHTTPRequestHandler):
    page: bytes = b""
    status_body: bytes = b""
    error_code: int = 200

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            body, code, mime = self.page, 200, "text/html; charset=utf-8"
        elif path == "/status.json":
            body = self.status_body
            code, mime = self.error_code, "application/json; charset=utf-8"
        else:
            body, code, mime = b"not found", 404, "text/plain"
        self.send_response(code)
        self.send_header("Content-Type", mime)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: object) -> None:
        pass


def serve_fixture(page: bytes, body: bytes, error_code: int = 200):
    # Per-request subclass isolates scenarios and avoids shared mutable state.
    handler = type("Handler", (FixtureHandler,), {
        "page": page, "status_body": body, "error_code": error_code,
    })
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def fixture_tests(browser: str, site_path: Path, version: str) -> None:
    page = site_path.read_bytes()
    if ("v" + version).encode("utf-8") not in page:
        raise AssertionError("Fixture site was not rendered for VERSION")

    now = datetime.now(timezone.utc)
    healthy = fixture_status(now, version)
    if healthy["status"] != "healthy":
        raise AssertionError("Healthy fixture was not accepted by the public exporter")
    failed = fixture_status(now, version, failed=True)
    if failed["status"] != "degraded":
        raise AssertionError("Failed CI fixture was not accepted by the public exporter")

    stale = dict(healthy)
    stale["source_generated_at"] = (now - timedelta(days=31)).isoformat()
    stale["expires_at"] = (now - timedelta(days=1)).isoformat()

    mismatch = dict(healthy)
    mismatch["version"] = "99.99.99"

    contradictory = json.loads(json.dumps(healthy))
    contradictory["checks"]["current_main_ci"] = False

    cases = [
        ("healthy", healthy, 200, "健康", "通过", "历史验证", "历史通过", "已包含"),
        ("failed-ci", failed, 200, "异常", "未通过", "未知", "未知", "未知"),
        ("stale-feed", stale, 200, "未知", "未知", "未知", "未知", "未知"),
        ("version-mismatch", mismatch, 200, "未知", "未知", "未知", "未知", "未知"),
        ("contradictory-healthy", contradictory, 200,
         "未知", "未知", "未知", "未知", "未知"),
        ("http-failure", healthy, 503, "未知", "未知", "未知", "未知", "未知"),
        ("missing-feed", healthy, 404, "未知", "未知", "未知", "未知", "未知"),
        ("invalid-json", b"{invalid", 200, "未知", "未知", "未知", "未知", "未知"),
    ]
    for case in cases:
        label, payload, status_code, *expected = case
        body = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
        server = serve_fixture(page, body, status_code)
        try:
            url = f"http://127.0.0.1:{server.server_port}/"
            dom = dump_dom(browser, url)
        finally:
            server.shutdown()
            server.server_close()
        actual = tuple(
            visible_text(dom, item)
            for item in ("status-overview", "ci-value", "release-value",
                         "recovery-value", "sbom-value")
        )
        if any(word not in value for word, value in zip(expected, actual)):
            raise AssertionError(
                f"{label}: browser rendered {actual!r}, expected tokens {expected!r}"
            )
        if "v" + version != visible_text(dom, "version-value"):
            raise AssertionError(f"{label}: VERSION changed in browser")
        print(f"PASS: real Chrome fixture {label}: {actual}")


def public_test(browser: str, page_url: str, version: str) -> None:
    url = page_url.rstrip("/") + "/"
    status_url = url + "status.json"
    request = urllib.request.Request(
        status_url, headers={"Cache-Control": "no-cache",
                             "User-Agent": "hello-github-browser-e2e"},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        data = json.load(response)
    dom = dump_dom(browser, url)
    expected_overview = {
        "healthy": "健康", "degraded": "异常", "unknown": "未知",
    }.get(data.get("status"))
    # At the consumption boundary, an expired/mismatched feed must be unknown
    # even if its published status is still "healthy".
    expires = data.get("expires_at")
    if not isinstance(expires, str):
        expected_overview = "未知"
    else:
        try:
            expiry = datetime.fromisoformat(expires.replace("Z", "+00:00"))
            if expiry <= datetime.now(timezone.utc):
                expected_overview = "未知"
        except ValueError:
            expected_overview = "未知"
    if data.get("version") not in (None, version):
        expected_overview = "未知"
    if expected_overview is None:
        raise AssertionError("Published feed schema/status is unknown")
    overview = visible_text(dom, "status-overview")
    if expected_overview not in overview:
        raise AssertionError(
            f"Public browser overview {overview!r} inconsistent with {data['status']!r}"
        )
    if visible_text(dom, "version-value") != "v" + version:
        raise AssertionError("Public browser VERSION mismatches repository")
    ci = visible_text(dom, "ci-value")
    if expected_overview == "健康" and ci != "通过":
        raise AssertionError(f"Healthy public feed yielded CI={ci!r}")
    if expected_overview == "未知" and ci != "未知":
        raise AssertionError(f"Unknown/expired public feed yielded CI={ci!r}")
    print(f"PASS: real Chrome public Pages {url} overview={overview}, CI={ci}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", type=Path, help="Rendered HTML to serve in fixture tests")
    parser.add_argument("--version-file", type=Path, default=Path("VERSION"))
    parser.add_argument("--public-url", help="Deployed Pages root URL (real browser)")
    args = parser.parse_args()
    if args.site is None and not args.public_url:
        parser.error("at least one of --site or --public-url is required")
    browser = chrome_binary()
    version = read_version(args.version_file)
    print(f"BROWSER_E2E_CHROME={browser}; VERSION={version}", flush=True)
    if args.site is not None:
        fixture_tests(browser, args.site, version)
    if args.public_url:
        public_test(browser, args.public_url, version)
    print("PASS: real browser E2E status checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
