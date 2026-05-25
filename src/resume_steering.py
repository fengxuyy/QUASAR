"""Helpers for applying user steering to an interrupted run."""

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from .prompting import build_resume_steering_injection


RESUME_STEERING_MARKER = "[USER STEERING WHILE RESUMING]"


def _normalise_next_nodes(next_nodes) -> list[str]:
    if not next_nodes:
        return []

    if isinstance(next_nodes, str):
        nodes = [next_nodes]
    else:
        try:
            nodes = list(next_nodes)
        except TypeError:
            nodes = [next_nodes]

    return [str(node).strip().strip("'\"").lower() for node in nodes]


def _has_operator_activity(state_values: dict) -> bool:
    """Infer active operator work from task-local messages."""
    plan = state_values.get("plan") or []
    completed_steps = state_values.get("completed_steps") or []
    if not plan or len(completed_steps) >= len(plan):
        return False

    # If evaluator has active local context, steering should stay unavailable.
    if state_values.get("evaluation_messages"):
        return False

    current_task_messages = state_values.get("current_task_messages") or []
    for message in current_task_messages:
        if isinstance(message, ToolMessage):
            return True
        if isinstance(message, AIMessage):
            content = getattr(message, "content", "")
            text = content.strip() if isinstance(content, str) else str(content).strip()
            if (text and text not in ("DONE", "GIVE_UP")) or getattr(message, "tool_calls", None):
                return True

    return False


def checkpoint_allows_resume_steering(next_nodes, state_values: dict | None = None) -> bool:
    """Return True only when the checkpoint belongs to operator work."""
    nodes = _normalise_next_nodes(next_nodes)

    if any(node == "operator" for node in nodes):
        return True

    non_operator_nodes = {
        "strategist_initial",
        "strategist_review",
        "plan_review_confirm",
        "evaluator_setup",
        "evaluator_loop",
        "__end__",
    }
    if any(
        node in non_operator_nodes
        or node.startswith("strategist")
        or node.startswith("evaluator")
        or "plan_review" in node
        for node in nodes
    ):
        return False

    if not isinstance(state_values, dict):
        return False

    return _has_operator_activity(state_values)


def checkpoint_is_strategist_stage(next_nodes, state_values: dict | None = None) -> bool:
    """Return True when a checkpoint is still in planning and has not started workspace work."""
    nodes = _normalise_next_nodes(next_nodes)
    strategist_nodes = {"strategist_initial", "strategist_review", "plan_review_confirm"}

    if not any(node in strategist_nodes or node.startswith("strategist") for node in nodes):
        return False

    if not isinstance(state_values, dict):
        return False

    # Replanning can happen after operator work. In that case resetting the run should still
    # clean up workspace artifacts produced by the earlier task execution.
    if state_values.get("completed_steps") or state_values.get("step_results"):
        return False
    if state_values.get("current_task_messages") or state_values.get("evaluation_messages"):
        return False
    if state_values.get("files_at_task_start"):
        return False

    return True


def build_resume_steering_message(steering: str) -> HumanMessage:
    """Build a compact task-local message for user steering supplied on resume."""
    return build_resume_steering_injection(steering).to_human_message()


def append_resume_steering_message(messages: list, steering: str) -> tuple[list, bool]:
    """Append steering to current task messages unless the exact note is already present."""
    steering = steering.strip()
    if not steering:
        return list(messages or []), False

    current_messages = list(messages or [])
    already_present = any(
        isinstance(message, HumanMessage)
        and RESUME_STEERING_MARKER in getattr(message, "content", "")
        and steering in getattr(message, "content", "")
        for message in current_messages
    )
    if already_present:
        return current_messages, False

    return current_messages + [build_resume_steering_message(steering)], True
