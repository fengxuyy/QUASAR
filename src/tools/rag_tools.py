from typing import Optional
from langchain_core.tools import tool

# Import RAG functionality from parent package sibling 'rag'
# Since we are in src.tools.rag_tools, we need to go up to src.rag
# Assuming src is a package
from ..rag import initialize_rag, query_rag as _query_rag, get_vectorstore

from .base import WORKSPACE_DIR


@tool
def initialize_rag_from_directory(directory_path: Optional[str] = None) -> str:
    """Initialize or reindex the RAG system with ASE, pymatgen, MACE, RASPA3, and Quantum ESPRESSO documentation.
    
    Args:
        directory_path: Path to directory containing source code or docs.
                       Can be a single path or comma-separated paths.
                       If None, tries to auto-detect from docs folder.
    
    Returns:
        Status message about initialization
    """
    try:
        from langchain_chroma import Chroma
        from ..rag import embeddings
        
        if not Chroma or not embeddings:
            return "Error: RAG dependencies not available. Install: langchain-chroma chromadb, sentence-transformers"
    except ImportError:
        return "Error: RAG dependencies not available. Install: langchain-chroma chromadb, sentence-transformers"
    
    # Parse comma-separated paths if provided
    if directory_path and ',' in directory_path:
        directory_path = [p.strip() for p in directory_path.split(',')]
    
    initialize_rag(directory_path, workspace_dir=WORKSPACE_DIR)
    
    vs = get_vectorstore()
    if vs:
        try:
            count = vs._collection.count()
            return f"RAG system initialized successfully with {count} document chunks."
        except:
            return "RAG system initialized successfully."
    else:
        return "Error: Failed to initialize RAG system. Check that the directory path is correct and contains ASE, pymatgen, MACE, RASPA3, or Quantum ESPRESSO files."


@tool
def query_rag(query: str, library: str, top_k: int = 3) -> str:
    """Query the RAG system for ASE, pymatgen, MACE, RASPA3, and Quantum ESPRESSO-related information.
    
    This is your exclusive source of information for ASE, pymatgen, MACE, RASPA3, and Quantum ESPRESSO API usage.
    Always query RAG before writing any code using these libraries.
    
    Args:
        query: The search query about ASE, pymatgen, MACE, RASPA3, or Quantum ESPRESSO functionality
        library: Library name to filter by. Valid values: "raspa3", "qe", "mace", "pymatgen", "ase"
        top_k: Number of results to return (default: 3)
    
    Returns:
        Retrieved documentation snippets and code examples
    """
    result = _query_rag(query, top_k, workspace_dir=WORKSPACE_DIR, library=library)
    # Format with code block
    return f"**RAG Query:** \"{query}\"\n\n```\n{result}\n```"

