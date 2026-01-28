"""Manage pending execution state for interrupted Python execution recovery.

This module persists execution state before starting execute_python, enabling
recovery from SIGKILL scenarios where the checkpoint cannot be updated.
"""

import json
from pathlib import Path
from typing import Optional, Dict, Any

from .tools.base import WORKSPACE_DIR
from .debug_logger import log_custom

PENDING_EXECUTION_FILE = WORKSPACE_DIR / "pending_execution.json"


def save_pending_execution(ai_message_content: str, tool_call: Dict[str, Any], task_index: int):
    """Save the pending execution state before starting execute_python.
    
    This file is written BEFORE tool execution starts, so it survives SIGKILL.
    
    Args:
        ai_message_content: The content of the AIMessage containing the tool call
        tool_call: Dict with 'id', 'name', and 'args' keys
        task_index: The current task index (0-based)
    """
    try:
        data = {
            "ai_message_content": ai_message_content,
            "tool_call": tool_call,
            "task_index": task_index
        }
        PENDING_EXECUTION_FILE.write_text(json.dumps(data, indent=2))
        log_custom("PENDING_EXEC", f"Saved pending execution for {tool_call.get('name', 'unknown')}")
    except Exception as e:
        log_custom("PENDING_EXEC", f"Failed to save pending execution: {e}")


def load_pending_execution() -> Optional[Dict[str, Any]]:
    """Load pending execution state if exists.
    
    Returns:
        Dict with pending execution data, or None if no pending execution.
    """
    if PENDING_EXECUTION_FILE.exists():
        try:
            data = json.loads(PENDING_EXECUTION_FILE.read_text())
            log_custom("PENDING_EXEC", f"Loaded pending execution: {data.get('tool_call', {}).get('name', 'unknown')}")
            return data
        except Exception as e:
            log_custom("PENDING_EXEC", f"Failed to load pending execution: {e}")
            return None
    return None


def clear_pending_execution():
    """Clear pending execution state after successful completion."""
    if PENDING_EXECUTION_FILE.exists():
        try:
            PENDING_EXECUTION_FILE.unlink()
            log_custom("PENDING_EXEC", "Cleared pending execution")
        except Exception as e:
            log_custom("PENDING_EXEC", f"Failed to clear pending execution: {e}")
