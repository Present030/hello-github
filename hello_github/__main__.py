"""Command-line entry point."""

from __future__ import annotations

import argparse
import json

from . import __version__
from .report import MESSAGE, build_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Show a small persistent-workspace runtime report.")
    parser.add_argument("--json", action="store_true", help="emit the runtime report as JSON")
    parser.add_argument("--version", action="version", version=__version__)
    args = parser.parse_args()

    if args.json:
        print(json.dumps(build_report(), sort_keys=True))
    else:
        print(MESSAGE)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
