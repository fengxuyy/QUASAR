"""Tests for image resource-cache linking and workspace path access."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest import mock

from src.rag.resource_cache import link_cached_resources
from src.tools.base import _is_path_inside


def test_link_cached_resources_symlinks_missing_and_empty_targets():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        cache = root / "cache"
        workspace = root / "workspace"
        workspace.mkdir()

        for name in ("docs", ".rag_index", ".hf_cache"):
            (cache / name).mkdir(parents=True)
            (cache / name / "sentinel.txt").write_text("ok")

        # Empty placeholder directory should be replaced with symlink
        (workspace / ".hf_cache").mkdir()
        # Non-empty existing directory must be preserved untouched
        (workspace / "docs").mkdir()
        (workspace / "docs" / "custom.txt").write_text("user")

        with mock.patch.dict(os.environ, {"QUASAR_RESOURCE_CACHE": str(cache)}):
            linked = link_cached_resources(workspace)

        assert set(linked) == {".rag_index", ".hf_cache"}
        assert (workspace / ".rag_index").is_symlink()
        assert (workspace / ".hf_cache").is_symlink()
        assert not (workspace / "docs").is_symlink()
        assert (workspace / "docs" / "custom.txt").read_text() == "user"


def test_is_path_inside_allows_resource_cache_symlinks_and_blocks_escapes():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        cache = root / "cache"
        workspace = root / "workspace"
        sibling = root / "workspace_evil"
        (cache / "docs" / "ase").mkdir(parents=True)
        (cache / "docs" / "ase" / "doc.rst").write_text("hi")
        workspace.mkdir()
        sibling.mkdir()
        (sibling / "secret.txt").write_text("nope")
        (workspace / "docs").symlink_to(cache / "docs", target_is_directory=True)

        with mock.patch.dict(os.environ, {"QUASAR_RESOURCE_CACHE": str(cache)}):
            assert _is_path_inside(workspace, workspace / "docs" / "ase" / "doc.rst") is True
            assert _is_path_inside(workspace, sibling / "secret.txt") is False
