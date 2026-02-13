"""
Pre-built RAG index downloader.

Downloads and extracts pre-built RAG index from HuggingFace Hub.
"""

import io
import json
import os
import shutil
import tarfile
from pathlib import Path
from typing import Optional, Callable

# HuggingFace Hub configuration
HF_REPO_ID = "fengxuyy/quasar-rag"
HF_FILENAME = "rag_index.tar.gz"
INDEX_VERSION = "1.0.0"

# Expected model for compatibility
EXPECTED_MODEL = "BAAI/bge-large-en-v1.5"

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


def get_index_cache_path(workspace_dir: Path) -> Path:
    """Get the path where the index should be cached."""
    return workspace_dir / ".rag_index"


def get_metadata_path(workspace_dir: Path) -> Path:
    """Get the path to the index metadata file."""
    return workspace_dir / ".rag_index" / "metadata.json"


def is_index_valid(workspace_dir: Path) -> bool:
    """Check if a valid pre-built index exists."""
    index_path = get_index_cache_path(workspace_dir)
    metadata_path = get_metadata_path(workspace_dir)
    chroma_path = index_path / "chroma_db"
    
    if not index_path.exists() or not chroma_path.exists():
        return False
    
    # Check for Chroma database files
    has_parquet = list(chroma_path.glob("*.parquet"))
    has_sqlite = list(chroma_path.glob("*.sqlite*")) + list(chroma_path.glob("*.db"))
    
    if not (has_parquet or has_sqlite):
        return False
    
    # Check metadata compatibility
    if metadata_path.exists():
        try:
            with open(metadata_path, 'r') as f:
                metadata = json.load(f)
            
            stored_model = metadata.get('model_name')
            if stored_model != EXPECTED_MODEL:
                _log(f"Index model mismatch: {stored_model} != {EXPECTED_MODEL}")
                return False
        except Exception as e:
            _log(f"Could not read metadata: {e}")
            # Continue anyway if we can't read metadata
    
    return True


def download_index(
    workspace_dir: Path,
    status_tracker: Optional[Callable[[str], None]] = None,
    force: bool = False
) -> bool:
    """Download pre-built RAG index from HuggingFace Hub.
    
    Args:
        workspace_dir: Workspace directory where index will be stored
        status_tracker: Optional callback for progress updates
        force: Force re-download even if index exists
        
    Returns:
        True if index is available (downloaded or existed), False on error
    """
    index_path = get_index_cache_path(workspace_dir)
    
    # Check if valid index already exists
    if not force and is_index_valid(workspace_dir):
        _log("Pre-built index already exists and is valid")
        return True
    
    # Remove existing index if forcing or invalid
    if index_path.exists():
        _log("Removing existing index...")
        shutil.rmtree(index_path, ignore_errors=True)
    
    index_path.mkdir(parents=True, exist_ok=True)
    
    try:
        if status_tracker:
            status_tracker("Downloading pre-built RAG index...")
        _log(f"Downloading index from HuggingFace: {HF_REPO_ID}")
        
        # Try using huggingface_hub first
        try:
            from huggingface_hub import hf_hub_download
            
            archive_path = hf_hub_download(
                repo_id=HF_REPO_ID,
                filename=HF_FILENAME,
                repo_type="dataset"
            )
            
            if status_tracker:
                status_tracker("Extracting RAG index...")
            _log(f"Extracting index from {archive_path}")
            
            with tarfile.open(archive_path, "r:gz") as tar:
                tar.extractall(path=index_path)
            
        except ImportError:
            # Fallback to direct URL download
            _log("huggingface_hub not available, using direct download")
            import requests
            
            url = f"https://huggingface.co/datasets/{HF_REPO_ID}/resolve/main/{HF_FILENAME}"
            
            if status_tracker:
                status_tracker("Downloading RAG index (this may take a few minutes)...")
            
            response = requests.get(url, stream=True, timeout=300)
            response.raise_for_status()
            
            if status_tracker:
                status_tracker("Extracting RAG index...")
            
            with tarfile.open(fileobj=io.BytesIO(response.content), mode="r:gz") as tar:
                tar.extractall(path=index_path)
        
        # Verify download
        if is_index_valid(workspace_dir):
            _log("Pre-built index downloaded and verified successfully")
            if status_tracker:
                status_tracker("RAG index ready")
            return True
        else:
            _log("Downloaded index failed verification")
            return False
            
    except Exception as e:
        _log(f"Failed to download pre-built index: {e}")
        if status_tracker:
            status_tracker(f"Index download failed: {e}")
        # Clean up partial download
        if index_path.exists():
            shutil.rmtree(index_path, ignore_errors=True)
        return False


def load_prebuilt_index(workspace_dir: Path, embeddings):
    """Load a pre-built index if it exists.
    
    Args:
        workspace_dir: Workspace directory
        embeddings: Embeddings model to use
        
    Returns:
        Chroma vectorstore or None if not available
    """
    try:
        from langchain_chroma import Chroma
    except ImportError:
        _log("langchain_chroma not available")
        return None
    
    if not is_index_valid(workspace_dir):
        return None
    
    chroma_path = get_index_cache_path(workspace_dir) / "chroma_db"
    
    try:
        vectorstore = Chroma(
            persist_directory=str(chroma_path),
            embedding_function=embeddings
        )
        
        count = vectorstore._collection.count()
        if count > 0:
            _log(f"Loaded pre-built index with {count} chunks")
            return vectorstore
    except Exception as e:
        _log(f"Failed to load pre-built index: {e}")
    
    return None
