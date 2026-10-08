"""Real Chrome (mobile and desktop) and Firefox keyboard/a11y regression gate.

Uses W3C WebDriver HTTP directly: no Selenium/Playwright Python dependency.
Browsers and drivers come from the GitHub-hosted Ubuntu runner image.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import time
from urllib.error import URLError, HTTPError
from urllib.request import ProxyHandler, Request, build_opener

if __package__:
    from .check_site_browser import fixture_status, serve_fixture
    from .render_site import read_version
else:
    from check_site_browser import fixture_status, serve_fixture
    from render_site import read_version
from datetime import datetime, timezone


HTTP = build_opener(ProxyHandler({}))
TAB = "\ue004"
ENTER = "\ue007"


def driver_binary(browser: str) -> str:
    name = "chromedriver" if browser == "chrome" else "geckodriver"
    found = shutil.which(name)
    if found:
        return found
    env = "CHROMEWEBDRIVER" if browser == "chrome" else "GECKOWEBDRIVER"
    directory = os.environ.get(env, "")
    candidate = Path(directory) / name
    if directory and candidate.is_file():
        return str(candidate)
    raise RuntimeError(f"{browser}: missing {name} on the GitHub runner")


def browser_binary(browser: str) -> str:
    name = "google-chrome" if browser == "chrome" else "firefox"
    found = shutil.which(name)
    if not found:
        raise RuntimeError(f"{browser}: missing {name}")
    return found


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class Browser:
    def __init__(self, browser: str, width: int | None = None):
        self.browser = browser
        self.width = width
        self.proc = None
        self.session = None

    def api(self, method: str, path: str, data=None):
        body = None if data is None else json.dumps(data).encode("utf-8")
        request = Request(
            f"http://127.0.0.1:{self.port}{path}", data=body, method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with HTTP.open(request, timeout=90 if path == "/session" else 15) as response:
                result = json.load(response)
        except HTTPError as exc:
            raise AssertionError(
                f"{self.browser} WebDriver {method} {path}: "
                f"{exc.code} {exc.read()[:1200]!r}"
            ) from exc
        value = result.get("value", result)
        if isinstance(value, dict) and value.get("error"):
            raise AssertionError(f"{self.browser} WebDriver: {value!r}")
        return result

    def __enter__(self):
        self.port = free_port()
        binary = driver_binary(self.browser)
        if self.browser == "chrome":
            command = [binary, f"--port={self.port}"]
            options = {
                "args": [
                    "--headless=new", "--no-sandbox", "--disable-gpu",
                    "--disable-dev-shm-usage", "--disable-background-networking",
                    "--no-first-run", "--no-default-browser-check",
                    "--window-size=1280,900",
                ],
                "binary": browser_binary(self.browser),
            }
            if self.width is not None:
                options["mobileEmulation"] = {
                    "deviceMetrics": {
                        "width": self.width, "height": 800, "pixelRatio": 1,
                    },
                }
            capabilities = {
                "browserName": "chrome", "goog:chromeOptions": options,
            }
        else:
            command = [binary, "--host", "127.0.0.1", "--port", str(self.port)]
            capabilities = {
                "browserName": "firefox",
                "moz:firefoxOptions": {
                    "args": ["-headless"],
                    "binary": browser_binary(self.browser),
                },
            }
        self.proc = subprocess.Popen(
            command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        try:
            for _ in range(150):
                if self.proc.poll() is not None:
                    raise AssertionError(f"{self.browser} driver exited early")
                try:
                    response = self.api("GET", "/status")
                    if response.get("value", {}).get("ready"):
                        break
                except (URLError, OSError):
                    pass
                time.sleep(0.1)
            else:
                raise AssertionError(f"{self.browser} driver startup timeout")

            result = self.api("POST", "/session", {
                "capabilities": {"alwaysMatch": capabilities},
            })
            value = result.get("value", {})
            self.session = value.get("sessionId") or result.get("sessionId")
            if not self.session:
                raise AssertionError(f"{self.browser} session missing: {result!r}")
            self.api("POST", f"/session/{self.session}/timeouts", {
                "script": 10000, "pageLoad": 20000,
            })
            if self.browser == "firefox":
                self.api("POST", f"/session/{self.session}/window/rect", {
                    "width": 1280, "height": 900,
                })
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, *_):
        if self.session:
            try:
                self.api("DELETE", f"/session/{self.session}")
            except Exception:
                pass
            self.session = None
        if self.proc:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=6)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()
            self.proc = None

    def open(self, url: str):
        self.api("POST", f"/session/{self.session}/url", {"url": url})

    def js(self, script: str, *args):
        result = self.api(
            "POST", f"/session/{self.session}/execute/sync",
            {"script": script, "args": list(args)},
        )
        return result.get("value")

    def key(self, value: str):
        self.api("POST", f"/session/{self.session}/actions", {
            "actions": [{"type": "key", "id": "keyboard", "actions": [
                {"type": "keyDown", "value": value},
                {"type": "keyUp", "value": value},
            ]}],
        })
        self.api("DELETE", f"/session/{self.session}/actions")

    def wait_status(self, expected: str):
        for _ in range(100):
            value = self.js(
                'return document.getElementById("status-overview")?.textContent || "";'
            )
            if expected in (value or ""):
                return
            time.sleep(0.1)
        raise AssertionError(f"{self.browser}: status did not become {expected!r}")


AUDIT_JS = r"""
const main = document.querySelector("main");
const heading = document.querySelector("h1");
const overview = document.getElementById("status-overview");
const links = [...document.querySelectorAll("a[href]")];
const clipped = [...document.querySelectorAll("main, h1, .status-grid, .status-card, nav, nav a")]
  .filter(el => {
    const r = el.getBoundingClientRect();
    return r.right > window.innerWidth + 2 || r.left < -2;
  }).map(el => el.tagName + (el.id ? "#" + el.id : ""));
const unnamed = links.filter(a => !a.textContent.trim() && !a.getAttribute("aria-label"));
const unsafe = links.filter(a => a.target === "_blank" && !a.rel.includes("noopener"));
return {
  width: window.innerWidth,
  scrollWidth: document.documentElement.scrollWidth,
  clipped, unnamed: unnamed.length, unsafe: unsafe.length,
  lang: document.documentElement.lang,
  mainCount: document.querySelectorAll("main").length,
  headingCount: document.querySelectorAll("h1").length,
  landmark: document.querySelector('section[aria-labelledby="status-title"]') !== null,
  live: overview.getAttribute("role") === "status" &&
        overview.getAttribute("aria-live") === "polite",
  hiddenEvidence: [...document.querySelectorAll("a.evidence")].filter(a => a.hidden).length,
  namedEvidence: [...document.querySelectorAll("a.evidence")]
    .every(a => (a.getAttribute("aria-label") || "").startsWith("查看 ")),
  skip: document.querySelector('a.skip-link[href="#content"]') !== null,
  focusStyle: [...document.querySelectorAll("a")].every(a => {
    a.focus();
    return a.matches(":focus-visible") || getComputedStyle(a).outlineStyle !== "none";
  }),
  mainId: main.id, heading: heading.textContent,
};
"""


def audit(browser: Browser, *, expected_width: int | None, failure: bool) -> None:
    state = browser.js(AUDIT_JS)
    if expected_width is not None and state["width"] != expected_width:
        raise AssertionError(f"{browser.browser}: viewport {state['width']}, expected {expected_width}")
    if state["scrollWidth"] > state["width"] + 2 or state["clipped"]:
        raise AssertionError(f"{browser.browser} horizontal overflow: {state!r}")
    for field, expected in (
        ("lang", "zh-CN"), ("mainCount", 1), ("headingCount", 1),
        ("landmark", True), ("live", True), ("unnamed", 0), ("unsafe", 0),
        ("namedEvidence", True), ("skip", True), ("mainId", "content"),
    ):
        if state[field] != expected:
            raise AssertionError(f"{browser.browser}: {field}={state[field]!r}")
    if state["hiddenEvidence"] != (4 if failure else 0):
        raise AssertionError(f"{browser.browser}: unexpected hidden evidence links: {state!r}")
    # The focus audit above only inspects styles; actual focus traversal below
    # uses WebDriver's real key input, not synthetic JavaScript KeyboardEvents.
    print(f"PASS: {browser.browser} {state['width']}px responsive/semantic checks")


def keyboard(browser: Browser, failure: bool) -> None:
    browser.open(browser.url)
    browser.wait_status("未知" if failure else "健康")
    # Reset focus: WebDriver keyboard input should encounter the skip link first.
    browser.js("document.activeElement.blur(); window.scrollTo(0, 0);")
    browser.key(TAB)
    focused = browser.js(
        'return {href: document.activeElement.getAttribute("href"), '
        'outline: getComputedStyle(document.activeElement).outlineStyle, '
        'width: getComputedStyle(document.activeElement).outlineWidth};'
    )
    if focused["href"] != "#content" or focused["outline"] == "none":
        raise AssertionError(f"{browser.browser}: skip-link keyboard focus {focused!r}")
    focus_targets = []
    for _ in range(5):
        browser.key(TAB)
        focus_targets.append(browser.js(
            'return document.activeElement.id || document.activeElement.textContent.trim();'
        ))
    if not failure:
        if focus_targets[:4] != [
            "ci-evidence", "release-evidence", "recovery-evidence", "sbom-evidence"
        ] or focus_targets[4] != "源码仓库":
            raise AssertionError(f"{browser.browser}: healthy Tab order {focus_targets!r}")
    elif focus_targets[0] != "源码仓库" or any(
        x.endswith("-evidence") for x in focus_targets
    ):
        raise AssertionError(f"{browser.browser}: failed Tab order {focus_targets!r}")
    print(f"PASS: {browser.browser} real Tab focus order: {focus_targets!r}")


def scenario(browser_name: str, width: int | None, page: bytes, version: str):
    healthy = fixture_status(datetime.now(timezone.utc), version)
    server = serve_fixture(page, json.dumps(healthy).encode("utf-8"))
    try:
        with Browser(browser_name, width) as browser:
            browser.url = f"http://127.0.0.1:{server.server_port}/"
            browser.open(browser.url)
            browser.wait_status("健康")
            audit(browser, expected_width=width, failure=False)
            keyboard(browser, failure=False)
    finally:
        server.shutdown()
        server.server_close()


def firefox_suite(page: bytes, version: str):
    # Reuse one Firefox session for healthy and degraded scenarios. Firefox
    # startup on shared hosted runners can take substantially longer than Chrome.
    healthy = fixture_status(datetime.now(timezone.utc), version)
    with Browser("firefox") as browser:
        cases = [
            ("healthy", json.dumps(healthy).encode("utf-8"), 200, "健康", False),
            ("HTTP 503", json.dumps(healthy).encode("utf-8"), 503, "未知", True),
            ("malformed JSON", b"{invalid", 200, "未知", True),
        ]
        for description, payload, code, expected, failure in cases:
            server = serve_fixture(page, payload, code)
            try:
                browser.url = f"http://127.0.0.1:{server.server_port}/"
                browser.open(browser.url)
                if failure:
                    for _ in range(100):
                        meta = browser.js(
                            'return document.getElementById("status-meta")?.textContent || "";'
                        )
                        if meta == "无法读取公开状态数据":
                            break
                        time.sleep(0.1)
                    else:
                        raise AssertionError(f"Firefox {description}: fallback not rendered")
                else:
                    browser.wait_status(expected)
                audit(browser, expected_width=None, failure=failure)
                keyboard(browser, failure=failure)
            finally:
                server.shutdown()
                server.server_close()
            print(f"PASS: Firefox {description} responsive, keyboard and fallback checks")



def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", type=Path, required=True)
    parser.add_argument("--version-file", type=Path, default=Path("VERSION"))
    args = parser.parse_args()
    version = read_version(args.version_file)
    page = args.site.read_bytes()
    if ("v" + version).encode() not in page:
        raise AssertionError("Compatibility test requires actual rendered website")
    for width in (320, 375, 768):
        scenario("chrome", width, page, version)
    scenario("chrome", None, page, version)
    firefox_suite(page, version)
    print("PASS: Chrome mobile/desktop and Firefox keyboard, a11y, failure checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
