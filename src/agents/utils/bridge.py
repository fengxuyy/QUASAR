"""
Bridge communication utilities for CLI/web interface.
"""

import sys
from typing import Any

from ...state import State

_EMPTY_CONTEXT_USAGE_SEED = {
    "input_tokens": 0,
    "agent_name": "",
}
_last_context_usage_seed = dict(_EMPTY_CONTEXT_USAGE_SEED)


def remember_context_usage_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Store the latest context-usage seed for reconnect/replay scenarios."""
    global _last_context_usage_seed

    if not isinstance(payload, dict):
        return dict(_last_context_usage_seed)

    try:
        input_tokens = max(int(payload.get("input_tokens") or 0), 0)
    except (TypeError, ValueError):
        input_tokens = 0

    agent_name = payload.get("agent") or ""
    _last_context_usage_seed = {
        "input_tokens": input_tokens,
        "agent_name": str(agent_name),
    }
    return dict(_last_context_usage_seed)


def get_last_context_usage_seed() -> dict[str, Any]:
    """Return the most recently recorded context-usage seed."""
    return dict(_last_context_usage_seed)


def reset_context_usage_seed() -> dict[str, Any]:
    """Clear the cached context-usage seed."""
    global _last_context_usage_seed
    _last_context_usage_seed = dict(_EMPTY_CONTEXT_USAGE_SEED)
    return dict(_last_context_usage_seed)


def build_replayed_context_usage_payload(
    *,
    input_tokens: int | None = None,
    agent_name: str | None = None,
    model_name: str | None = None,
) -> dict[str, Any]:
    """Rebuild a context-usage snapshot from the last recorded seed."""
    from ...context_budget import build_context_usage_snapshot
    from ...context_summarizer import get_effective_model_name

    seed = get_last_context_usage_seed()
    effective_agent_name = seed["agent_name"] if agent_name is None else agent_name
    effective_input_tokens = seed["input_tokens"] if input_tokens is None else input_tokens
    effective_model_name = get_effective_model_name(
        agent_name=str(effective_agent_name or ""),
        model_name=model_name,
    )

    return build_context_usage_snapshot(
        input_tokens=int(effective_input_tokens or 0),
        model_name=effective_model_name,
        agent_name=str(effective_agent_name or ""),
    )


def plan_review_confirm_node(state: State) -> dict:
    """Wait for CLI review confirmation before operator execution begins."""
    bridge = sys.modules.get("bridge")
    if bridge is None:
        confirmation = {"action": "confirm", "feedback": ""}
    else:
        confirmation = bridge.begin_plan_confirmation_wait()

    action = confirmation.get("action", "confirm")
    feedback = (confirmation.get("feedback", "") or "").strip()

    if action == "confirm":
        return {
            "plan_review_proceed": True,
            "plan_review_action": "confirm",
            "plan_review_feedback": "",
        }

    if action == "revise":
        return {
            "plan_review_proceed": False,
            "plan_review_action": "revise",
            "plan_review_feedback": feedback,
        }

    user_request = state.get("user_input", "") or ""
    bridge = sys.modules.get("bridge")
    if bridge is not None:
        bridge.mark_plan_declined(user_request)
        bridge.send_json("plan_declined", {"user_input": user_request})

    return {
        "plan_review_proceed": False,
        "plan_review_action": "decline",
        "plan_review_feedback": "",
    }


def send_agent_event(
    agent: str,
    event: str,
    status: str = "",
    is_error: bool = False,
    output: str = "",
    user_feedback: str = "",
    tool_name: str = "",
) -> None:
    """Send agent lifecycle event to CLI.
    
    Args:
        agent: Agent name (e.g., 'operator', 'evaluator')
        event: Event type (e.g., 'step_complete', 'update', 'start', 'complete')
        status: Status text to display
        is_error: Whether this event represents an error (for step_complete display)
        output: Optional output text to show in collapsible section (for step_complete events)
        user_feedback: Optional user request (e.g. plan revision feedback for the web UI)
        tool_name: Optional tool id for error events (e.g. execute_python for validation failures)
    """
    bridge = sys.modules.get("bridge")
    if bridge is not None:
        try:
            bridge.send_agent_event(
                agent, event, status, is_error, output, user_feedback, tool_name
            )
        except Exception:
            pass


def send_json(type_: str, payload: dict) -> None:
    """Send JSON message to CLI."""
    bridge = sys.modules.get("bridge")
    if bridge is not None:
        try:
            bridge.send_json(type_, payload)
        except Exception:
            pass


def send_context_usage(payload: dict) -> None:
    """Send a context-usage snapshot to the active UI."""
    remember_context_usage_payload(payload)
    send_json("context_usage", payload)


def send_plan_stream(content: str, is_complete: bool = False, parsed_plan: list = None, is_replanning: bool = False) -> None:
    """Send streaming plan content to CLI.
    
    Args:
        content: Raw streaming content (for display during streaming)
        is_complete: Whether the plan is complete
        parsed_plan: Optional list of parsed task strings (sent when complete)
        is_replanning: Whether this is a replanning operation (vs initial plan or review)
    """
    bridge = sys.modules.get("bridge")
    if bridge is not None:
        try:
            bridge.send_plan_stream(content, is_complete, parsed_plan, is_replanning)
        except Exception:
            pass


def send_text_stream(agent: str, content: str, is_complete: bool = False) -> None:
    """Send streaming LLM text content to CLI.
    
    Args:
        agent: Agent name (e.g., 'operator', 'evaluator')
        content: Accumulated text content
        is_complete: Whether the streaming is complete
    """
    bridge = sys.modules.get("bridge")
    if bridge is not None:
        try:
            bridge.send_text_stream(agent, content, is_complete)
        except Exception:
            pass


def send_thought_stream(agent: str, content: str, is_complete: bool = False) -> None:
    """Send streaming LLM thought content to CLI.
    
    Args:
        agent: Agent name (e.g., 'operator', 'evaluator')
        content: Accumulated thought content
        is_complete: Whether the streaming is complete
    """
    bridge = sys.modules.get("bridge")
    if bridge is not None:
        try:
            bridge.send_thought_stream(agent, content, is_complete)
        except Exception:
            pass
