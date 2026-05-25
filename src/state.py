"""
State definition for the strategist-operator architecture.
"""

from typing import Annotated, Literal
from typing_extensions import TypedDict, NotRequired
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage

from .prompting.metadata import PROMPT_PROFILE, PROMPT_VERSION, initial_prompt_metadata


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
    prompt_profile: str  # Prompt assembly profile pinned to this run
    prompt_version: str  # Prompt assembly version pinned to this run
    prompt_metadata: dict  # Debug-only prompt section/injection metadata
    prompt_runtime_events: list[dict]  # Task/run scoped prompt events for rehydration after summarization
    resume_steering: NotRequired[str]  # User message provided while resuming an interrupted run
    plan_review_proceed: NotRequired[bool]  # Set by plan_review_confirm gate for routing
    plan_review_action: NotRequired[Literal["confirm", "decline", "revise"]]  # Latest plan-confirmation decision
    plan_review_feedback: NotRequired[str]  # User feedback for revising the reviewed plan


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
        "prompt_profile": PROMPT_PROFILE,
        "prompt_version": PROMPT_VERSION,
        "prompt_metadata": initial_prompt_metadata(),
        "prompt_runtime_events": [],
    }
