"""Prompt registry and selector primitives for dynamic-v2 assembly."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from .types import PromptAgent, PromptSection, PromptStability


PromptLayer = Literal["system", "context", "runtime"]
PromptCachePolicy = Literal["static", "session", "task", "runtime", "uncached"]


@dataclass(frozen=True)
class PromptContext:
    """Context available when deciding which prompt sections to render."""

    agent: PromptAgent
    phase: str
    run_state: dict[str, Any] = field(default_factory=dict)
    task_index: int | None = None
    tool_names: tuple[str, ...] = ()
    granularity_level: str = ""
    accuracy_mode: str = ""
    rag_enabled: bool | None = None
    hardware_info: str = ""


RenderFn = Callable[[PromptContext], str]
IncludeFn = Callable[[PromptContext], bool]


@dataclass(frozen=True)
class PromptSectionSpec:
    """Declarative prompt section recipe used by the selector."""

    id: str
    agent: PromptAgent
    layer: PromptLayer
    stability: PromptStability
    priority: int
    cache_policy: PromptCachePolicy
    render: RenderFn
    include: IncludeFn | None = None
    dependencies: tuple[str, ...] = ()

    def should_include(self, context: PromptContext) -> bool:
        if self.agent != context.agent:
            return False
        if self.include is None:
            return True
        return bool(self.include(context))

    def render_section(self, context: PromptContext) -> PromptSection:
        return PromptSection(
            id=self.id,
            content=self.render(context),
            agent=self.agent,
            stability=self.stability,
        )


@dataclass(frozen=True)
class PromptSelection:
    """Resolved section list plus debug metadata."""

    sections: list[PromptSection]
    selected: list[dict[str, Any]]
    skipped: list[dict[str, Any]]

    @property
    def render_order(self) -> list[str]:
        return [section.id for section in self.sections]


class PromptSelector:
    """Resolve prompt section specs in deterministic priority/id order."""

    def select(
        self,
        context: PromptContext,
        specs: list[PromptSectionSpec],
    ) -> PromptSelection:
        sections: list[PromptSection] = []
        selected: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []

        for spec in sorted(specs, key=lambda item: (item.priority, item.id)):
            if not spec.should_include(context):
                skipped.append(self._spec_metadata(spec, reason="include_predicate_false"))
                continue

            section = spec.render_section(context)
            sections.append(section)
            selected.append({
                **self._spec_metadata(spec, reason="selected"),
                "length": section.length,
                "hash": section.hash,
            })

        return PromptSelection(sections=sections, selected=selected, skipped=skipped)

    @staticmethod
    def _spec_metadata(spec: PromptSectionSpec, *, reason: str) -> dict[str, Any]:
        return {
            "id": spec.id,
            "agent": spec.agent,
            "layer": spec.layer,
            "stability": spec.stability,
            "priority": spec.priority,
            "cache_policy": spec.cache_policy,
            "dependencies": list(spec.dependencies),
            "reason": reason,
        }


DEFAULT_SELECTOR = PromptSelector()
