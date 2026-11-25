"""Pre-cache QUASAR documentation, RAG index, and embedding weights at image build time.

Controlled by ``QUASAR_PRECACHE_MODE`` (default ``all``):
  - ``all``: docs repos + QE pseudopotentials + MACE models + RAG index + BGE embeddings
  - ``docs``: docs repos + QE pseudopotentials + MACE models only
  - ``none``: skip pre-caching (leave cache directory empty)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _mode() -> str:
    raw = (os.environ.get("QUASAR_PRECACHE_MODE") or "all").strip().lower()
    if raw in {"false", "off", "0", "none"}:
        return "none"
    if raw in {"docs", "docs-only", "documentation"}:
        return "docs"
    return "all"


def main() -> None:
    cache_root = Path(
        os.environ.get("QUASAR_RESOURCE_CACHE", "/opt/quasar/resource-cache")
    ).resolve()
    hf_cache = cache_root / ".hf_cache"
    cache_root.mkdir(parents=True, exist_ok=True)
    hf_cache.mkdir(parents=True, exist_ok=True)

    os.environ["HF_HOME"] = str(hf_cache)
    os.environ["TRANSFORMERS_CACHE"] = str(hf_cache)
    os.environ["SENTENCE_TRANSFORMERS_HOME"] = str(hf_cache)
    os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = "1"
    os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
    os.environ["TOKENIZERS_PARALLELISM"] = "false"

    mode = _mode()
    print(f"Pre-caching QUASAR resources in {cache_root} (mode={mode})", flush=True)
    if mode == "none":
        print("Skipping resource pre-cache (mode=none).", flush=True)
        return

    from src.rag.docs_downloader import download_docs, is_docs_complete

    if not download_docs(cache_root) or not is_docs_complete(cache_root):
        raise RuntimeError(
            "Documentation pre-cache incomplete "
            "(need full repos + QE SSSP/PseudoDojo + MACE models)."
        )
    print("Documentation repos, pseudopotentials, and MACE models are ready.", flush=True)

    if mode == "docs":
        print("QUASAR docs cache is ready (RAG index/embeddings skipped).", flush=True)
        return

    from src.rag.embeddings import initialize_embeddings
    from src.rag.index_downloader import download_index, is_index_valid

    if not download_index(cache_root) or not is_index_valid(cache_root):
        raise RuntimeError("RAG index pre-cache did not produce a valid index.")
    print("Pre-built RAG index is ready.", flush=True)

    if initialize_embeddings(workspace_dir=cache_root) is None:
        raise RuntimeError("Embedding model pre-cache failed.")
    print("Embedding model weights are ready.", flush=True)

    # Remove downloaded rag_index.tar.gz blob from HF hub cache after extraction
    # to avoid duplicating the compressed archive in the final image layer.
    import shutil

    for dataset_cache in (hf_cache / "hub").glob("datasets--*"):
        shutil.rmtree(dataset_cache, ignore_errors=True)

    print("QUASAR resource cache is ready (docs + RAG + embeddings).", flush=True)


if __name__ == "__main__":
    main()
