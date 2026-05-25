"""Shared context-window configuration and usage helpers."""

from __future__ import annotations

import os
from typing import Optional


# Per-model maximum context lengths (in tokens).
# Keys are exact model names (case-insensitive match).
MODEL_MAX_CONTEXT: dict[str, int] = {
    "gemini-2.5-pro": 1_048_576,
    "gemini-2.5-flash": 1_048_576,
    "gemini-3.5-flash": 1_048_576,
    "gemini-3.1-pro-preview": 1_048_576,
    "gemini-3-flash-preview": 1_048_576,
}

CONTEXT_THRESHOLD_RATIOS: dict[str, float] = {
    "low": 0.20,
    "medium": 0.40,
    "hard": 0.60,
}

DEFAULT_CONTEXT_THRESHOLD_LEVEL = "medium"
DEFAULT_CONTEXT_THRESHOLD_RATIO = CONTEXT_THRESHOLD_RATIOS[DEFAULT_CONTEXT_THRESHOLD_LEVEL]


def normalize_context_threshold_level(value: Optional[str]) -> str:
    """Normalize a context-threshold level, falling back to the default."""
    normalized = (value or "").strip().lower()
    if normalized in CONTEXT_THRESHOLD_RATIOS:
        return normalized
    return DEFAULT_CONTEXT_THRESHOLD_LEVEL


def get_context_threshold_level(value: Optional[str] = None) -> str:
    """Return the active context-threshold level."""
    raw_value = os.getenv("CONTEXT_THRESHOLD") if value is None else value
    return normalize_context_threshold_level(raw_value)


def get_context_threshold_ratio(value: Optional[str] = None) -> float:
    """Return the active context-threshold ratio."""
    return CONTEXT_THRESHOLD_RATIOS[get_context_threshold_level(value)]


def get_model_max_context(model_name: str) -> Optional[int]:
    """Return the max context length for a model, or None if not registered."""
    return MODEL_MAX_CONTEXT.get((model_name or "").lower())


def get_restricted_context_limit(model_name: str, threshold_level: Optional[str] = None) -> Optional[int]:
    """Return the effective context-compression limit for a model."""
    max_context = get_model_max_context(model_name)
    if max_context is None:
        return None
    return int(max_context * get_context_threshold_ratio(threshold_level))


def build_context_usage_snapshot(
    *,
    input_tokens: int = 0,
    model_name: Optional[str] = None,
    agent_name: str = "",
    threshold_level: Optional[str] = None,
) -> dict:
    """Build a UI-friendly snapshot of restricted context-window usage."""
    normalized_input_tokens = max(int(input_tokens or 0), 0)
    normalized_threshold_level = get_context_threshold_level(threshold_level)
    threshold_ratio = CONTEXT_THRESHOLD_RATIOS[normalized_threshold_level]
    effective_model = model_name or os.getenv("MODEL", "")
    max_context_tokens = get_model_max_context(effective_model)
    threshold_tokens = (
        int(max_context_tokens * threshold_ratio)
        if max_context_tokens is not None
        else None
    )

    usage_percent = None
    if threshold_tokens:
        usage_percent = round((normalized_input_tokens / threshold_tokens) * 100, 1)

    max_context_percent = None
    if max_context_tokens:
        max_context_percent = round((normalized_input_tokens / max_context_tokens) * 100, 1)

    remaining_tokens = None
    if threshold_tokens is not None:
        remaining_tokens = max(threshold_tokens - normalized_input_tokens, 0)

    return {
        "agent": agent_name,
        "model": effective_model,
        "threshold_level": normalized_threshold_level,
        "threshold_ratio": threshold_ratio,
        "threshold_percent": int(threshold_ratio * 100),
        "max_context_tokens": max_context_tokens,
        "threshold_tokens": threshold_tokens,
        "input_tokens": normalized_input_tokens,
        "usage_percent": usage_percent,
        "max_context_percent": max_context_percent,
        "remaining_tokens": remaining_tokens,
        "is_supported_model": max_context_tokens is not None,
        "is_over_limit": bool(threshold_tokens is not None and normalized_input_tokens >= threshold_tokens),
    }
