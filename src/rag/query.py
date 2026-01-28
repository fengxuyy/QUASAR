"""Query functionality for RAG system."""

import os
import re
from pathlib import Path
from typing import Optional

from .vectorstore import get_vectorstore, initialize_rag
from .embeddings import get_embeddings

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


# Library name mapping for query filtering
LIBRARY_NAME_MAP = {
    "raspa3": "raspa3", "raspa": "raspa3",
    "qe": "quantum-espresso", "quantum-espresso": "quantum-espresso",
    "quantum espresso": "quantum-espresso", "quantumespresso": "quantum-espresso",
    "mace": "mace", "pymatgen": "pymatgen", "ase": "ase", "lammps": "lammps",
}

VALID_LIBRARIES_MSG = """Valid library names are:
- "raspa3" (or "raspa")
- "qe" (or "quantum-espresso", "quantum espresso")
- "mace"
- "pymatgen"
- "ase"
- "lammps"

If you want to search across all documentation, omit the library parameter."""


def _clean_text_content(text: str, max_consecutive_newlines: int = 2) -> str:
    """Clean text content by removing excessive whitespace."""
    if not text:
        return text
    
    # Replace multiple consecutive whitespace (spaces, tabs) with single space
    text = re.sub(r'[ \t]+', ' ', text)
    
    # Replace multiple consecutive newlines with max_consecutive_newlines
    text = re.sub(r'\n{3,}', '\n' * max_consecutive_newlines, text)
    
    # Remove leading/trailing whitespace from each line
    lines = [line.strip() for line in text.split('\n')]
    
    # Remove empty lines at the beginning and end
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    
    # Join back together
    text = '\n'.join(lines)
    
    # Final cleanup
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    return text


def query_rag(query: str, top_k: int = 3, workspace_dir: Optional[Path] = None, library: Optional[str] = None) -> str:
    """Query the RAG system for documentation.
    
    Args:
        query: Search query
        top_k: Number of results to return (default: 3)
        workspace_dir: Workspace directory (defaults to current directory)
        library: Optional library filter (raspa3, qe, mace, pymatgen, ase, lammps)
    
    Returns:
        Retrieved documentation snippets
    """
    if workspace_dir is None:
        workspace_dir = Path.cwd()
    
    rag_vectorstore = get_vectorstore()
    embeddings = get_embeddings()
    
    if rag_vectorstore is None:
        if Chroma and embeddings:
            _log("Attempting to auto-initialize RAG system")
            initialize_rag(workspace_dir=workspace_dir)
            rag_vectorstore = get_vectorstore()
        
        if rag_vectorstore is None:
            return "RAG system not initialized. Please ensure the pre-built index is available."
    
    # Normalize library filter
    library_filter = None
    if library:
        library_filter = LIBRARY_NAME_MAP.get(library.lower().strip())
        if not library_filter:
            return f"Error: Invalid library name '{library}'.\n\n{VALID_LIBRARIES_MSG}"
    
    try:
        where_filter = {"library": library_filter} if library_filter else None
        initial_k = top_k * 5
        
        if where_filter:
            docs_with_scores = rag_vectorstore.similarity_search_with_score(
                query, k=initial_k, filter=where_filter
            )
        else:
            docs_with_scores = rag_vectorstore.similarity_search_with_score(query, k=initial_k)
        
        if not docs_with_scores:
            lib_msg = f' in {library_filter} documentation' if library_filter else ''
            return f'No relevant documentation found for: "{query}"{lib_msg}.'
        
        # Re-rank with keyword boosting
        query_terms = set(term.lower() for term in re.findall(r'\w+', query) if len(term) > 2)
        reranked = []
        
        for doc, distance in docs_with_scores:
            base_sim = max(0, 1.0 - distance)
            content_lower = doc.page_content.lower()
            
            keyword_score = 0
            if query_terms:
                matches = sum(1 for term in query_terms if term in content_lower)
                keyword_score = matches / len(query_terms)
            
            final_score = base_sim + (keyword_score * 0.3)
            reranked.append((doc, final_score))
        
        reranked.sort(key=lambda x: x[1], reverse=True)
        
        # Filter by relevance threshold
        filtered = [(doc, score) for doc, score in reranked if score > 0.35][:top_k]
        if not filtered:
            filtered = reranked[:top_k]
        
        # Format results
        results = []
        for doc, score in filtered:
            if score < 0.1:
                continue
            
            content = _clean_text_content(doc.page_content)
            if len(content) > 4000:
                content = content[:4000] + "\n... (truncated)"
            
            source = doc.metadata.get('source', 'unknown')
            lib = doc.metadata.get('library', 'unknown')
            doc_type = doc.metadata.get('doc_type', 'unknown')
            module = doc.metadata.get('module', '')
            
            if os.path.isabs(source):
                try:
                    source = os.path.relpath(source, workspace_dir)
                except:
                    pass
            
            parts = [f"[Result {len(results) + 1}]"]
            if lib != 'unknown':
                parts.append(f"Library: {lib}")
            if doc_type != 'unknown':
                parts.append(f"Type: {doc_type}")
            if module:
                parts.append(f"Module: {module}")
            parts.extend([f"Source: {source}", f"Relevance: {score:.3f}", f"Content:\n{content}\n"])
            
            results.append("\n".join(parts))
        
        if not results:
            return """RAG query returned results, but none were relevant.

Try:
1. Rephrasing your query with different keywords
2. Searching for more specific terms
3. Consulting documentation directly"""
        
        return "\n".join(results)
    except Exception as e:
        _log("Error querying RAG", {"error": str(e)})
        return f"Error querying RAG: {str(e)}"
