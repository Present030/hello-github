"""Real Chrome smoke test for the self-contained Pixel Alchemy game.

Runs only in the existing browser E2E job; no new test dependencies.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from check_site_compatibility import Browser, ENTER


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", type=Path, required=True)
    args = parser.parse_args()
    page = args.site.resolve()
    if not page.is_file():
        raise AssertionError(f"Game was not included in the published site: {page}")

    with Browser("chrome", 375) as browser:
        browser.open(page.as_uri())
        before = browser.js("""
            const canvas = document.querySelector("#world");
            return {
              ready: canvas?.getAttribute("data-ready"),
              buttons: document.querySelectorAll(".tool[data-material]").length,
              scrollWidth: document.documentElement.scrollWidth,
              innerWidth: window.innerWidth,
              height: canvas?.height,
              width: canvas?.width
            };
        """)
        if before["ready"] != "true" or before["buttons"] != 8:
            raise AssertionError(f"Game did not initialize or materials are missing: {before!r}")
        if before["scrollWidth"] > before["innerWidth"] + 2:
            raise AssertionError(f"Game overflows 375px mobile viewport: {before!r}")
        if (before["width"], before["height"]) != (192, 120):
            raise AssertionError(f"Unexpected game simulation dimensions: {before!r}")

        browser.js('document.getElementById("pause").click();')
        paused = browser.js("""
            const pause = document.getElementById("pause");
            return pause.getAttribute("aria-pressed") === "true" &&
                document.getElementById("live").textContent.includes("暂停");
        """)
        if not paused:
            raise AssertionError("Pause button did not pause simulation")

        browser.js('document.querySelector("[data-material=\'2\']").click();')
        selected = browser.js("""
            return document.getElementById("current-tool").textContent === "水" &&
              document.querySelector("[data-material='2']").getAttribute("aria-pressed") === "true";
        """)
        if not selected:
            raise AssertionError("Water material selection did not update controls")

        # Paint with the real keyboard on a focused canvas while simulation is paused.
        browser.js('document.getElementById("world").focus();')
        browser.key(ENTER)
        painted = browser.js("""
            const ctx = document.getElementById("world").getContext("2d");
            const rgba = ctx.getImageData(96, 60, 1, 1).data;
            return [rgba[0], rgba[1], rgba[2]];
        """)
        if not (65 <= painted[0] <= 100 and 145 <= painted[1] <= 195):
            raise AssertionError(f"Enter did not paint water in the canvas: {painted!r}")

        browser.js('document.getElementById("volcano").click();')
        scene = browser.js("""
            const ctx = document.getElementById("world").getContext("2d");
            const rgba = ctx.getImageData(71, 53, 1, 1).data;
            return [rgba[0], rgba[1], rgba[2]];
        """)
        if scene[0] < 175 or scene[1] < 60:
            raise AssertionError(f"Volcano scene did not draw lava: {scene!r}")

        browser.js('document.getElementById("clear").click();')
        cleared = browser.js("""
            const ctx = document.getElementById("world").getContext("2d");
            return Array.from(ctx.getImageData(71, 53, 1, 1).data).slice(0, 3);
        """)
        if cleared[0] > 40:
            raise AssertionError(f"Clear did not reset the world: {cleared!r}")

    print("PASS: Pixel Alchemy Chrome mobile load, materials, keyboard drawing, pause, scenes, clear")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
