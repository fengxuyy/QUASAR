"""Prompt profile metadata helpers."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .types import PromptAssembly

PROMPT_PROFILE = "dynamic-v2"
PROMPT_VERSION = "2026-05-19.1"


def initial_prompt_metadata() -> dict[str, Any]:
    """Metadata stored with new runs."""
    return {
        "profile": PROMPT_PROFILE,
        "version": PROMPT_VERSION,
        "agents": {},
    }


def prompt_identity_from_state(state: dict | None) -> tuple[str, str]:
    """Return the prompt profile/version pinned to this run."""
    state = state or {}
    profile = state.get("prompt_profile") or PROMPT_PROFILE
    version = state.get("prompt_version") or PROMPT_VERSION
    return profile, version


def prompt_metadata_update(
    state: dict | None,
    assembly: PromptAssembly,
) -> dict[str, Any]:
    """Merge one assembly's diagnostics into run prompt metadata."""
    state = state or {}
    profile = state.get("prompt_profile") or assembly.profile
    version = state.get("prompt_version") or assembly.version
    metadata = deepcopy(state.get("prompt_metadata") or {})
    metadata.setdefault("profile", profile)
    metadata.setdefault("version", version)
    metadata.setdefault("agents", {})
    metadata["agents"][assembly.agent] = assembly.metadata()
    return {
        "prompt_profile": profile,
        "prompt_version": version,
        "prompt_metadata": metadata,
    }
