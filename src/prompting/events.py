"""Lifecycle-aware prompt runtime events."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage

from .types import PromptAgent, PromptEventScope, PromptInjection


def prompt_event_from_injection(
    injection: PromptInjection,
    *,
    task_index: int | None = None,
) -> dict[str, Any]:
    """Serialize a task/run scoped injection for checkpoint state."""
    return {
        **injection.metadata(),
        "content": injection.content,
        "task_index": task_index,
    }


def prompt_event_from_message(
    message: BaseMessage,
    *,
    task_index: int | None = None,
) -> dict[str, Any] | None:
    """Extract serialized event metadata from a rendered HumanMessage."""
    if not isinstance(message, HumanMessage):
        return None
    event = getattr(message, "additional_kwargs", {}).get("quasar_prompt_event")
    if not isinstance(event, dict) or not event.get("id"):
        return None

    serialized = deepcopy(event)
    serialized["content"] = getattr(message, "content", "")
    serialized.setdefault("task_index", task_index)
    return serialized


def injection_from_prompt_event(event: dict[str, Any]) -> PromptInjection:
    """Rebuild a PromptInjection from checkpoint metadata."""
    return PromptInjection(
        id=event["id"],
        content=event.get("content", ""),
        agent=event.get("agent", "operator"),
        dedupe_key=event.get("dedupe_key"),
        stability=event.get("stability", "runtime"),
        scope=event.get("scope", "turn"),
    )


def _event_key(event: dict[str, Any]) -> tuple:
    return (
        event.get("agent"),
        event.get("id"),
        event.get("dedupe_key") or event.get("hash") or event.get("content"),
        event.get("scope"),
        event.get("task_index") if event.get("scope") == "task" else None,
    )


def upsert_prompt_runtime_event(
    events: list[dict[str, Any]] | None,
    injection: PromptInjection,
    *,
    task_index: int | None = None,
) -> list[dict[str, Any]]:
    """Add or replace a non-turn runtime event in checkpoint state."""
    current = list(events or [])
    if injection.scope == "turn":
        return current

    event = prompt_event_from_injection(injection, task_index=task_index)
    key = _event_key(event)
    kept = [existing for existing in current if _event_key(existing) != key]
    kept.append(event)
    return kept


def merge_prompt_events_from_messages(
    events: list[dict[str, Any]] | None,
    messages: list[BaseMessage],
    *,
    task_index: int | None = None,
) -> list[dict[str, Any]]:
    """Capture task/run scoped prompt events already present in messages."""
    current = list(events or [])
    keys = {_event_key(event) for event in current}

    for message in messages or []:
        event = prompt_event_from_message(message, task_index=task_index)
        if not event or event.get("scope") == "turn":
            continue
        key = _event_key(event)
        if key not in keys:
            current.append(event)
            keys.add(key)

    return current


def active_prompt_events(
    events: list[dict[str, Any]] | None,
    *,
    agent: PromptAgent | str,
    task_index: int | None = None,
) -> list[dict[str, Any]]:
    """Return events that should be visible to an agent at this point."""
    active: list[dict[str, Any]] = []
    for event in events or []:
        if event.get("agent") != agent:
            continue
        scope: PromptEventScope = event.get("scope", "turn")
        if scope == "run":
            active.append(event)
        elif scope == "task" and event.get("task_index") == task_index:
            active.append(event)
    return active


def rehydrate_prompt_runtime_events(
    messages: list[BaseMessage],
    events: list[dict[str, Any]] | None,
    *,
    agent: PromptAgent | str,
    task_index: int | None = None,
) -> tuple[list[BaseMessage], int]:
    """Append missing active task/run events after summarization."""
    updated = list(messages or [])
    appended = 0
    for event in active_prompt_events(events, agent=agent, task_index=task_index):
        injection = injection_from_prompt_event(event)
        if injection.is_present(updated):
            continue
        updated.append(injection.to_human_message())
        appended += 1
    return updated, appended


def clear_prompt_runtime_events_for_task(
    events: list[dict[str, Any]] | None,
    *,
    task_index: int,
) -> list[dict[str, Any]]:
    """Drop task-scoped runtime events after the task is complete."""
    return [
        event for event in events or []
        if not (event.get("scope") == "task" and event.get("task_index") == task_index)
    ]
