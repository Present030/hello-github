"""Real-Chrome regression for one-screen text cultivation, journal and save migration."""
from __future__ import annotations

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

from check_site_compatibility import Browser


KEY = "hello-github-text-cultivation-v1"


class SilentHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_args: object) -> None:
        pass


def saved(browser: Browser):
    return browser.js("return JSON.parse(localStorage.getItem(arguments[0]));", KEY)


def overwrite(browser: Browser, fields: dict) -> None:
    browser.js("""
        const obj = JSON.parse(localStorage.getItem(arguments[0]));
        Object.assign(obj, arguments[1]);
        obj.updated = Date.now();
        localStorage.setItem(arguments[0], JSON.stringify(obj));
    """, KEY, fields)


def layout(browser: Browser, width: int, height: int) -> None:
    browser.api("POST", f"/session/{browser.session}/goog/cdp/execute", {
        "cmd": "Emulation.setDeviceMetricsOverride",
        "params": {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": True},
    })
    state = browser.js("""
        const items = ["cultivate","gather","burn","brew","pill","break"];
        const allVisible = items.every(id => {
            const node = document.getElementById(id), r = node.getBoundingClientRect();
            return !node.hidden && r.width > 0 && r.height > 0 &&
                r.top >= -2 && r.bottom <= innerHeight + 2;
        });
        const history = document.getElementById("journal");
        const region = history.getBoundingClientRect();
        return {
            width: innerWidth, height: innerHeight,
            htmlHeight: document.documentElement.scrollHeight,
            bodyHeight: document.body.scrollHeight,
            htmlWidth: document.documentElement.scrollWidth,
            visibleButtons: allVisible,
            historyVisible: region.height > 38 && region.top >= -2 &&
                region.bottom <= innerHeight + 2,
            logParent: history.parentElement.className,
            hiddenTabs: document.querySelectorAll('[role="tab"]').length
        };
    """)
    assert (state["width"], state["height"]) == (width, height), state
    assert state["htmlHeight"] <= height + 2 and state["bodyHeight"] <= height + 2, state
    assert state["htmlWidth"] <= width + 2, state
    assert state["visibleButtons"] and state["historyVisible"], state
    assert state["logParent"] == "chronicle" and state["hiddenTabs"] == 0, state


def test(browser: Browser, url: str) -> None:
    browser.open(url)
    initial = browser.js("""
        return {
            ready: document.documentElement.dataset.ready,
            realm: document.getElementById("realm").textContent,
            graphics: document.querySelectorAll("canvas,svg,img,video").length
        };
    """)
    assert initial == {"ready": "true", "realm": "凡人", "graphics": 0}, initial
    for width, height in [(320, 568), (375, 667), (768, 700), (1280, 800)]:
        layout(browser, width, height)

    # Long journals must always be visible and must retain every event in v2.
    lifetime = [f"第 {i:03d} 条 · 修炼纪事" for i in range(70)]
    overwrite(browser, {"journal": lifetime, "version": 2})
    browser.open(url)
    journal = browser.js("""
        const list = document.getElementById("journal");
        const entries = JSON.parse(localStorage.getItem(arguments[0])).journal;
        return {
            stored:entries.length, rendered:list.children.length,
            first:list.firstElementChild.textContent, last:list.lastElementChild.textContent,
            count:document.getElementById("journal-count").textContent,
            scrollable:list.scrollHeight > list.clientHeight
        };
    """, KEY)
    assert journal["stored"] == journal["rendered"] == 70, journal
    assert journal["first"] == lifetime[0] and journal["last"] == lifetime[-1], journal
    assert journal["scrollable"] and "70" in journal["count"], journal

    # Reading older entries must not jump to the top on every timer update.
    browser.js('document.getElementById("journal").scrollTop = 150;')
    scroll_before = browser.js('return document.getElementById("journal").scrollTop;')
    assert scroll_before > 0
    browser.js('document.getElementById("gather").click();')
    after = browser.js("""
        const list = document.getElementById("journal");
        const s = JSON.parse(localStorage.getItem(arguments[0]));
        return {stored:s.journal.length, count:list.children.length,
            first:list.firstElementChild.textContent, scroll:list.scrollTop,
            visible:!list.hidden};
    """, KEY)
    assert after["stored"] == after["count"] == 71 and after["visible"], after
    assert after["scroll"] >= scroll_before, after
    browser.open(url)
    assert len(saved(browser)["journal"]) == 71

    # Real unattended cultivation resumes after a simulated offline interval.
    overwrite(browser, {"mode": "cultivate", "qi": 0})
    browser.js("""
        const x = JSON.parse(localStorage.getItem(arguments[0]));
        x.updated = Date.now() - 5500;
        localStorage.setItem(arguments[0], JSON.stringify(x));
    """, KEY)
    browser.open(url)
    advanced = saved(browser)
    assert advanced["qi"] >= 20 and advanced["realm"] == 0, advanced
    assert browser.js('return !document.getElementById("offline").hidden;')

    # v2 saves upgrade in place (same key, no loss of realm, resources or notes).
    overwrite(browser, {"version": 2, "realm": 3, "qi": 42,
                        "age": 30 * 365, "journal": lifetime[:]})
    browser.open(url)
    upgraded = saved(browser)
    assert upgraded["version"] == 3 and upgraded["realm"] == 3, upgraded
    assert upgraded["qi"] >= 42 and len(upgraded["journal"]) == 70, upgraded

    # One second is a season now; a four/five-second catchup consumes >1 year.
    overwrite(browser, {"mode": "cultivate", "age": 18 * 365, "qi": 0})
    browser.js("""
        const x=JSON.parse(localStorage.getItem(arguments[0]));
        x.updated=Date.now()-5500;
        localStorage.setItem(arguments[0], JSON.stringify(x));
    """, KEY)
    browser.open(url)
    faster_clock = saved(browser)
    assert faster_clock["age"] >= 18 * 365 + 5 * 90, faster_clock
    assert "剩约" in browser.js("return document.getElementById('life-clock').textContent;")

    # Early breakthrough grants actual technique bonuses, not only extra lifespan.
    overwrite(browser, {"realm": 2, "qi": 91, "age": 20 * 365, "mode": "cultivate"})
    browser.open(url)
    browser.js("Math.random=()=>0; document.getElementById('break').click();")
    unlocked = saved(browser)
    assert unlocked["realm"] == 3 and unlocked["age"] >= 21 * 365, unlocked
    assert any("归元诀" in e for e in unlocked["journal"]), unlocked
    assert "归元诀" in browser.js("return document.getElementById('insight').textContent;")

    # New burn cultivation gains fourfold qi at a larger and uncertain life cost.
    overwrite(browser, {"realm": 2, "qi": 0, "age": 20 * 365,
                        "mode": "cultivate"})
    browser.open(url)
    browser.js('document.getElementById("burn").click();')
    assert saved(browser)["mode"] == "burn"
    browser.js("""
        const x=JSON.parse(localStorage.getItem(arguments[0]));
        x.qi=0; x.updated=Date.now()-5500;
        localStorage.setItem(arguments[0], JSON.stringify(x));
    """, KEY)
    browser.open(url)
    burned = saved(browser)
    assert burned["qi"] >= 20 * 5, burned
    assert burned["age"] >= 20 * 365 + 5 * 270, burned

    # End-of-life pressure: major cultivation consumes multiple whole years.
    overwrite(browser, {"realm": 9, "qi": 600, "age": 99 * 365 - 5,
                        "mode": "cultivate", "dead": False})
    browser.open(url)
    browser.js("Math.random=()=>0; document.getElementById('break').click();")
    exhausted = saved(browser)
    assert exhausted["dead"] and "冲关耗尽" in exhausted["cause"], exhausted
    browser.js('document.getElementById("rebirth").click();')
    assert not saved(browser)["dead"]

    # Brewing, preparation, normal and major breakthroughs.
    overwrite(browser, {"herbs": 5, "stones": 2, "mode": "cultivate"})
    browser.open(url)
    potion = browser.js("""
        Math.random = () => 0;
        document.getElementById("brew").click();
        document.getElementById("pill").click();
        return JSON.parse(localStorage.getItem(arguments[0]));
    """, KEY)
    assert potion["buff"] and potion["pills"] == 0, potion

    # Start at Qi 9 and cross to Foundation Establishment early stage.
    # Update to the new urgency: the breakthrough itself takes multiple years.
    overwrite(browser, {"realm": 9, "qi": 600, "buff": False, "age": 29 * 365})
    browser.open(url)
    browser.js("Math.random = () => 0; document.getElementById('break').click();")
    breakthrough = saved(browser)
    assert breakthrough["realm"] == 10 and "筑基初期" in browser.js(
        "return document.getElementById('realm').textContent;"
    ), breakthrough
    assert breakthrough["journal"][0].find("筑基初期") >= 0, breakthrough

    # Within Foundation: early -> middle -> late -> Core, all visible stages.
    for old_realm, target, qi in [(10, "筑基中期", 900),
                                  (11, "筑基后期", 1250),
                                  (12, "金丹初期", 1700)]:
        overwrite(browser, {"realm": old_realm, "qi": qi})
        browser.open(url)
        browser.js("Math.random = () => 0; document.getElementById('break').click();")
        assert browser.js("return document.getElementById('realm').textContent;") == target

    # A death due to aging is final until the player explicitly reincarnates.
    overwrite(browser, {"realm": 0, "age": 75 * 365 - 2, "qi": 0})
    browser.js("""
        const x=JSON.parse(localStorage.getItem(arguments[0]));
        x.updated=Date.now()-5500;
        localStorage.setItem(arguments[0], JSON.stringify(x));
    """, KEY)
    browser.open(url)
    death = saved(browser)
    assert death["dead"] and death["generation"] == 1, death
    assert browser.js('return !document.getElementById("rebirth").hidden;')
    assert browser.js('return document.getElementById("journal").children.length;') >= 70
    browser.js('document.getElementById("rebirth").click();')
    reborn = saved(browser)
    assert not reborn["dead"] and reborn["generation"] == 2 and reborn["realm"] == 0
    assert reborn["marks"] >= 1 and reborn["qi"] == 0, reborn

    # High-realm tribulation can still be fatal.
    overwrite(browser, {"realm": 31, "qi": 94000, "age": 100 * 365,
                        "buff": False, "dead": False, "ascended": False})
    browser.open(url)
    outcome = browser.js("""
        const values=[0.99,0];
        Math.random=()=>values.length?values.shift():0;
        document.getElementById("break").click();
        return JSON.parse(localStorage.getItem(arguments[0]));
    """, KEY)
    assert outcome["dead"] and "天劫" in outcome["cause"], outcome

    # Existing v1 saves retain attained major stage and fractional cultivation.
    for old_realm, expected_realm, old_qi, expected_qi, display in [
        (10, 10, 450, 450, "筑基初期"),
        (11, 13, 1350, 1350, "金丹初期"),
        (12, 16, 2850, 2850, "元婴初期"),
        (13, 19, 5500, 5500, "化神初期"),
        (14, 31, 11000, 47000, "渡劫"),
    ]:
        overwrite(browser, {"version": 1, "realm": old_realm, "qi": old_qi,
                            "dead": False, "ascended": False, "age": 75 * 365,
                            "journal": lifetime[:]})
        browser.open(url)
        migrated = saved(browser)
        assert migrated["version"] == 3 and migrated["realm"] == expected_realm, migrated
        assert abs(migrated["qi"] - expected_qi) < 1, migrated
        assert len(migrated["journal"]) == len(lifetime), migrated
        assert browser.js("return document.getElementById('realm').textContent;") == display

    print("PASS: game UI, full journal, accelerated lifespan, rewarded breakthroughs, burn-mode risk, v1/v2 migration, death and tribulation")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", type=Path, required=True)
    args = parser.parse_args()
    source = args.site.resolve()
    if not source.is_file():
        raise AssertionError("Text cultivation was not included in published Pages output")
    server = ThreadingHTTPServer(("127.0.0.1", 0),
        partial(SilentHandler, directory=str(source.parent)))
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
