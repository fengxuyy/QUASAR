"""RAG system for QUASAR-CHEM documentation retrieval.

This module provides RAG functionality for retrieving documentation from:
- ASE, pymatgen, MACE, RASPA3, Quantum ESPRESSO, LAMMPS

Features:
- Downloads documentation repos to ./docs on first use
- Downloads pre-built index from HuggingFace Hub
- For building the index, see: scripts/build_rag_index.py
"""

from .embeddings import initialize_embeddings, get_embeddings, get_embeddings_model_info
from .vectorstore import initialize_rag, get_vectorstore, set_vectorstore
from .query import query_rag
from .index_downloader import download_index, is_index_valid
from .docs_downloader import download_docs, is_docs_available, get_docs_path

# Global state for backward compatibility
rag_vectorstore = None
embeddings = None


def _sync_globals():
    """Sync module-level globals with internal state."""
    global rag_vectorstore, embeddings
    rag_vectorstore = get_vectorstore()
    embeddings = get_embeddings()


# Wrap functions to sync globals
_original_initialize_rag = initialize_rag
_original_set_vectorstore = set_vectorstore


def _wrapped_initialize_rag(*args, **kwargs):
    result = _original_initialize_rag(*args, **kwargs)
    _sync_globals()
    return result


def _wrapped_set_vectorstore(vs):
    result = _original_set_vectorstore(vs)
    _sync_globals()
    return result


initialize_rag = _wrapped_initialize_rag
set_vectorstore = _wrapped_set_vectorstore
_sync_globals()

__all__ = [
    'initialize_embeddings',
    'initialize_rag',
    'query_rag',
    'download_index',
    'is_index_valid',
    'download_docs',
    'is_docs_available',
    'get_docs_path',
    'get_vectorstore',
    'set_vectorstore',
    'get_embeddings',
    'get_embeddings_model_info',
    'rag_vectorstore',
    'embeddings',
]
