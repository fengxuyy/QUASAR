"""
Custom exceptions and error handling utilities.
"""

import re
import time
from typing import Any, Callable, TypeVar

from ...tools import LOGS_DIR
from .bridge import send_agent_event, send_json

T = TypeVar("T")


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

    def __init__(self, message: str, *, agent: str = "system"):
        super().__init__(message)
        self.agent = agent


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
    """Check if an exception is a known API error based on HTTP error codes or messages."""
    # API error codes to detect: 400 (Bad Request), 401 (Unauthorized), 403 (Forbidden),
    # 404 (Not Found - invalid model), 429 (Rate Limit), 499 (Client Closed Request),
    # 500 (Server Error), 502 (Bad Gateway), 503 (Service Unavailable), 504 (Gateway Timeout)
    api_error_codes = {400, 401, 403, 404, 429, 499, 500, 502, 503, 504}
    
    error_str = str(e)
    
    # Pattern 1: Look for "429 RESOURCE_EXHAUSTED" or "401 UNAUTHORIZED" or "404 NOT_FOUND" etc.
    code_match = re.search(r'\b(400|401|403|404|429|499|500|502|503|504)\b', error_str)
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
    return (
        "resource_exhausted" in error_str_lower
        or "connection error" in error_str_lower
        or is_non_retriable_api_error(e)
    )


def is_non_retriable_api_error(e: Exception) -> bool:
    """Return True for invalid credentials, permissions, or model names that will not self-heal on retry."""
    non_retriable_codes = {401, 403, 404}
    error_str = str(e)
    error_str_lower = error_str.lower()

    for attr in ("status_code", "code"):
        val = getattr(e, attr, None)
        if isinstance(val, int) and val in non_retriable_codes:
            return True

    if re.search(r'\b(401|403|404)\b', error_str):
        return True

    code_in_dict = re.search(r"'code':\s*(\d+)", error_str) or re.search(r'"code":\s*(\d+)', error_str)
    if code_in_dict and int(code_in_dict.group(1)) in non_retriable_codes:
        return True

    non_retriable_phrases = (
        "api_key_invalid",
        "api key not valid",
        "invalid api key",
        "invalid_api_key",
        "incorrect api key",
        "api key expired",
        "authentication_error",
        "invalid x-api-key",
        "permission_denied",
        "permission denied",
        "model_not_found",
        "model not found",
        "is not found for api version",
        "does not exist",
        "invalid model",
        "unknown model",
        "not a valid model",
    )
    return any(phrase in error_str_lower for phrase in non_retriable_phrases)


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
    Non-retriable authentication/model errors (e.g. 401/403/404, invalid API key)
    fail immediately with FatalAPIError instead of sitting in a retry loop.
    When retries are exhausted, saves usage stats and raises FatalAPIError.
    """
    from .logging import _write_to_log
    
    error_str = str(error)

    if is_non_retriable_api_error(error):
        final_msg = f"API request failed (check MODEL and MODEL_API_KEY in Settings): {error_str}"
        _write_to_log(f"\n---\n\n**[{agent.upper()}] Fatal API Error:**\n\n> {final_msg}\n\n")
        _save_stats_on_system_interrupt()
        raise FatalAPIError(final_msg, agent=agent)

    error_msg = f"API connection error (attempt {current_count}/{max_retries}): {error_str}"
    _write_to_log(f"\n---\n\n**[{agent.upper()}] API Error:**\n\n> {error_msg}\n\n")

    if current_count >= max_retries:
        # Log final failure
        final_msg = f"System interrupted due to persistent API connection errors after {max_retries} retries."
        _write_to_log(f"\n---\n\n**[{agent.upper()}] Fatal Error:**\n\n> {final_msg}\n\n")
        
        # Save usage stats before raising (system will exit)
        _save_stats_on_system_interrupt()
        
        # Raise fatal error to terminate the run
        raise FatalAPIError(
            f"{final_msg}\n\nLast API error: {error_str}",
            agent=agent,
        )

    # Send status update to Node.js CLI - this replaces the current tool status
    retry_status = f"API Error - Retrying ({current_count}/{max_retries})..."
    send_agent_event(
        agent,
        "update",
        retry_status,
        is_error=True,
        output=error_str,
    )
    
    # Wait before retry, but do not count retry backoff as active run time.
    # Respect bridge.interrupt_event if available so user Stop works immediately.
    from ...usage_tracker import begin_excluded_interval, end_excluded_interval

    interrupt_ev = None
    try:
        import bridge as _bridge
        interrupt_ev = getattr(_bridge, "interrupt_event", None)
    except Exception:
        interrupt_ev = None

    begin_excluded_interval()
    try:
        if interrupt_ev is not None and wait_seconds > 0:
            if interrupt_ev.wait(wait_seconds):
                raise KeyboardInterrupt("Interrupted during API retry backoff")
        else:
            time.sleep(wait_seconds)
    finally:
        end_excluded_interval()
    return True


def run_with_api_retries(
    agent: str,
    operation: Callable[[], T],
    *,
    max_retries: int = 3,
    wait_seconds: int = 120,
) -> T:
    """Run one model operation with the shared API retry policy."""
    api_error_count = 0

    while True:
        try:
            return operation()
        except FatalAPIError:
            raise
        except Exception as error:
            if not is_api_connection_error(error):
                raise
            api_error_count += 1
            handle_api_retry(
                agent,
                error,
                api_error_count,
                max_retries=max_retries,
                wait_seconds=wait_seconds,
            )


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
