"""Console entry point (`quasar`) for pip-installed QUASAR CLI and Web UI."""

from __future__ import annotations

import hashlib
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable, Optional, Sequence

from . import __version__

MIN_NODE_MAJOR = 20
_READY_SENTINEL = ".ready"


def _package_src_dir() -> Path:
    return Path(__file__).resolve().parent


def _runtime_root() -> Path:
    return _package_src_dir().parent


def _packaged_ui_dir() -> Path:
    return _package_src_dir() / "_packaged_ui"


def _is_repo_checkout(root: Path) -> bool:
    return (
        (root / "bridge.py").is_file()
        and (root / "pyproject.toml").is_file()
        and (root / "cli").is_dir()
        and (root / "web").is_dir()
    )


def _default_ui_cache_root() -> Path:
    override = (os.environ.get("QUASAR_UI_CACHE_DIR") or "").strip()
    if override:
        return Path(override).expanduser()

    xdg_cache = (os.environ.get("XDG_CACHE_HOME") or "").strip()
    if xdg_cache:
        return Path(xdg_cache).expanduser() / "quasar" / "ui"

    if os.name == "nt":
        local_app_data = (os.environ.get("LOCALAPPDATA") or "").strip()
        if local_app_data:
            return Path(local_app_data) / "quasar" / "ui"

    return Path.home() / ".cache" / "quasar" / "ui"


def _detect_node() -> tuple[str, int]:
    node_bin = shutil.which("node")
    if not node_bin:
        raise RuntimeError(
            "Node.js >= 20 is required to run the QUASAR CLI and Web UI, "
            "but `node` was not found on PATH.\n"
            "Install Node.js 20+ (e.g. https://nodejs.org, `brew install node`, "
            "or `conda install -c conda-forge nodejs>=20`) and re-run `quasar`."
        )

    proc = subprocess.run(
        [node_bin, "--version"],
        capture_output=True,
        text=True,
        check=False,
    )
    version_text = (proc.stdout or "").strip()
    match = re.match(r"^v?(\d+)", version_text)
    if proc.returncode != 0 or not match:
        raise RuntimeError(
            f"Unable to determine Node.js version from `{node_bin} --version` "
            f"(output: {version_text!r})."
        )

    major = int(match.group(1))
    if major < MIN_NODE_MAJOR:
        raise RuntimeError(
            f"QUASAR requires Node.js >= {MIN_NODE_MAJOR}, but found {version_text} "
            f"at {node_bin}. Please upgrade Node.js and re-run `quasar`."
        )
    return node_bin, major


def _detect_npm() -> str:
    npm_bin = shutil.which("npm")
    if not npm_bin:
        raise RuntimeError(
            "`npm` was not found on PATH. It is required once to install the "
            "QUASAR CLI/Web UI Node.js runtime dependencies into the local cache."
        )
    return npm_bin


def _hash_paths(paths: Iterable[Path]) -> str:
    digest = hashlib.sha256()
    digest.update(__version__.encode("utf-8"))
    for path in sorted(paths):
        if path.is_file():
            digest.update(path.name.encode("utf-8"))
            digest.update(path.read_bytes())
        elif path.is_dir():
            for child in sorted(p for p in path.rglob("*") if p.is_file()):
                rel = child.relative_to(path).as_posix()
                digest.update(rel.encode("utf-8"))
                digest.update(child.read_bytes())
    return digest.hexdigest()[:12]


def _bootstrap_node_component(
    *,
    component: str,
    packaged_dir: Path,
    asset_subdir: str,
    node_major: int,
    cache_root: Optional[Path] = None,
) -> Path:
    """Materialize a packaged JS component and install its runtime node_modules once."""
    package_json = packaged_dir / "package.json"
    asset_src = packaged_dir / asset_subdir
    if not package_json.is_file() or not asset_src.is_dir():
        raise RuntimeError(
            f"Packaged QUASAR {component} assets are missing under {packaged_dir}. "
            "Reinstall `quasar-core` or build the frontend/CLI assets."
        )

    fingerprint = _hash_paths([package_json, asset_src])
    arch_tag = f"node{node_major}-{sys.platform}-{platform.machine()}"
    base_cache = cache_root or _default_ui_cache_root()
    target_dir = base_cache / f"{component}-{__version__}-{arch_tag}-{fingerprint}"
    ready_file = target_dir / _READY_SENTINEL

    if ready_file.is_file():
        return target_dir

    npm_bin = _detect_npm()
    base_cache.mkdir(parents=True, exist_ok=True)
    staging_dir = base_cache / f".{target_dir.name}.tmp.{os.getpid()}"
    if staging_dir.exists():
        shutil.rmtree(staging_dir, ignore_errors=True)

    print(
        f"[QUASAR] First-time setup: installing {component} Node.js runtime dependencies...",
        file=sys.stderr,
        flush=True,
    )

    try:
        staging_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(package_json, staging_dir / "package.json")
        shutil.copytree(asset_src, staging_dir / asset_subdir)

        install_cmd = [
            npm_bin,
            "install",
            "--omit=dev",
            "--no-audit",
            "--no-fund",
            "--no-package-lock",
            "--loglevel=error",
        ]
        proc = subprocess.run(
            install_cmd,
            cwd=str(staging_dir),
            stdout=sys.stderr,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"Failed to install QUASAR {component} Node.js runtime dependencies "
                f"(npm exited with code {proc.returncode})."
            )

        (staging_dir / _READY_SENTINEL).write_text(f"{__version__}\n", encoding="utf-8")

        try:
            os.replace(staging_dir, target_dir)
        except OSError:
            if ready_file.is_file():
                shutil.rmtree(staging_dir, ignore_errors=True)
            else:
                shutil.rmtree(target_dir, ignore_errors=True)
                shutil.move(str(staging_dir), str(target_dir))
    except Exception:
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise

    return target_dir


def _build_runtime_env(
    root: Path,
    *,
    web_server_entry: Optional[Path] = None,
    web_static_dir: Optional[Path] = None,
    web_scripts_dir: Optional[Path] = None,
    extra_env: Optional[dict[str, str]] = None,
) -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("QUASAR_PYTHON", sys.executable)
    env.setdefault("QUASAR_RUNTIME_ROOT", str(root))

    bridge_path = root / "bridge.py"
    if bridge_path.is_file():
        env.setdefault("QUASAR_BRIDGE_PATH", str(bridge_path))

    if not (env.get("WORKSPACE_DIR") or "").strip():
        if _is_repo_checkout(root):
            env["WORKSPACE_DIR"] = str(root / "workspace")
        else:
            env["WORKSPACE_DIR"] = os.getcwd()

    if web_server_entry is not None:
        env["QUASAR_WEB_SERVER_ENTRY"] = str(web_server_entry)
    if web_static_dir is not None:
        env["QUASAR_WEB_STATIC_DIR"] = str(web_static_dir)
    if web_scripts_dir is not None:
        env["QUASAR_WEB_SCRIPTS_DIR"] = str(web_scripts_dir)

    if extra_env:
        env.update(extra_env)

    return env


def _resolve_repo_ui(root: Path) -> Optional[dict[str, Path]]:
    cli_entry = root / "cli" / "dist" / "cli.js"
    cli_modules = root / "cli" / "node_modules"
    if not (cli_entry.is_file() and cli_modules.is_dir()):
        return None

    result: dict[str, Path] = {"cli_entry": cli_entry}
    web_entry = root / "web" / "dist-server" / "index.js"
    web_modules = root / "web" / "node_modules"
    if web_entry.is_file() and web_modules.is_dir():
        result["web_server_entry"] = web_entry
    web_static = root / "web" / "dist"
    if web_static.is_dir():
        result["web_static_dir"] = web_static
    web_scripts = root / "web" / "server" / "scripts"
    if web_scripts.is_dir():
        result["web_scripts_dir"] = web_scripts
    return result


def _exec_node(node_bin: str, script: Path, args: Sequence[str], env: dict[str, str]) -> int:
    cmd = [node_bin, str(script), *args]
    if os.name == "nt":
        return subprocess.call(cmd, env=env)
    os.execvpe(node_bin, cmd, env)
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)

    if args in (["--version"], ["-V"]):
        print(__version__)
        return 0

    try:
        node_bin, node_major = _detect_node()
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    root = _runtime_root()
    repo_ui = _resolve_repo_ui(root)
    wants_web_only = args == ["--web"]
    wants_web = "--web" in args

    try:
        if repo_ui is not None:
            env = _build_runtime_env(
                root,
                web_server_entry=repo_ui.get("web_server_entry"),
                web_static_dir=repo_ui.get("web_static_dir"),
                web_scripts_dir=repo_ui.get("web_scripts_dir"),
            )
            return _exec_node(node_bin, repo_ui["cli_entry"], args, env)

        packaged = _packaged_ui_dir()
        if not packaged.is_dir():
            print(
                "Error: QUASAR UI assets were not found in this installation.\n"
                "If running from source, build `cli` (`cd cli && npm install && npm run build`) "
                "and `web` (`cd web && npm install && npm run build`).",
                file=sys.stderr,
            )
            return 1

        web_static_dir = packaged / "web" / "dist"
        web_scripts_dir = packaged / "web" / "server" / "scripts"
        web_server_entry: Optional[Path] = None

        if wants_web:
            web_runtime = _bootstrap_node_component(
                component="web",
                packaged_dir=packaged / "web",
                asset_subdir="dist-server",
                node_major=node_major,
            )
            web_server_entry = web_runtime / "dist-server" / "index.js"

        if wants_web_only and web_server_entry is not None:
            env = _build_runtime_env(
                root,
                web_server_entry=web_server_entry,
                web_static_dir=web_static_dir if web_static_dir.is_dir() else None,
                web_scripts_dir=web_scripts_dir if web_scripts_dir.is_dir() else None,
                extra_env={
                    "NODE_ENV": "production",
                    "SERVE_STATIC": "true",
                },
            )
            print("Starting QUASAR Web UI...", flush=True)
            print(f"Launching Web UI server from {web_server_entry}", flush=True)
            return _exec_node(node_bin, web_server_entry, [], env)

        cli_runtime = _bootstrap_node_component(
            component="cli",
            packaged_dir=packaged / "cli",
            asset_subdir="dist",
            node_major=node_major,
        )
        cli_entry = cli_runtime / "dist" / "cli.js"
        env = _build_runtime_env(
            root,
            web_server_entry=web_server_entry,
            web_static_dir=web_static_dir if web_static_dir.is_dir() else None,
            web_scripts_dir=web_scripts_dir if web_scripts_dir.is_dir() else None,
        )
        return _exec_node(node_bin, cli_entry, args, env)
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
