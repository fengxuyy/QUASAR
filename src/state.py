"""
State definition for the strategist-operator architecture.
"""

from typing import Annotated
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage


class State(TypedDict):
    """State for the strategist-operator graph."""
    messages: Annotated[list, add_messages]  # Global conversation history
    user_input: str  # Original user request (used by strategist to build proper message order)
    current_task_messages: list[BaseMessage] # Messages for the current task only (reset per task)
    plan: list[str]  # List of steps to execute
    completed_steps: list[str]  # Steps that have been completed
    step_results: dict[int, str]  # Results for each step (summaries)
    files_at_task_start: list[str]  # Files existing at the start of the current task
    evaluation_attempts: int  # Number of evaluation retry attempts for current task
    initial_plan_content: str  # Raw LLM response from initial planning (for checkpoint between phases)
    is_replanning: bool  # Whether in replanning mode (skip review phase)
    evaluation_messages: list[BaseMessage]  # Messages accumulated during evaluation (for checkpoint)


def create_initial_state(user_input: str) -> State:
    """Create initial state from user input."""
    return {
        "messages": [],  # Start empty - strategist adds SystemMessage + HumanMessage in correct order
        "user_input": user_input,  # Store separately for strategist to use
        "current_task_messages": [],
        "plan": [],
        "completed_steps": [],
        "step_results": {},
        "files_at_task_start": [],
        "evaluation_attempts": 0,
        "initial_plan_content": "",
        "is_replanning": False,
        "evaluation_messages": [],
    }
