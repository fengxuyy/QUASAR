"""
Custom exceptions and error handling utilities.
"""

import re
import time
from typing import Any

from ...tools import LOGS_DIR
from .bridge import send_agent_event, send_json


class StreamingTimeoutError(Exception):
    """Exception raised when streaming times out."""
    pass


class APIConnectionError(Exception):
    """Custom exception for API connection errors."""
    pass


class FatalAPIError(Exception):
    """Exception raised when API errors persist after all retries are exhausted.
    
    This exception signals that the run should be terminated immediately.
    """
    pass


# Try to import ValidationError from pydantic
try:
    from pydantic import ValidationError
except ImportError:
    ValidationError = None


def format_validation_error(e: Any) -> str:
    """Format a Pydantic ValidationError into a concise, human-readable string.
    
    Strips out any raw input data that could contain large content like code.
    
    Args:
        e: The ValidationError object
        
    Returns:
        str: A formatted error message without raw arguments
    """
    if ValidationError is None or not isinstance(e, ValidationError):
        return _sanitize_error_message(str(e))
    
    try:
        errors = e.errors()
        messages = []
        for error in errors:
            loc = ' -> '.join(str(x) for x in error.get('loc', []))
            msg = error.get('msg', 'Unknown error')
            error_type = error.get('type', '')
            
            # Build concise message without raw input
            if loc:
                messages.append(f"Field '{loc}': {msg}")
            else:
                messages.append(msg)
        
        error_count = len(errors)
        result = f"Validation error ({error_count} issue{'s' if error_count > 1 else ''}): "
        result += "; ".join(messages)
        return result
        
    except Exception:
        # Fallback to sanitized string representation
        return _sanitize_error_message(str(e))


def _sanitize_error_message(error_str: str) -> str:
    """Remove raw JSON arguments/input data from error messages.
    
    This prevents large code content from being displayed in the execution log.
    
    Args:
        error_str: The raw error string
        
    Returns:
        str: Sanitized error message without raw arguments
    """
    # Remove JSON-like structures that might contain code
    # Pattern matches: {'key': 'value'...} or {"key": "value"...}
    sanitized = re.sub(
        r"\{['\"]?\w+['\"]?\s*:\s*['\"].*?['\"].*?\}",
        "{...}",
        error_str,
        flags=re.DOTALL
    )
    
    # Truncate if still too long
    max_len = 500
    if len(sanitized) > max_len:
        sanitized = sanitized[:max_len] + "... [truncated]"
    
    return sanitized


def is_api_connection_error(e: Exception) -> bool:
    """Check if an exception is a known API connection error based on HTTP error codes."""
    # API error codes to detect: 400 (Bad Request), 401 (Unauthorized), 404 (Not Found - invalid model), 
    # 429 (Rate Limit), 500 (Server Error)
    api_error_codes = {400, 401, 404, 429, 500}
    
    error_str = str(e)
    
    # Try to extract error code from the error string
    # Pattern 1: Look for "429 RESOURCE_EXHAUSTED" or "401 UNAUTHORIZED" or "404 NOT_FOUND" etc.
    code_match = re.search(r'\b(400|401|404|429|500)\b', error_str)
    if code_match:
        return True
    
    # Pattern 2: Look for error dict with code field: {'error': {'code': 429, ...}}
    code_in_dict = re.search(r"'code':\s*(\d+)", error_str) or re.search(r'"code":\s*(\d+)', error_str)
    if code_in_dict:
        code = int(code_in_dict.group(1))
        if code in api_error_codes:
            return True
    
    # Pattern 3: Check exception attributes (some libraries attach error info)
    if hasattr(e, 'status_code'):
        if e.status_code in api_error_codes:
            return True
    
    if hasattr(e, 'code'):
        if e.code in api_error_codes:
            return True
    
    # Fallback: check for common error strings (for backward compatibility)
    error_str_lower = error_str.lower()
    return "resource_exhausted" in error_str_lower or "connection error" in error_str_lower


def handle_api_retry(
    agent: str,
    error: Exception,
    current_count: int,
    max_retries: int = 3,
    wait_seconds: int = 120
) -> bool:
    """
    Handle API connection error with retry logic.
    
    Sends status updates to Node.js CLI and logs error details to conversation.md.
    When retries are exhausted or error is non-retriable, saves usage stats to
    checkpoint_settings.json and generates usage_report.md before returning.
    
    Args:
        agent: Agent name (e.g., "operator", "evaluator", "strategist")
        error: The exception that occurred
        current_count: Current retry attempt number (1-indexed)
        max_retries: Maximum number of retries allowed
        wait_seconds: Seconds to wait before retrying
        
    Returns:
        bool: True if should retry, False if max retries exceeded or error is non-retriable
    """
    from .logging import _write_to_log
    
    error_str = str(error)
    
    # Check if this is a non-retriable error (404 model not found, 401 unauthorized)
    # These errors won't be fixed by retrying
    is_non_retriable = bool(re.search(r'\b(404|401)\b', error_str))
    
    if is_non_retriable:
        # Don't retry - send error immediately
        _write_to_log(f"\n---\n\n**[{agent.upper()}] API Error:**\n\n> {error_str}\n\n")
        
        # Send error message to bridge for display in execution log
        send_json("error", {"message": error_str})
        
        # Save usage stats before returning (system will exit)
        _save_stats_on_system_interrupt()
        return False
    
    # For retriable errors, proceed with retry logic
    error_msg = f"API connection error (attempt {current_count}/{max_retries}): {error_str}"
    _write_to_log(f"\n---\n\n**[{agent.upper()}] API Error:**\n\n> {error_msg}\n\n")
    
    # Send status update to Node.js CLI - this replaces the current tool status
    retry_status = f"API Error - Retrying ({current_count}/{max_retries})..."
    send_agent_event(agent, "update", retry_status)
    
    if current_count >= max_retries:
        # Log final failure
        final_msg = f"System interrupted due to persistent API connection errors after {max_retries} retries."
        _write_to_log(f"\n---\n\n**[{agent.upper()}] Fatal Error:**\n\n> {final_msg}\n\n")
        
        # Send error message to bridge for display in execution log
        send_json("error", {"message": error_str})
        
        # Save usage stats before raising (system will exit)
        _save_stats_on_system_interrupt()
        
        # Raise fatal error to terminate the run
        raise FatalAPIError(final_msg)
    
    # Wait before retry
    time.sleep(wait_seconds)
    return True


def _save_stats_on_system_interrupt():
    """Save usage stats when system is interrupted by an error.
    
    This is called when the system needs to exit due to API failures or other
    fatal errors, ensuring usage data is preserved.
    """
    try:
        from ...usage_tracker import save_stats_to_checkpoint, set_run_status, end_run
        
        # Set status to interrupted
        set_run_status("interrupted")
        
        # Save token stats to checkpoint
        save_stats_to_checkpoint()
        
        # Note: Usage report is only generated on resume or hardware change as requested
        
        # End run timing
        end_run()
    except Exception:
        pass  # Fail silently - don't disrupt the error handling flow

