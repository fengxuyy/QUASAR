"""
QUASAR CLI entry point.

This module is the ``console_scripts`` entry point installed by
``pip install quasar-core``.  It locates the bundled Node.js CLI
(``cli.bundle.mjs``) and ``bridge.py``, then hands control to
``node`` via ``os.execvp`` so the process replaces itself entirely.
"""

from __future__ import annotations

import os
import shutil
import signal
import sys
from pathlib import Path


def _find_node() -> str | None:
    """Return the absolute path to a ``node`` binary, or *None*."""
    return shutil.which("node")


def _find_cli_bundle() -> Path | None:
    """Locate ``cli.bundle.mjs`` relative to this file's install location."""
    # The bundle lives at  quasar_cli/cli_dist/cli.bundle.mjs
    bundle = Path(__file__).resolve().parent / "cli_dist" / "cli.bundle.mjs"
    if bundle.is_file():
        return bundle
    return None


def _find_bridge() -> Path | None:
    """Locate ``bridge.py``.

    Search order:
      1. Sibling of the installed ``quasar_cli`` package (pip layout)
      2. ``../bridge.py`` relative to cwd (dev / Docker layout)
      3. ``bridge.py`` in cwd
      4. ``/app/bridge.py`` (Docker container layout)
    """
    # pip-installed layout:  site-packages/quasar_cli/  and  site-packages/bridge.py
    pkg_root = Path(__file__).resolve().parent.parent
    candidate = pkg_root / "bridge.py"
    if candidate.is_file():
        return candidate

    # Development / Docker layouts
    for p in (
        Path.cwd().parent / "bridge.py",
        Path.cwd() / "bridge.py",
        Path("/app/bridge.py"),
    ):
        if p.is_file():
            return p

    return None


def main() -> None:
    """Entry point for the ``quasar`` console script."""
    # --- Check for Node.js -----------------------------------------------
    node = _find_node()
    if node is None:
        print(
            "\033[31m✗ Node.js not found\033[0m\n"
            "\033[90mThe QUASAR CLI requires Node.js ≥ 20 to run.\n"
            "Install it from https://nodejs.org/ or via your package manager:\n"
            "  brew install node          # macOS\n"
            "  sudo apt install nodejs    # Debian / Ubuntu\n"
            "  conda install -c conda-forge nodejs  # conda\033[0m",
            file=sys.stderr,
        )
        sys.exit(1)

    # --- Locate bundled CLI JS -------------------------------------------
    cli_bundle = _find_cli_bundle()
    if cli_bundle is None:
        print(
            "\033[31m✗ CLI bundle not found\033[0m\n"
            "\033[90mExpected cli.bundle.mjs at:\n"
            f"  {Path(__file__).resolve().parent / 'cli_dist' / 'cli.bundle.mjs'}\n"
            "The quasar-core package may have been installed incorrectly.\n"
            "Try reinstalling:  pip install --force-reinstall quasar-core\033[0m",
            file=sys.stderr,
        )
        sys.exit(1)

    # --- Locate bridge.py ------------------------------------------------
    bridge = _find_bridge()
    if bridge is None:
        print(
            "\033[31m✗ bridge.py not found\033[0m\n"
            "\033[90mThe QUASAR Python backend could not be located.\n"
            "Make sure quasar-core is installed correctly.\033[0m",
            file=sys.stderr,
        )
        sys.exit(1)

    # --- Set environment for the Node.js CLI -----------------------------
    env = os.environ.copy()
    env["QUASAR_BRIDGE_PATH"] = str(bridge)

    # --- Replace this process with node ----------------------------------
    argv = [node, str(cli_bundle)] + sys.argv[1:]

    # Reset signal handlers so node gets clean defaults
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    signal.signal(signal.SIGTERM, signal.SIG_DFL)

    os.execvpe(node, argv, env)


if __name__ == "__main__":
    main()
