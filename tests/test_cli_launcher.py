"""Tests for src.cli_launcher (pip-installed CLI and Web UI launcher)."""

from pathlib import Path
from unittest import mock

import pytest

from src import __version__, cli_launcher


def test_version_flag_short_circuits_without_node(capsys):
    with mock.patch.object(cli_launcher, "_detect_node") as detect_node:
        code = cli_launcher.main(["--version"])
    assert code == 0
    assert capsys.readouterr().out.strip() == __version__
    detect_node.assert_not_called()


def test_detect_node_missing(monkeypatch):
    monkeypatch.setattr(cli_launcher.shutil, "which", lambda _name: None)
    with pytest.raises(RuntimeError, match="Node.js >= 20 is required"):
        cli_launcher._detect_node()


def test_detect_node_too_old(monkeypatch):
    monkeypatch.setattr(cli_launcher.shutil, "which", lambda _name: "/usr/bin/node")
    fake_proc = mock.Mock(returncode=0, stdout="v18.19.0\n")
    monkeypatch.setattr(cli_launcher.subprocess, "run", lambda *a, **k: fake_proc)
    with pytest.raises(RuntimeError, match="requires Node.js >= 20"):
        cli_launcher._detect_node()


def test_build_runtime_env_defaults_workspace_to_cwd_for_pip_install(tmp_path, monkeypatch):
    site_packages = tmp_path / "site-packages"
    site_packages.mkdir()
    (site_packages / "bridge.py").write_text("# bridge\n", encoding="utf-8")

    user_dir = tmp_path / "user-project"
    user_dir.mkdir()
    monkeypatch.chdir(user_dir)
    monkeypatch.delenv("WORKSPACE_DIR", raising=False)
    monkeypatch.delenv("QUASAR_PYTHON", raising=False)
    monkeypatch.delenv("QUASAR_RUNTIME_ROOT", raising=False)
    monkeypatch.delenv("QUASAR_BRIDGE_PATH", raising=False)

    env = cli_launcher._build_runtime_env(
        site_packages,
        web_server_entry=tmp_path / "web" / "dist-server" / "index.js",
        web_static_dir=tmp_path / "web" / "dist",
        web_scripts_dir=tmp_path / "web" / "server" / "scripts",
    )

    assert env["WORKSPACE_DIR"] == str(user_dir)
    assert env["QUASAR_RUNTIME_ROOT"] == str(site_packages)
    assert env["QUASAR_BRIDGE_PATH"] == str(site_packages / "bridge.py")
    assert env["QUASAR_PYTHON"]
    assert env["QUASAR_WEB_SERVER_ENTRY"].endswith("dist-server/index.js")
    assert env["QUASAR_WEB_STATIC_DIR"].endswith("web/dist")
    assert env["QUASAR_WEB_SCRIPTS_DIR"].endswith("server/scripts")


def test_build_runtime_env_preserves_explicit_workspace_dir(tmp_path, monkeypatch):
    custom_ws = tmp_path / "custom-ws"
    monkeypatch.setenv("WORKSPACE_DIR", str(custom_ws))
    env = cli_launcher._build_runtime_env(tmp_path)
    assert env["WORKSPACE_DIR"] == str(custom_ws)


def test_bootstrap_node_component_installs_once_and_reuses_cache(tmp_path, monkeypatch):
    packaged = tmp_path / "packaged" / "cli"
    (packaged / "dist").mkdir(parents=True)
    (packaged / "package.json").write_text('{"name":"cli","type":"module"}\n', encoding="utf-8")
    (packaged / "dist" / "cli.js").write_text("console.log('hi');\n", encoding="utf-8")

    cache_root = tmp_path / "cache"
    install_calls = []

    def fake_run(cmd, cwd=None, stdout=None, check=False):
        install_calls.append((cmd, cwd, stdout))
        (Path(cwd) / "node_modules").mkdir(exist_ok=True)
        return mock.Mock(returncode=0)

    monkeypatch.setattr(cli_launcher, "_detect_npm", lambda: "/usr/bin/npm")
    monkeypatch.setattr(cli_launcher.subprocess, "run", fake_run)

    first = cli_launcher._bootstrap_node_component(
        component="cli",
        packaged_dir=packaged,
        asset_subdir="dist",
        node_major=22,
        cache_root=cache_root,
    )
    second = cli_launcher._bootstrap_node_component(
        component="cli",
        packaged_dir=packaged,
        asset_subdir="dist",
        node_major=22,
        cache_root=cache_root,
    )

    assert first == second
    assert (first / "dist" / "cli.js").is_file()
    assert (first / "node_modules").is_dir()
    assert (first / ".ready").is_file()
    assert len(install_calls) == 1
