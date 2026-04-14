"""
Entry point for the `quasar` console script installed by pip.

When a user runs `quasar [args]`, pip calls main() here.
This launcher:
  1. Locates the pre-built Node CLI bundle (quasar_node/dist/cli.js) that
     ships alongside this file in site-packages.
  2. Passes the bridge.py path and the current Python executable to Node via
     environment variables so the Node process can spawn the right Python.
  3. Exec's Node, forwarding all arguments and the current environment.
"""

import os
import sys
import subprocess
from pathlib import Path


def _node_major_version() -> int | None:
    """Return the major version of `node` on PATH, or None if unavailable."""
    try:
        proc = subprocess.run(
            ["node", "--version"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None
    line = proc.stdout.strip()
    if not line.startswith("v"):
        return None
    try:
        return int(line[1:].split(".", 1)[0])
    except ValueError:
        return None


def main() -> None:
    root = Path(__file__).resolve().parent

    # Paths within site-packages after `pip install quasar-core`
    cli_js = root / "quasar_node" / "dist" / "cli.js"
    bridge_py = root / "bridge.py"

    if not cli_js.exists():
        print(
            "QUASAR: frontend bundle not found.\n"
            f"  Expected: {cli_js}\n"
            "  Please reinstall the package: pip install --force-reinstall quasar-core",
            file=sys.stderr,
        )
        raise SystemExit(1)

    if not bridge_py.exists():
        print(
            "QUASAR: bridge.py not found.\n"
            f"  Expected: {bridge_py}\n"
            "  Please reinstall the package: pip install --force-reinstall quasar-core",
            file=sys.stderr,
        )
        raise SystemExit(1)

    env = os.environ.copy()
    # Tell the Node CLI exactly where bridge.py lives (survives across cwd changes)
    env["QUASAR_BRIDGE_PATH"] = str(bridge_py)
    # Tell the Node CLI which Python binary to use (stays inside the venv if any)
    env["QUASAR_PYTHON_PATH"] = sys.executable

    major = _node_major_version()
    if major is not None and major < 20:
        print(
            f"QUASAR requires Node.js 20 or newer; found Node {major}.x.\n"
            "  Upgrade from https://nodejs.org and retry.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    try:
        result = subprocess.run(
            ["node", str(cli_js), *sys.argv[1:]],
            env=env,
        )
        raise SystemExit(result.returncode)
    except FileNotFoundError:
        print(
            "QUASAR requires Node.js 20 or newer (the CLI bundle needs modern RegExp support).\n"
            "  Install from https://nodejs.org and retry.",
            file=sys.stderr,
        )
        raise SystemExit(1)


if __name__ == "__main__":
    main()
