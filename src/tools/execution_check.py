"""
Execution check tools for LLM to decide whether to continue or interrupt running Python executions.
"""

from langchain_core.tools import tool


@tool
def continue_execution() -> str:
    """Continue the currently running Python execution.
    
    Call this when the execution should continue running for another check-in interval.
    The script will continue running and you will be prompted again after the next interval.
    
    Returns:
        Confirmation message that execution will continue.
    """
    return "CONTINUE_EXECUTION"


@tool
def interrupt_execution(reason: str) -> str:
    """Interrupt and terminate the currently running Python execution.
    
    Call this when the execution should be stopped. The process will be terminated
    and any partial output will be returned.
    
    Use this when:
    - The script has been running too long without progress
    - You've determined the script is stuck in an infinite loop
    - Resource constraints require stopping the execution
    - The intermediate results suggest the approach needs to change
    
    Args:
        reason: A clear explanation of why the execution is being interrupted.
                This will be recorded in the execution history.
    
    Returns:
        Confirmation message that execution will be interrupted, including the reason.
    """
    return f"INTERRUPT_EXECUTION: {reason}"
