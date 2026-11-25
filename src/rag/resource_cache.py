"""Link pre-cached docs, RAG index, and HuggingFace weights into a workspace.

When running inside a Docker image built with ``QUASAR_RESOURCE_CACHE``
(e.g. ``/opt/quasar/resource-cache``), bind-mounting a fresh host directory at
``/workspace`` starts empty. Calling ``link_cached_resources(workspace_dir)``
symlinks ``docs``, ``.rag_index``, and ``.hf_cache`` from the image cache into
the workspace when not already present, avoiding multi-minute first-run
downloads.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, List, Optional

DEFAULT_CACHED_RESOURCES = ("docs", ".rag_index", ".hf_cache")


def get_resource_cache_dir() -> Optional[Path]:
    """Return the configured resource cache directory if it exists."""
    raw = (os.environ.get("QUASAR_RESOURCE_CACHE") or "").strip()
    if not raw:
        return None
    cache_dir = Path(raw)
    if not cache_dir.is_dir():
        return None
    return cache_dir


def link_cached_resources(
    workspace_dir: Path,
    names: Iterable[str] = DEFAULT_CACHED_RESOURCES,
) -> List[str]:
    """Symlink pre-cached resources into ``workspace_dir`` when missing.

    Existing non-empty directories/files in ``workspace_dir`` are never
    overwritten. Dangling symlinks or empty placeholder directories are
    replaced with links to the cache.
    """
    cache_dir = get_resource_cache_dir()
    if cache_dir is None:
        return []

    try:
        cache_resolved = cache_dir.resolve()
        workspace_resolved = workspace_dir.resolve()
        if cache_resolved == workspace_resolved:
            return []
    except OSError:
        return []

    workspace_dir.mkdir(parents=True, exist_ok=True)
    linked: List[str] = []

    for name in names:
        source = cache_dir / name
        if not source.exists():
            continue

        target = workspace_dir / name
        try:
            if target.is_symlink():
                if target.exists():
                    continue
                target.unlink()
            elif target.exists():
                if target.is_dir() and not any(target.iterdir()):
                    target.rmdir()
                else:
                    continue

            target.symlink_to(source, target_is_directory=source.is_dir())
            linked.append(name)
        except OSError:
            continue

    return linked
