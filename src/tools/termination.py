"""
Task-related LangChain tools shared across agents.
"""

from typing import Literal
from langchain_core.tools import tool


@tool
def complete_task() -> str:
    """Signal that the current operator task is completed."""
    return "**Task Completion:**\n> Task completion recorded: DONE."


@tool
def submit_evaluation(status: Literal["pass", "fail"], summary: str) -> str:
    """Submit the evaluator decision for the current task.
    
    Args:
        status: Either "pass" if all requirements are satisfied, or "fail" otherwise.
        summary: One paragraph summarizing the evaluation (evidence or issues).
    """
    if not summary or not summary.strip():
        return "**Submit Evaluation:**\n> Error: Summary is required. Please provide a summary of your evaluation."
    return f"**Submit Evaluation:** {status.upper()}\n\n> {summary[:200]}..."
