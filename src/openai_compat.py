"""OpenAI-compatible LangChain helpers used by QUASAR."""

from __future__ import annotations

import json
from typing import Any, Mapping, cast

from langchain_core.messages import (
    AIMessageChunk,
    BaseMessageChunk,
    ChatMessageChunk,
    FunctionMessageChunk,
    HumanMessageChunk,
    SystemMessageChunk,
    ToolMessageChunk,
)
from langchain_core.messages.tool import tool_call_chunk
from langchain_core.outputs import ChatGenerationChunk

try:
    from langchain_openai import ChatOpenAI as _ImportedChatOpenAI
except Exception:
    _ImportedChatOpenAI = object

try:
    from langchain_openai.chat_models.base import _create_usage_metadata
except Exception:
    def _create_usage_metadata(token_usage, _service_tier=None):
        return token_usage


LangChainChatOpenAI = (
    _ImportedChatOpenAI if isinstance(_ImportedChatOpenAI, type) else object
)


def _stringify_reasoning_delta(value: Any) -> str:
    """Convert provider-specific reasoning payloads to plain text."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = [_stringify_reasoning_delta(item) for item in value]
        return "".join(part for part in parts if part)
    if isinstance(value, dict):
        for key in ("thinking", "reasoning", "reasoning_content", "text", "content"):
            nested = _stringify_reasoning_delta(value.get(key))
            if nested:
                return nested
        try:
            return json.dumps(value, ensure_ascii=False)
        except TypeError:
            return str(value)
    return str(value)


def _extract_reasoning_from_delta(delta: Mapping[str, Any]) -> str:
    """Read the reasoning field emitted by OpenAI-compatible streaming APIs."""
    for key in ("reasoning", "reasoning_content", "thinking"):
        reasoning_text = _stringify_reasoning_delta(delta.get(key))
        if reasoning_text:
            return reasoning_text
    return ""


def _convert_delta_to_message_chunk_with_reasoning(
    delta: Mapping[str, Any],
    default_class: type[BaseMessageChunk],
) -> BaseMessageChunk:
    """Convert an OpenAI delta into a LangChain chunk while preserving reasoning."""
    id_ = delta.get("id")
    role = cast(str, delta.get("role"))
    content = cast(str, delta.get("content") or "")
    additional_kwargs: dict[str, Any] = {}

    reasoning_text = _extract_reasoning_from_delta(delta)
    if reasoning_text:
        additional_kwargs["reasoning"] = reasoning_text

    if delta.get("function_call"):
        function_call = dict(delta["function_call"])
        if "name" in function_call and function_call["name"] is None:
            function_call["name"] = ""
        additional_kwargs["function_call"] = function_call

    tool_call_chunks = []
    if raw_tool_calls := delta.get("tool_calls"):
        try:
            tool_call_chunks = [
                tool_call_chunk(
                    name=raw_tool_call["function"].get("name"),
                    args=raw_tool_call["function"].get("arguments"),
                    id=raw_tool_call.get("id"),
                    index=raw_tool_call["index"],
                )
                for raw_tool_call in raw_tool_calls
            ]
        except KeyError:
            pass

    if role == "user" or default_class == HumanMessageChunk:
        return HumanMessageChunk(content=content, id=id_)
    if role == "assistant" or default_class == AIMessageChunk:
        return AIMessageChunk(
            content=content,
            additional_kwargs=additional_kwargs,
            id=id_,
            tool_call_chunks=tool_call_chunks,  # type: ignore[arg-type]
        )
    if role in ("system", "developer") or default_class == SystemMessageChunk:
        if role == "developer":
            additional_kwargs = {"__openai_role__": "developer"}
        else:
            additional_kwargs = {}
        return SystemMessageChunk(
            content=content,
            id=id_,
            additional_kwargs=additional_kwargs,
        )
    if role == "function" or default_class == FunctionMessageChunk:
        return FunctionMessageChunk(content=content, name=delta["name"], id=id_)
    if role == "tool" or default_class == ToolMessageChunk:
        return ToolMessageChunk(
            content=content,
            tool_call_id=delta["tool_call_id"],
            id=id_,
        )
    if role or default_class == ChatMessageChunk:
        return ChatMessageChunk(content=content, role=role, id=id_)
    return default_class(content=content, id=id_)  # type: ignore[call-arg]


class QuasarChatOpenAI(LangChainChatOpenAI):
    """ChatOpenAI variant that preserves streamed reasoning deltas."""

    def _convert_chunk_to_generation_chunk(
        self,
        chunk: dict,
        default_chunk_class: type,
        base_generation_info: dict | None,
    ) -> ChatGenerationChunk | None:
        if chunk.get("type") == "content.delta":
            return None

        token_usage = chunk.get("usage")
        choices = chunk.get("choices", []) or chunk.get("chunk", {}).get("choices", [])

        usage_metadata = (
            _create_usage_metadata(token_usage, chunk.get("service_tier"))
            if token_usage
            else None
        )

        if len(choices) == 0:
            generation_chunk = ChatGenerationChunk(
                message=default_chunk_class(content="", usage_metadata=usage_metadata),
                generation_info=base_generation_info,
            )
            if self.output_version == "v1":
                generation_chunk.message.content = []
                generation_chunk.message.response_metadata["output_version"] = "v1"
            return generation_chunk

        choice = choices[0]
        if choice["delta"] is None:
            return None

        message_chunk = _convert_delta_to_message_chunk_with_reasoning(
            choice["delta"],
            default_chunk_class,
        )
        generation_info = {**base_generation_info} if base_generation_info else {}

        if finish_reason := choice.get("finish_reason"):
            generation_info["finish_reason"] = finish_reason
            if model_name := chunk.get("model"):
                generation_info["model_name"] = model_name
            if system_fingerprint := chunk.get("system_fingerprint"):
                generation_info["system_fingerprint"] = system_fingerprint
            if service_tier := chunk.get("service_tier"):
                generation_info["service_tier"] = service_tier
            if isinstance(message_chunk, AIMessageChunk):
                message_chunk.chunk_position = "last"

        if logprobs := choice.get("logprobs"):
            generation_info["logprobs"] = logprobs

        if usage_metadata and isinstance(message_chunk, AIMessageChunk):
            message_chunk.usage_metadata = usage_metadata

        message_chunk.response_metadata["model_provider"] = "openai"
        return ChatGenerationChunk(
            message=message_chunk,
            generation_info=generation_info or None,
        )
