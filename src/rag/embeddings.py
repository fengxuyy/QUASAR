"""
Embeddings initialization for RAG.

Uses BAAI/bge-large-en-v1.5 for maximum accuracy.
This model is used for both indexing and querying to ensure compatibility.
"""

import os
from pathlib import Path
from typing import Optional, List

try:
    from langchain_huggingface import HuggingFaceEmbeddings
    _HAS_EMBEDDINGS = True
except ImportError:
    HuggingFaceEmbeddings = None
    _HAS_EMBEDDINGS = False

# Fixed model for cross-device compatibility
# Do NOT change this without rebuilding the index
MODEL_NAME = "BAAI/bge-large-en-v1.5"
MODEL_DIMENSIONS = 1024

# BGE models work best with query prefix for retrieval
# See: https://huggingface.co/BAAI/bge-large-en-v1.5
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

_embeddings = None

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


def _detect_device(status_tracker=None) -> str:
    """Detect available compute device. Returns 'cuda' if available, else 'cpu'."""
    try:
        import torch
        if torch.cuda.is_available():
            device_name = torch.cuda.get_device_name(0)
            if status_tracker:
                status_tracker(f"Using GPU: {device_name}")
            _log(f"GPU detected: {device_name}")
            return 'cuda'
    except ImportError:
        pass

    _log("No GPU available, using CPU")
    return 'cpu'


# Define BGEEmbeddings only if HuggingFaceEmbeddings is available
if _HAS_EMBEDDINGS:
    class BGEEmbeddings(HuggingFaceEmbeddings):
        """HuggingFace embeddings with BGE query prefix support.
        
        BGE models perform better when queries are prefixed with a special instruction.
        Documents are embedded without prefix, queries are prefixed.
        """
        
        def embed_query(self, text: str) -> List[float]:
            """Embed a query with BGE prefix for better retrieval."""
            # Add BGE query prefix for retrieval
            prefixed_text = QUERY_PREFIX + text
            return super().embed_query(prefixed_text)
        
        # embed_documents does NOT use prefix (documents are embedded as-is)
else:
    BGEEmbeddings = None


def _create_embeddings(device: str):
    """Create embeddings instance with BGE model.
    
    Suppresses stdout/stderr during creation to avoid interfering with CLI spinners.
    """
    if not _HAS_EMBEDDINGS or BGEEmbeddings is None:
        _log("Embeddings library not available")
        return None
    
    import io
    import contextlib
    
    # Suppress all stdout/stderr during model download
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return BGEEmbeddings(
            model_name=MODEL_NAME,
            model_kwargs={'device': device},
            encode_kwargs={'normalize_embeddings': True}
        )


def initialize_embeddings(workspace_dir: Optional[Path] = None, status_tracker=None):
    """Initialize embeddings for RAG.
    
    Args:
        workspace_dir: Workspace directory for persistent model cache.
        status_tracker: Optional callback for progress updates.
    
    Returns:
        Initialized embeddings object
    """
    global _embeddings
    
    if _embeddings is not None:
        return _embeddings
    
    # Setup cache directory
    if workspace_dir:
        cache_folder = workspace_dir / ".hf_cache"
        expected_cache = str(cache_folder)
        if os.environ.get("HF_HOME") != expected_cache:
            cache_folder.mkdir(parents=True, exist_ok=True)
            os.environ["HF_HOME"] = expected_cache
            os.environ["TRANSFORMERS_CACHE"] = expected_cache
            os.environ["SENTENCE_TRANSFORMERS_HOME"] = expected_cache
    
    device = _detect_device(status_tracker)
    device_str = "GPU" if device == 'cuda' else "CPU"
    
    if status_tracker:
        status_tracker(f"Loading embedding model ({device_str})...")
    
    _log(f"Loading {MODEL_NAME} on {device}")
    
    try:
        _embeddings = _create_embeddings(device)
        _log(f"Embeddings loaded successfully on {device}")
        
    except Exception as e:
        _log(f"Error loading embeddings on {device}: {e}")
        # If GPU failed, try CPU
        if device == 'cuda':
            _log("Falling back to CPU...")
            if status_tracker:
                status_tracker("Falling back to CPU...")
            try:
                _embeddings = _create_embeddings('cpu')
                _log("Embeddings loaded on CPU")
            except Exception as e2:
                _log(f"Failed to load embeddings on CPU: {e2}")
                _embeddings = None
        else:
            _embeddings = None
    
    return _embeddings


def get_embeddings():
    """Get the current embeddings object."""
    return _embeddings


def get_embeddings_model_info() -> Optional[dict]:
    """Get information about the current embeddings model."""
    if _embeddings is None:
        return None
    
    device = 'cpu'
    if hasattr(_embeddings, 'model_kwargs') and _embeddings.model_kwargs:
        device = _embeddings.model_kwargs.get('device', 'cpu')
    
    return {
        'model_name': MODEL_NAME,
        'dimensions': MODEL_DIMENSIONS,
        'device': device
    }
