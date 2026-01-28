"""
Vector store management for RAG.

This module handles:
1. Downloading documentation (ASE, pymatgen, MACE, RASPA3, Q-E, LAMMPS)
2. Loading the pre-built RAG index from HuggingFace Hub

Indexing is handled separately by scripts/build_rag_index.py.
"""

from pathlib import Path
from typing import Optional

# Import Chroma from langchain-chroma
try:
    from langchain_chroma import Chroma
except ImportError:
    Chroma = None

# Import debug logger
try:
    from ..debug_logger import log_custom
    _HAS_DEBUG_LOGGER = True
except ImportError:
    _HAS_DEBUG_LOGGER = False

def _log(message: str, data: dict = None):
    """Log a RAG message to debug log."""
    if _HAS_DEBUG_LOGGER:
        log_custom("RAG", message, data or {})

from .embeddings import get_embeddings, initialize_embeddings
from .index_downloader import download_index, load_prebuilt_index, is_index_valid
from .docs_downloader import download_docs, is_docs_available

# Global vectorstore state
_vectorstore = None


def initialize_rag(
    workspace_dir: Optional[Path] = None,
    status_tracker=None,
    download_documentation: bool = True
):
    """Initialize RAG vector store by loading pre-built index.
    
    This function:
    1. Downloads documentation repos if not present
    2. Loads existing pre-built index from local cache
    3. Downloads pre-built index from HuggingFace Hub if not cached
    
    Note: Index building is handled separately by scripts/build_rag_index.py
    
    Args:
        workspace_dir: Workspace directory (defaults to current directory)
        status_tracker: Optional callback for progress updates
        download_documentation: Whether to download documentation repos (default: True)
    """
    global _vectorstore
    
    if workspace_dir is None:
        workspace_dir = Path.cwd()
    
    # 1. Download documentation repos if needed
    if download_documentation and not is_docs_available(workspace_dir):
        if status_tracker:
            status_tracker("Downloading documentation...")
        download_docs(workspace_dir, status_tracker)
    elif status_tracker:
        # Docs already available
        pass
    
    # 2. Initialize embeddings
    if status_tracker:
        status_tracker("Loading embedding model...")
    embeddings = initialize_embeddings(workspace_dir, status_tracker)
    
    # Check prerequisites
    if not Chroma:
        _log("WARNING: LangChain Chroma not available. Install: pip install langchain-chroma chromadb")
        if status_tracker:
            status_tracker("RAG unavailable: missing langchain-chroma")
        return
    if not embeddings:
        _log("WARNING: Embeddings not available. Install: pip install sentence-transformers")
        if status_tracker:
            status_tracker("RAG unavailable: missing embeddings")
        return
    
    # 3. Try to load pre-built index
    if status_tracker:
        status_tracker("Checking RAG index...")
    
    # Check if pre-built index exists locally
    if is_index_valid(workspace_dir):
        _log("Found valid pre-built index locally")
        if status_tracker:
            status_tracker("Loading RAG index...")
            
        vectorstore = load_prebuilt_index(workspace_dir, embeddings)
        if vectorstore:
            _vectorstore = vectorstore
            count = _vectorstore._collection.count()
            _log(f"Loaded pre-built index with {count} chunks")
            if status_tracker:
                status_tracker(f"RAG ready ({count} chunks)")
            return
    
    # 4. Download pre-built index from HuggingFace
    _log("Pre-built index not found or invalid, attempting download...")
    if status_tracker:
        status_tracker("Downloading RAG index...")
    
    if download_index(workspace_dir, status_tracker):
        if status_tracker:
            status_tracker("Loading RAG index...")
            
        vectorstore = load_prebuilt_index(workspace_dir, embeddings)
        if vectorstore:
            _vectorstore = vectorstore
            count = _vectorstore._collection.count()
            _log(f"Downloaded and loaded pre-built index with {count} chunks")
            if status_tracker:
                status_tracker(f"RAG ready ({count} chunks)")
            return
    
    # No index available
    _log("Pre-built index not available. Please build index using scripts/build_rag_index.py")
    if status_tracker:
        status_tracker("RAG index unavailable")
    _vectorstore = None


def get_vectorstore():
    """Get the current RAG vector store."""
    return _vectorstore


def set_vectorstore(vs):
    """Set the RAG vector store."""
    global _vectorstore
    _vectorstore = vs
