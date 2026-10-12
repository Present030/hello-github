"""Headless Chrome smoke tests for the text-only cultivation idle game."""
from __future__ import annotations

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

from check_site_compatibility import Browser


class SilentHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_args: object) -> None:
        pass


def test(browser: Browser, url: str) -> None:
    browser.open(url)
    ready = browser.js("""
        return {
            ready: document.documentElement.dataset.ready,
            title: document.title,
            graphics: document.querySelectorAll("img,svg,canvas,video").length,
            overflow: document.documentElement.scrollWidth > innerWidth + 2,
            realm: document.getElementById("realm").textContent
        };
    """)
    assert ready["ready"] == "true", ready
    assert "山中问道" in ready["title"], ready
    assert ready["graphics"] == 0 and not ready["overflow"], ready
    assert ready["realm"] == "凡人", ready

    # One-screen layout: page itself must not scroll at phone sizes;
    # only a tab panel may scroll internally when text becomes long.
    def layout(expected_width: int, expected_height: int) -> None:
        browser.api("POST", f"/session/{browser.session}/goog/cdp/execute", {
            "cmd": "Emulation.setDeviceMetricsOverride",
            "params": {"width": expected_width, "height": expected_height,
                       "deviceScaleFactor": 1, "mobile": True},
        })
        state = browser.js("""
            const active = document.querySelector('.tabs [aria-selected="true"]');
            return {
                width: innerWidth, height: innerHeight,
                rootHeight: document.documentElement.scrollHeight,
                bodyHeight: document.body.scrollHeight,
                rootWidth: document.documentElement.scrollWidth,
                active: active?.dataset.panel,
                tabs: document.querySelectorAll('[role="tab"]').length,
                visiblePanels: [...document.querySelectorAll('[role="tabpanel"]')]
                  .filter(panel => !panel.hidden).length,
            };
        """)
        assert state["width"] == expected_width and state["height"] == expected_height, state
        assert state["rootHeight"] <= state["height"] + 2, state
        assert state["bodyHeight"] <= state["height"] + 2, state
        assert state["rootWidth"] <= state["width"] + 2, state
        assert state["tabs"] == 4 and state["visiblePanels"] == 1, state

    for width, height in [(320, 568), (375, 667), (768, 700), (1280, 800)]:
        layout(width, height)

    browser.js('document.getElementById("tab-journal").click();')
    panel_state = browser.js("""
        return {
            selected: document.getElementById("tab-journal").getAttribute("aria-selected"),
            shown: !document.getElementById("panel-journal").hidden,
            practiceHidden: document.getElementById("panel-practice").hidden
        };
    """)
    assert panel_state == {"selected": "true", "shown": True, "practiceHidden": True}, panel_state
    browser.js('document.getElementById("tab-practice").click();')
    assert browser.js('return !document.getElementById("panel-practice").hidden;')

    browser.js('document.getElementById("gather").click();')
    mode = browser.js("""
        return JSON.parse(localStorage.getItem("hello-github-text-cultivation-v1")).mode;
    """)
    assert mode == "gather", mode

    # A five-second absence grants cultivation but does not auto-break through.
    browser.js("""
        const key = "hello-github-text-cultivation-v1";
        const save = JSON.parse(localStorage.getItem(key));
        save.mode = "cultivate";
        save.qi = 0;
        save.updated = Date.now() - 5500;
        localStorage.setItem(key, JSON.stringify(save));
    """)
    browser.open(url)
    progress = browser.js("""
        const x = JSON.parse(localStorage.getItem("hello-github-text-cultivation-v1"));
        return {qi:x.qi, realm:x.realm, offline:!document.getElementById("offline").hidden};
    """)
    assert progress["qi"] >= 20 and progress["realm"] == 0 and progress["offline"], progress

    # Brewing and protective medicine use actual local resources.
    browser.js("""
        const key = "hello-github-text-cultivation-v1";
        const save = JSON.parse(localStorage.getItem(key));
        save.herbs = 5; save.stones = 2; save.updated = Date.now();
        localStorage.setItem(key, JSON.stringify(save));
    """)
    browser.open(url)
    result = browser.js("""
        Math.random = () => 0;
        document.getElementById("brew").click();
        document.getElementById("pill").click();
        return JSON.parse(localStorage.getItem("hello-github-text-cultivation-v1"));
    """)
    assert result["buff"] is True and result["pills"] == 0, result

    # Mortality is real: offline lifetime depletion stops simulation and
    # makes reincarnation possible, without automatically reincarnating.
    browser.js("""
        const key = "hello-github-text-cultivation-v1";
        const save = JSON.parse(localStorage.getItem(key));
        save.realm = 0; save.age = 75*365 - 2;
        save.qi = 0; save.updated = Date.now() - 5500;
        localStorage.setItem(key, JSON.stringify(save));
    """)
    browser.open(url)
    death = browser.js("""
        const x = JSON.parse(localStorage.getItem("hello-github-text-cultivation-v1"));
        return {dead:x.dead, generation:x.generation, marks:x.marks,
          rebirth:!document.getElementById("rebirth").hidden};
    """)
    assert death["dead"] and death["rebirth"] and death["generation"] == 1, death
    assert browser.js('return !document.getElementById("panel-fate").hidden;'), "Fatal outcome must open breakthrough tab"
    browser.js('document.getElementById("rebirth").click();')
    reborn = browser.js("""
        const x = JSON.parse(localStorage.getItem("hello-github-text-cultivation-v1"));
        return {dead:x.dead, generation:x.generation, realm:x.realm,
          marks:x.marks, qi:x.qi};
    """)
    assert not reborn["dead"] and reborn["generation"] == 2, reborn
    assert reborn["marks"] >= 1 and reborn["realm"] == 0 and reborn["qi"] == 0, reborn
    assert browser.js('return !document.getElementById("panel-practice").hidden;'), "Rebirth should return to practice tab"

    # A deliberate high-realm breakthrough can be fatal.
    browser.js("""
        const key = "hello-github-text-cultivation-v1";
        const x = JSON.parse(localStorage.getItem(key));
        x.realm = 14; x.qi = 22000; x.age = 100*365;
        x.updated = Date.now(); x.dead = false; x.ascended = false; x.buff = false;
        localStorage.setItem(key, JSON.stringify(x));
    """)
    browser.open(url)
    outcome = browser.js("""
        const values = [0.99, 0];
        Math.random = () => values.length ? values.shift() : 0;
        document.getElementById("break").click();
        const x = JSON.parse(localStorage.getItem("hello-github-text-cultivation-v1"));
        return {dead:x.dead, cause:x.cause, rebirth:!document.getElementById("rebirth").hidden};
    """)
    assert outcome["dead"] and outcome["rebirth"] and "天劫" in outcome["cause"], outcome
    assert browser.js('return !document.getElementById("panel-fate").hidden;')

    print("PASS: text cultivation no page scrollbar 320/375/768/1280, tabs, offline, pills, death, reincarnation, tribulation")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", type=Path, required=True)
    args = parser.parse_args()
    source = args.site.resolve()
    if not source.is_file():
        raise AssertionError("Text cultivation was not included in the Pages output")
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        partial(SilentHandler, directory=str(source.parent)),
    )
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        with Browser("chrome", 375) as browser:
            test(browser, "http://127.0.0.1:{}/{}".format(server.server_port, source.name))
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
