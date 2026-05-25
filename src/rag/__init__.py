"""Lazy RAG facade for QUASAR-CHEM documentation retrieval.

The embedding/vectorstore stack can load native ML libraries. Keep this package
cheap to import so normal agent startup does not touch that stack unless RAG is
actually initialized or queried.
"""

# Global state for backward compatibility. These are synced after RAG calls.
rag_vectorstore = None
embeddings = None


def _sync_globals():
    """Sync module-level globals with the internal RAG modules when loaded."""
    global rag_vectorstore, embeddings

    try:
        from .embeddings import get_embeddings
        from .vectorstore import get_vectorstore
    except Exception:
        return

    rag_vectorstore = get_vectorstore()
    embeddings = get_embeddings()


def initialize_embeddings(*args, **kwargs):
    from .embeddings import initialize_embeddings as _initialize_embeddings

    result = _initialize_embeddings(*args, **kwargs)
    _sync_globals()
    return result


def get_embeddings(*args, **kwargs):
    from .embeddings import get_embeddings as _get_embeddings

    result = _get_embeddings(*args, **kwargs)
    _sync_globals()
    return result


def get_embeddings_model_info(*args, **kwargs):
    from .embeddings import get_embeddings_model_info as _get_embeddings_model_info

    return _get_embeddings_model_info(*args, **kwargs)


def initialize_rag(*args, **kwargs):
    from .vectorstore import initialize_rag as _initialize_rag

    result = _initialize_rag(*args, **kwargs)
    _sync_globals()
    return result


def get_vectorstore(*args, **kwargs):
    from .vectorstore import get_vectorstore as _get_vectorstore

    result = _get_vectorstore(*args, **kwargs)
    _sync_globals()
    return result


def set_vectorstore(*args, **kwargs):
    from .vectorstore import set_vectorstore as _set_vectorstore

    result = _set_vectorstore(*args, **kwargs)
    _sync_globals()
    return result


def query_rag(*args, **kwargs):
    from .query import query_rag as _query_rag

    result = _query_rag(*args, **kwargs)
    _sync_globals()
    return result


def download_index(*args, **kwargs):
    from .index_downloader import download_index as _download_index

    return _download_index(*args, **kwargs)


def is_index_valid(*args, **kwargs):
    from .index_downloader import is_index_valid as _is_index_valid

    return _is_index_valid(*args, **kwargs)


def download_docs(*args, **kwargs):
    from .docs_downloader import download_docs as _download_docs

    return _download_docs(*args, **kwargs)


def is_docs_available(*args, **kwargs):
    from .docs_downloader import is_docs_available as _is_docs_available

    return _is_docs_available(*args, **kwargs)


def get_docs_path(*args, **kwargs):
    from .docs_downloader import get_docs_path as _get_docs_path

    return _get_docs_path(*args, **kwargs)


__all__ = [
    "initialize_embeddings",
    "initialize_rag",
    "query_rag",
    "download_index",
    "is_index_valid",
    "download_docs",
    "is_docs_available",
    "get_docs_path",
    "get_vectorstore",
    "set_vectorstore",
    "get_embeddings",
    "get_embeddings_model_info",
    "rag_vectorstore",
    "embeddings",
]
