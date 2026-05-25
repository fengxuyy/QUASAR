"""Typed prompt sections and runtime injections."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from typing import Literal

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage


PromptAgent = Literal["strategist", "operator", "evaluator", "checkin"]
PromptStability = Literal["static", "session", "task", "runtime"]
PromptEventScope = Literal["turn", "task", "run"]


def stable_hash(text: str) -> str:
    """Return a short stable hash for prompt diagnostics."""
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class PromptSection:
    """A named prompt section used by a system or context prompt."""

    id: str
    content: str
    agent: PromptAgent
    stability: PromptStability = "static"

    @property
    def hash(self) -> str:
        return stable_hash(self.content)

    @property
    def length(self) -> int:
        return len(self.content or "")


@dataclass(frozen=True)
class PromptInjection:
    """A typed runtime context item rendered into the message stream."""

    id: str
    content: str
    agent: PromptAgent
    dedupe_key: str | None = None
    stability: PromptStability = "runtime"
    scope: PromptEventScope = "turn"

    @property
    def hash(self) -> str:
        return stable_hash(self.content)

    @property
    def length(self) -> int:
        return len(self.content or "")

    def metadata(self) -> dict:
        return {
            "id": self.id,
            "agent": self.agent,
            "stability": self.stability,
            "scope": self.scope,
            "dedupe_key": self.dedupe_key,
            "length": self.length,
            "hash": self.hash,
        }

    def to_human_message(self) -> HumanMessage:
        return HumanMessage(
            content=self.content,
            additional_kwargs={"quasar_prompt_event": self.metadata()},
        )

    def is_present(self, messages: list[BaseMessage]) -> bool:
        needle = self.dedupe_key or self.content
        for message in messages or []:
            if not isinstance(message, HumanMessage):
                continue
            event = getattr(message, "additional_kwargs", {}).get("quasar_prompt_event")
            if isinstance(event, dict):
                same_id = event.get("id") == self.id
                same_dedupe = (
                    self.dedupe_key
                    and event.get("dedupe_key") == self.dedupe_key
                )
                if same_id and (not self.dedupe_key or same_dedupe):
                    return True
            if needle and needle in str(getattr(message, "content", "")):
                return True
        return False


@dataclass(frozen=True)
class PromptAssembly:
    """Rendered messages plus diagnostic prompt assembly metadata."""

    agent: PromptAgent
    messages: list[BaseMessage]
    sections: list[PromptSection] = field(default_factory=list)
    injections: list[PromptInjection] = field(default_factory=list)
    profile: str = "dynamic-v2"
    version: str = "2026-05-19.1"
    assembly_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    phase: str = ""
    render_order: list[str] = field(default_factory=list)
    selected_sections: list[dict] = field(default_factory=list)
    skipped_sections: list[dict] = field(default_factory=list)

    @property
    def content_hash(self) -> str:
        parts = []
        for message in self.messages:
            parts.append(f"{type(message).__name__}:{getattr(message, 'content', '')}")
        return stable_hash("\n\n".join(parts))

    def metadata(self) -> dict:
        return {
            "profile": self.profile,
            "version": self.version,
            "agent": self.agent,
            "phase": self.phase,
            "assembly_id": self.assembly_id,
            "message_hash": self.content_hash,
            "render_order": self.render_order or [section.id for section in self.sections],
            "selected_sections": self.selected_sections,
            "skipped_sections": self.skipped_sections,
            "sections": [
                {
                    "id": section.id,
                    "stability": section.stability,
                    "length": section.length,
                    "hash": section.hash,
                }
                for section in self.sections
            ],
            "injections": [
                {
                    "id": injection.id,
                    "stability": injection.stability,
                    "scope": injection.scope,
                    "dedupe_key": injection.dedupe_key,
                    "length": injection.length,
                    "hash": injection.hash,
                }
                for injection in self.injections
            ],
        }

    @classmethod
    def from_system_and_human(
        cls,
        *,
        agent: PromptAgent,
        system: PromptSection,
        human: PromptSection | PromptInjection,
        profile: str = "dynamic-v2",
        version: str = "2026-05-19.1",
        phase: str = "",
        render_order: list[str] | None = None,
        selected_sections: list[dict] | None = None,
        skipped_sections: list[dict] | None = None,
    ) -> "PromptAssembly":
        human_message = (
            human.to_human_message()
            if isinstance(human, PromptInjection)
            else HumanMessage(content=human.content)
        )
        return cls(
            agent=agent,
            messages=[SystemMessage(content=system.content), human_message],
            sections=[system] + ([] if isinstance(human, PromptInjection) else [human]),
            injections=[human] if isinstance(human, PromptInjection) else [],
            profile=profile,
            version=version,
            phase=phase,
            render_order=render_order or [],
            selected_sections=selected_sections or [],
            skipped_sections=skipped_sections or [],
        )


def append_injection(
    messages: list[BaseMessage],
    injection: PromptInjection,
) -> tuple[list[BaseMessage], bool]:
    """Append a prompt injection unless its dedupe key/content is already present."""
    current_messages = list(messages or [])
    if injection.is_present(current_messages):
        return current_messages, False
    return current_messages + [injection.to_human_message()], True
