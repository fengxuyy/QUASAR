"""Prompt assembly helpers for QUASAR agents."""

from .builders import (
    build_checkin_control_reminder_injection,
    build_checkin_empty_response_injection,
    build_checkin_history_message,
    build_checkin_prompt_injection,
    build_evaluation_feedback_injection,
    build_evaluator_messages,
    build_evaluator_repeated_tool_warning_injection,
    build_hardware_change_injection,
    build_operator_messages,
    build_operator_repeated_tool_warning_injection,
    build_resume_steering_injection,
    build_strategist_review_prompt,
    build_strategist_messages,
    build_strategist_repeated_tool_warning_injection,
    build_summarized_checkin_reminder_injection,
)
from .events import (
    active_prompt_events,
    clear_prompt_runtime_events_for_task,
    merge_prompt_events_from_messages,
    rehydrate_prompt_runtime_events,
    upsert_prompt_runtime_event,
)
from .metadata import (
    PROMPT_PROFILE,
    PROMPT_VERSION,
    initial_prompt_metadata,
    prompt_identity_from_state,
    prompt_metadata_update,
)
from .registry import PromptContext, PromptSectionSpec, PromptSelector
from .types import PromptAssembly, PromptInjection, PromptSection

__all__ = [
    "PROMPT_PROFILE",
    "PROMPT_VERSION",
    "PromptAssembly",
    "PromptContext",
    "PromptInjection",
    "PromptSection",
    "PromptSectionSpec",
    "PromptSelector",
    "active_prompt_events",
    "build_checkin_control_reminder_injection",
    "build_checkin_empty_response_injection",
    "build_checkin_history_message",
    "build_checkin_prompt_injection",
    "build_evaluation_feedback_injection",
    "build_evaluator_messages",
    "build_evaluator_repeated_tool_warning_injection",
    "build_hardware_change_injection",
    "build_operator_messages",
    "build_operator_repeated_tool_warning_injection",
    "build_resume_steering_injection",
    "build_strategist_review_prompt",
    "build_strategist_messages",
    "build_strategist_repeated_tool_warning_injection",
    "build_summarized_checkin_reminder_injection",
    "clear_prompt_runtime_events_for_task",
    "initial_prompt_metadata",
    "merge_prompt_events_from_messages",
    "prompt_identity_from_state",
    "prompt_metadata_update",
    "rehydrate_prompt_runtime_events",
    "upsert_prompt_runtime_event",
]
