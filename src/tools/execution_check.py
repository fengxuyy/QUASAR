"""
Execution check tools for LLM to decide whether to continue or interrupt running Python executions.
"""

import re
from typing import Optional

from langchain_core.tools import tool

from .execution import execute_python_with_state_preserved


CHECKIN_TEMP_TIMEOUT_MINUTES = 5.0
FORBIDDEN_TEMP_PYTHON_PATTERNS = (
    (r"\bimport\s+subprocess\b|\bfrom\s+subprocess\b", "the subprocess module"),
    (r"\b(?:__import__|importlib\.import_module)\s*\(\s*['\"]subprocess['\"]\s*\)", "the subprocess module"),
    (r"\bos\.system\s*\(", "os.system"),
    (r"\bos\.popen\s*\(", "os.popen"),
    (r"\bimport\s+multiprocessing\b|\bfrom\s+multiprocessing\b", "multiprocessing"),
    (r"\b(?:__import__|importlib\.import_module)\s*\(\s*['\"]multiprocessing['\"]\s*\)", "multiprocessing"),
    (r"\basyncio\.create_subprocess(?:_exec|_shell)?\b", "asyncio subprocess helpers"),
    (r"\bopen\s*\([^)]*,\s*['\"][^'\"]*[wax+][^'\"]*['\"]", "file writes via open(...)"),
    (r"\bopen\s*\([^)]*mode\s*=\s*['\"][^'\"]*[wax+][^'\"]*['\"]", "file writes via open(...)"),
    (r"\.open\s*\(\s*['\"][^'\"]*[wax+][^'\"]*['\"]", "file writes via Path.open(...)"),
    (r"\.open\s*\([^)]*mode\s*=\s*['\"][^'\"]*[wax+][^'\"]*['\"]", "file writes via Path.open(...)"),
    (r"\.(?:write_text|write_bytes|unlink|rename|replace|mkdir|touch|chmod|rmdir|symlink_to|hardlink_to)\s*\(", "filesystem mutation helpers"),
    (r"\bos\.(?:remove|unlink|rename|replace|mkdir|makedirs|rmdir|removedirs|chmod)\s*\(", "os filesystem mutation helpers"),
    (r"\bshutil\.(?:rmtree|move|copy|copy2|copytree)\s*\(", "shutil filesystem mutation helpers"),
)


@tool
def continue_execution(summary: str = "") -> str:
    """Continue the currently running Python execution.
    
    Call this when the execution should continue running for another check-in interval.
    The script will continue running and you will be prompted again after the next interval.

    Args:
        summary: Brief summary of the current execution stage and why it is safe to continue.
    
    Returns:
        Confirmation message that execution will continue.
    """
    return "CONTINUE_EXECUTION"


@tool
def execute_temporary_python(
    code: str,
    file_path: str = "",
    timeout: Optional[float] = None,
) -> str:
    """Execute a short-lived temporary Python snippet during a check-in.

    Use this only to parse existing result files and determine simulation status.
    Do not launch subprocesses, start new simulations, or make long-running changes.
    This always runs with a fixed 5-minute timeout.

    Args:
        code: Temporary Python code that reads/parses existing outputs.
        file_path: Not allowed for this tool. Temporary check-in parsing must use inline code only.
        timeout: Not allowed for this tool. The timeout is fixed at 5 minutes.

    Returns:
        Execution results including stdout, stderr, and exit code.
    """
    if not code or not code.strip():
        return "Error: 'code' must be provided."
    if file_path:
        return (
            "Error: 'file_path' is not supported for execute_temporary_python. "
            "Use inline code only so check-in parsing remains temporary."
        )
    if timeout is not None:
        return (
            "Error: 'timeout' is fixed for execute_temporary_python. "
            "Do not override it; this tool always uses a 5-minute timeout."
        )

    for pattern, label in FORBIDDEN_TEMP_PYTHON_PATTERNS:
        if re.search(pattern, code):
            return (
                f"Error: Temporary check-in Python cannot use {label}. "
                "Use it only to parse existing results and determine simulation status without modifying files or the system."
            )

    return execute_python_with_state_preserved(
        timeout=CHECKIN_TEMP_TIMEOUT_MINUTES,
        code=code,
    )


@tool
def interrupt_execution(reason: str) -> str:
    """Interrupt and terminate the currently running Python execution.
    
    Call this when the execution should be stopped. The process will be terminated
    and any partial output will be returned.
    
    # Use this when:
    # - Anomalies are detected: For example, calculations not converging, unphysical values, important warnings, or errors that undermine the goals of the current simulation.
    # - Resource health issues occur: If you observe the system is idle, unresponsive, or exhibiting sustained low CPU/GPU utilization (which may indicate the process is stuck or has stalled), interrupt the execution.
    
    Args:
        reason: A clear explanation of why the execution is being interrupted.
                This will be recorded in the execution history.
    
    Returns:
        Confirmation message that execution will be interrupted, including the reason.
    """
    return f"INTERRUPT_EXECUTION: {reason}"
