"""Debug-only logging for prompt assembly."""

from __future__ import annotations

import json
import os
from datetime import datetime

from .types import PromptAssembly, PromptInjection


def _write_prompt_jsonl(kind: str, payload: dict) -> None:
    """Write structured prompt diagnostics when DEBUG logging is enabled."""
    if os.getenv("DEBUG", "0").lower() not in ("1", "true", "yes"):
        return
    try:
        from ..tools.base import LOGS_DIR

        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        entry = {
            "timestamp": datetime.now().isoformat(timespec="milliseconds"),
            "kind": kind,
            **payload,
        }
        with open(LOGS_DIR / "prompt_assembly.jsonl", "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def log_prompt_assembly(
    assembly: PromptAssembly,
    *,
    task_index: int | None = None,
    context: str = "",
) -> None:
    """Log prompt section/injection diagnostics without changing UI output."""
    try:
        from ..debug_logger import log_custom

        payload = assembly.metadata()
        payload["task_index"] = task_index
        if context:
            payload["context"] = context
        _write_prompt_jsonl("assembly", payload)
        log_custom("PROMPT_ASSEMBLY", f"{assembly.agent} prompt assembled", payload)
    except Exception:
        pass


def log_prompt_injection(
    injection: PromptInjection,
    *,
    task_index: int | None = None,
    context: str = "",
) -> None:
    """Log one runtime injection without changing UI output."""
    try:
        from ..debug_logger import log_custom

        payload = {
            "agent": injection.agent,
            "id": injection.id,
            "stability": injection.stability,
            "scope": injection.scope,
            "dedupe_key": injection.dedupe_key,
            "length": injection.length,
            "hash": injection.hash,
            "task_index": task_index,
        }
        if context:
            payload["context"] = context
        _write_prompt_jsonl("injection", payload)
        log_custom("PROMPT_INJECTION", f"{injection.agent} injection rendered", payload)
    except Exception:
        pass
