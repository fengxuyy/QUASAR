"""
Entry point for the `quasar` console script installed by pip.

The Python package ships the backend plus a bundled Node CLI artifact.
This launcher wires the installed bridge and the active Python interpreter
into the Node process so `pip install quasar-core` exposes a working
`quasar` command.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parent
    cli_js = root / "quasar_node" / "dist" / "cli.js"
    bridge_py = root / "bridge.py"

    if not cli_js.exists():
        print(
            "QUASAR: frontend bundle not found.\n"
            f"  Expected: {cli_js}\n"
            "  Rebuild the package bundle and reinstall quasar-core.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    if not bridge_py.exists():
        print(
            "QUASAR: bridge.py not found.\n"
            f"  Expected: {bridge_py}\n"
            "  Reinstall quasar-core to restore the packaged backend.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    env = os.environ.copy()
    env["QUASAR_BRIDGE_PATH"] = str(bridge_py)
    env["QUASAR_PYTHON_PATH"] = sys.executable

    try:
        result = subprocess.run(["node", str(cli_js), *sys.argv[1:]], env=env)
    except FileNotFoundError:
        print(
            "QUASAR requires Node.js 18 or later at runtime.\n"
            "  Install Node.js from https://nodejs.org and retry.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
