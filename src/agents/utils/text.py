"""
Text extraction and formatting utilities.
"""

from typing import Any, Dict, List
from langchain_core.messages import HumanMessage

# Re-export truncate_content from tools.base
from ...tools.base import truncate_content


def _extract_text(content_obj: Any) -> str:
    """Normalize provider-specific chunk content into plain text."""
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
                text_val = part.get('text') or part.get('content') or ''
                if isinstance(text_val, str):
                    parts.append(text_val)
        return "".join(parts)
    if isinstance(content_obj, dict):
        text_val = content_obj.get('text') or content_obj.get('content') or ''
        return text_val if isinstance(text_val, str) else str(content_obj)
    return str(content_obj)


def _extract_thoughts(content_obj: Any) -> str:
    """Extract provider-specific "thinking" content from streamed chunks."""
    if content_obj is None:
        return ""
    if isinstance(content_obj, str):
        return ""
    if isinstance(content_obj, list):
        parts = []
        for part in content_obj:
            if isinstance(part, dict):
                if part.get('type') == 'thinking':
                    thinking_val = part.get('thinking') or part.get('text') or part.get('content') or ''
                else:
                    thinking_val = part.get('thinking') or ''
                if thinking_val:
                    parts.append(thinking_val if isinstance(thinking_val, str) else str(thinking_val))
        return "".join(parts)
    if isinstance(content_obj, dict):
        if content_obj.get('type') == 'thinking':
            thinking_val = content_obj.get('thinking') or content_obj.get('text') or content_obj.get('content') or ''
            return thinking_val if isinstance(thinking_val, str) else str(thinking_val)
        thinking_val = content_obj.get('thinking')
        return thinking_val if isinstance(thinking_val, str) else ""
    return ""


def _safe_utf8_text(text: Any) -> str:
    """Convert text to a UTF-8 safe string by replacing invalid surrogates."""
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)
    return text.encode("utf-8", errors="replace").decode("utf-8")


def _get_message_content(msg):
    """Extract content from a message (dict or object)."""
    if isinstance(msg, dict):
        return msg.get('content', '')
    elif hasattr(msg, 'content'):
        return msg.content
    return str(msg)


def _get_message_type(msg):
    """Get message type name."""
    if isinstance(msg, dict):
        return msg.get('role', 'unknown')
    return type(msg).__name__


def extract_project_request(messages: List) -> str:
    """Extract project request from messages.
    
    Looks for the first user message with non-empty content.
    
    Args:
        messages: List of messages (can be dict or message objects)
        
    Returns:
        str: The project request content, or empty string if not found
    """
    for msg in messages:
        if isinstance(msg, dict):
            if msg.get('role') == 'user':
                content = msg.get('content', '')
                if content and isinstance(content, str) and content.strip():
                    return content.strip()
        elif isinstance(msg, HumanMessage):
            content = getattr(msg, 'content', '')
            if content and isinstance(content, str) and content.strip():
                return content.strip()
    return ""


def format_plan(plan: List[str]) -> str:
    """Format plan as numbered list.
    
    Args:
        plan: List of plan steps
        
    Returns:
        str: Formatted plan string
    """
    if not plan:
        return "No plan found."
    return "\n".join(plan)


def format_history(step_results: Dict[int, str], completed_steps: List[str]) -> str:
    """Format task history from step results with improved markdown.
    
    Args:
        step_results: Dictionary mapping task index to summary
        completed_steps: List of completed step descriptions
        
    Returns:
        str: Formatted history string with better markdown formatting
    """
    if not step_results:
        return "*No previous task summaries.*"
    
    formatted_tasks = []
    for i in range(len(completed_steps)):
        task_num = i + 1
        step_desc = completed_steps[i] if i < len(completed_steps) else "Unknown step"
        summary = step_results.get(i, "No summary recorded.")
        
        # Create header with task number and step description
        task_block = f"### Task {task_num}: {step_desc}\n\n"
        
        # Format the summary - if multi-line, keep as-is; otherwise wrap nicely
        summary_clean = summary.strip()
        if summary_clean:
            task_block += f"{summary_clean}\n"
        else:
            task_block += "*No summary recorded.*\n"
        
        formatted_tasks.append(task_block)
    
    return "\n".join(formatted_tasks) if formatted_tasks else "*No previous task summaries.*"
