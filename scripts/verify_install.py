from __future__ import annotations

import importlib.metadata
import json
import sys

EXPECTED_VERSION = "0.18.2"


def main() -> int:
    try:
        distribution = importlib.metadata.distribution("hermes-agent")
    except importlib.metadata.PackageNotFoundError:
        print("Hermes Agent is not installed in this venv", file=sys.stderr)
        return 1

    if distribution.version != EXPECTED_VERSION:
        print(
            f"Expected hermes-agent {EXPECTED_VERSION}, got {distribution.version}",
            file=sys.stderr,
        )
        return 1

    direct_url_text = distribution.read_text("direct_url.json")
    if direct_url_text:
        direct_url = json.loads(direct_url_text)
        if direct_url.get("dir_info", {}).get("editable", False):
            print("Hermes Agent must not be installed in editable mode", file=sys.stderr)
            return 1
        print(
            "Hermes Agent must be installed from the pinned package-index wheel",
            file=sys.stderr,
        )
        return 1

    tui_entry = distribution.locate_file("hermes_cli/tui_dist/entry.js")
    if not tui_entry.is_file():
        print("Hermes release wheel is missing tui_dist/entry.js", file=sys.stderr)
        return 1

    print(f"Hermes Agent {distribution.version} release wheel is installed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
