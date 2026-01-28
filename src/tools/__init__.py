from .filesystem import (
    read_file,
    write_file,
    edit_file,
    delete_file,
    list_directory,
    move_file,
    rename_file,
    analyze_image,
    grep_search,
    get_hardware_info
)
# Lazy import rag_tools to avoid heavy dependencies on import
# from .rag_tools import (
#     initialize_rag_from_directory,
#     query_rag
# )
from .execution import (
    execute_python,
    resume_execution,
    interrupt_running_execution,
    has_running_process
)
from .execution_check import continue_execution, interrupt_execution
from .web import (
    search_web,
    fetch_web_page
)
from .termination import complete_task, submit_evaluation
from .base import WORKSPACE_DIR, LOGS_DIR, MULTIMODAL_MODELS
import os

def initialize_rag_from_directory(*args, **kwargs):
    from .rag_tools import initialize_rag_from_directory as _init
    return _init(*args, **kwargs)

def query_rag(*args, **kwargs):
    from .rag_tools import query_rag as _query
    return _query(*args, **kwargs)

def is_rag_enabled():
    """Check if RAG is enabled via environment variable.
    
    Returns:
        bool: True if RAG is enabled (default), False if disabled
    """
    return os.getenv("ENABLE_RAG", "true").lower() in ("true", "1", "yes", "on")

def get_all_tools():
    """Get all tools for the agent."""
    tools = [
        read_file,
        write_file,
        edit_file,
        delete_file,
        list_directory,
        move_file,
        rename_file,
        analyze_image,
        execute_python,
        search_web,
        fetch_web_page,
        grep_search,
        get_hardware_info
    ]
    
    # Conditionally include RAG query tool if enabled
    # Note: initialize_rag_from_directory is NOT included here - it's an infrastructure
    # tool that should only be called during system startup in bridge.py
    if is_rag_enabled():
        # Lazy import here as well
        from .rag_tools import query_rag
        tools.insert(0, query_rag)
    
    return tools
