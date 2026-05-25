"""Context summarization for Gemini models.

When a Gemini model's context exceeds the configured restricted context
window, this module summarizes the conversation history and replaces it
with a compact summary to prevent context overflow.
"""

import os
from typing import Optional

from langchain_core.messages import SystemMessage, HumanMessage, BaseMessage

from .context_budget import (
    DEFAULT_CONTEXT_THRESHOLD_RATIO,
    MODEL_MAX_CONTEXT,
    build_context_usage_snapshot,
    get_context_threshold_ratio,
    get_model_max_context,
)
from .debug_logger import log_custom


CONTEXT_THRESHOLD_RATIO = DEFAULT_CONTEXT_THRESHOLD_RATIO


def _get_real_attr(obj, attr_name: str):
    """Read an actual attribute without triggering MagicMock child synthesis."""
    try:
        return object.__getattribute__(obj, attr_name)
    except AttributeError:
        return None
    except Exception:
        return getattr(obj, attr_name, None)


def _extract_summary_text(content_obj) -> str:
    """Normalize model response content into plain text for summaries."""
    if content_obj is None:
        return ""
    if isinstance(content_obj, str):
        return content_obj
    if isinstance(content_obj, list):
        parts = []
        for part in content_obj:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                text_val = part.get("text") or part.get("content") or ""
                if isinstance(text_val, str):
                    parts.append(text_val)
        return "".join(parts)
    if isinstance(content_obj, dict):
        text_val = content_obj.get("text") or content_obj.get("content") or ""
        return text_val if isinstance(text_val, str) else str(content_obj)
    return str(content_obj)


def _get_model_max_context(model_name: str) -> int | None:
    """Backward-compatible wrapper around the shared model-context lookup."""
    return get_model_max_context(model_name)


def is_gemini_model(model_name: str) -> bool:
    """Check if the given model name is a Gemini model."""
    return "gemini" in (model_name or "").lower()


def should_summarize_context(input_tokens: int, model_name: Optional[str] = None) -> bool:
    """Determine if context summarization should be triggered.
    
    Args:
        input_tokens: Number of input tokens from the most recent API call
                      (represents the full context size sent to the model).
        model_name: Name of the model. If None, reads from MODEL env var.
        
    Returns:
        True if summarization should be triggered, False otherwise.
    """
    if model_name is None:
        model_name = os.getenv("MODEL", "")
    
    max_context = _get_model_max_context(model_name)
    if max_context is None:
        return False
    
    threshold = int(max_context * get_context_threshold_ratio())
    return input_tokens >= threshold


def get_effective_model_name(agent_name: str = "", model_name: Optional[str] = None) -> str:
    """Resolve the active model name for an agent.

    Prefers an explicit model_name, then any per-agent override, then the primary
    MODEL environment variable.
    """
    if model_name:
        return model_name

    if agent_name:
        agent_model = os.getenv(f"{agent_name.upper()}_MODEL", "")
        if agent_model:
            return agent_model

    return os.getenv("MODEL", "")

# Summarization prompt template
_SUMMARIZATION_PROMPT = """You are a Context Compression Assistant. Your objective is to distill the conversation history into a high-density summary that allows an AI agent to seamlessly resume work without losing critical context.

Your summary MUST include:
1. **Key decisions made**: Chosen approaches and their rationale.
2. **Tools & Results**: Important file modifications, commands executed, and their outcomes.
3. **Progress**: Clearly delineated completed vs. pending tasks.
4. **Critical Context**: Exact file paths, precise error messages, domain variables, and scientific parameters.
5. **Current State**: The agent's exact focus right before this summary.

Maximize information density. Be concise, but do not drop any specific technical details, paths, or errors required to resume work seamlessly.

<CONVERSATION_HISTORY>
{history}
</CONVERSATION_HISTORY>

Provide your summary below:"""




def _format_messages_for_summary(messages: list[BaseMessage]) -> str:
    """Format messages into a text block for summarization.
    
    Skips SystemMessage (preserved separately) and formats each message
    with its role for clarity.
    """
    parts = []
    for msg in messages:
        if isinstance(msg, SystemMessage):
            continue
        
        # Determine role
        role = type(msg).__name__.replace("Message", "")
        content = getattr(msg, "content", "")
        
        # Truncate very long individual messages to keep the summarization prompt manageable
        if isinstance(content, str) and len(content) > 10000:
            content = content[:10000] + "\n... [truncated]"
        elif not isinstance(content, str):
            content = str(content)
        
        # Include tool call info if present
        tool_calls = getattr(msg, "tool_calls", None)
        tool_info = ""
        if tool_calls:
            tool_names = [tc.get("name", "unknown") for tc in tool_calls if isinstance(tc, dict)]
            if tool_names:
                tool_info = f" [Tool calls: {', '.join(tool_names)}]"
        
        # Include tool_call_id for ToolMessages
        tool_call_id = getattr(msg, "tool_call_id", None)
        id_info = f" (tool_call_id: {tool_call_id})" if tool_call_id else ""
        
        parts.append(f"[{role}{tool_info}{id_info}]: {content}")
    
    return "\n\n".join(parts)


def summarize_messages(
    messages: list[BaseMessage],
    llm,
    agent_name: str = "",
) -> list[BaseMessage]:
    """Summarize a message list, preserving the SystemMessage.
    
    Calls the LLM to produce a concise summary of the conversation,
    then returns a new message list: [original SystemMessage, HumanMessage(summary)].
    
    Args:
        messages: Current message list (must start with SystemMessage).
        llm: Base LLM instance (without tool bindings).
        agent_name: Agent name for logging and token tracking.
        
    Returns:
        New message list with [SystemMessage, HumanMessage(summary)].
    """
    from .usage_tracker import extract_cache_read_tokens, record_api_call
    
    # Extract the original SystemMessage(s)
    system_messages = [m for m in messages if isinstance(m, SystemMessage)]
    non_system_messages = [m for m in messages if not isinstance(m, SystemMessage)]
    
    if not non_system_messages:
        log_custom("CONTEXT_SUMMARIZER", "No non-system messages to summarize, skipping")
        return messages
    
    # Format conversation for summarization
    history_text = _format_messages_for_summary(messages)
    summarization_prompt = _SUMMARIZATION_PROMPT.format(history=history_text)
    
    log_custom("CONTEXT_SUMMARIZER", f"Summarizing {len(non_system_messages)} messages for {agent_name}", {
        "original_message_count": len(messages),
        "agent_name": agent_name,
    })
    
    try:
        llm_for_summary = _unwrap_llm_for_summarization(llm)

        # Call LLM for summarization (non-streaming for simplicity)
        summary_response = llm_for_summary.invoke([
            SystemMessage(content="You are a context compression assistant. Produce a concise but complete summary."),
            HumanMessage(content=summarization_prompt),
        ])
        
        # Track token usage for the summarization call
        if hasattr(summary_response, "usage_metadata") and summary_response.usage_metadata:
            usage = summary_response.usage_metadata
            if isinstance(usage, dict):
                s_in = usage.get("input_tokens", 0)
                s_out = usage.get("output_tokens", 0)
            else:
                s_in = getattr(usage, "input_tokens", 0)
                s_out = getattr(usage, "output_tokens", 0)
            record_api_call(
                input_tokens=s_in,
                output_tokens=s_out,
                agent_name=agent_name,
                cache_read_tokens=extract_cache_read_tokens(usage),
            )
        
        summary_text = _extract_summary_text(getattr(summary_response, "content", ""))
        if not isinstance(summary_text, str):
            summary_text = str(summary_text)
        
        if not summary_text.strip():
            log_custom("CONTEXT_SUMMARIZER", "Summarization returned empty, keeping original messages")
            return messages
        
        # Build the new compact message list
        summary_header = (
            "[CONTEXT SUMMARY — The following is an automated summary of the previous conversation. "
            "Continue your work based on this context.]\n\n"
        )
        summarized_messages = system_messages + [
            HumanMessage(content=summary_header + summary_text)
        ]
        
        log_custom("CONTEXT_SUMMARIZER", f"Context summarized for {agent_name}", {
            "original_messages": len(messages),
            "summarized_messages": len(summarized_messages),
            "summary_length": len(summary_text),
        })
        
        return summarized_messages
        
    except Exception as e:
        log_custom("CONTEXT_SUMMARIZER", f"Summarization failed for {agent_name}: {str(e)}, keeping original messages")
        return messages


def _unwrap_llm_for_summarization(llm):
    """Return the base LLM beneath any LangChain tool-binding wrappers."""
    current = llm
    seen_ids = set()

    while current is not None and id(current) not in seen_ids:
        seen_ids.add(id(current))
        bound = _get_real_attr(current, "bound")
        if bound is None or bound is current:
            break
        current = bound

    return current


def maybe_summarize_messages(
    messages: list[BaseMessage],
    llm,
    agent_name: str = "",
    model_name: Optional[str] = None,
    input_tokens: Optional[int] = None,
    runtime_events: Optional[list[dict]] = None,
    task_index: Optional[int] = None,
) -> tuple[list[BaseMessage], bool, str, int]:
    """Summarize messages when the tracked context size exceeds the model threshold.

    Returns:
        (messages, did_summarize, effective_model_name, trigger_input_tokens)
    """
    from .agents.utils.streaming import get_last_input_tokens, reset_last_input_tokens

    effective_model = get_effective_model_name(agent_name=agent_name, model_name=model_name)
    trigger_input_tokens = input_tokens if input_tokens is not None else (
        get_last_input_tokens(agent_name) if agent_name else 0
    )

    if trigger_input_tokens <= 0 or not should_summarize_context(trigger_input_tokens, effective_model):
        return messages, False, effective_model, trigger_input_tokens

    summarized_messages = summarize_messages(messages, llm, agent_name=agent_name)
    did_summarize = summarized_messages is not messages
    if did_summarize and agent_name:
        if runtime_events:
            try:
                from .prompting.events import rehydrate_prompt_runtime_events

                summarized_messages, rehydrated_count = rehydrate_prompt_runtime_events(
                    summarized_messages,
                    runtime_events,
                    agent=agent_name,
                    task_index=task_index,
                )
                if rehydrated_count:
                    log_custom("CONTEXT_SUMMARIZER", "Rehydrated prompt runtime events", {
                        "agent_name": agent_name,
                        "task_index": task_index,
                        "count": rehydrated_count,
                    })
            except Exception:
                pass
        reset_last_input_tokens(agent_name)
        try:
            from .agents.utils.bridge import send_context_usage

            send_context_usage(
                build_context_usage_snapshot(
                    input_tokens=0,
                    model_name=effective_model,
                    agent_name=agent_name,
                )
            )
        except Exception:
            pass

    return summarized_messages, did_summarize, effective_model, trigger_input_tokens
