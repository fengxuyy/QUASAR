"""
Logging utilities for conversation and execution logs.
"""

from datetime import datetime
from pathlib import Path
from typing import Dict, List

from langchain_core.messages import AIMessage, SystemMessage, ToolMessage

from ...tools import LOGS_DIR
from ...tools.base import MAX_OUTPUT_CHARS, truncate_content
from .text import _safe_utf8_text, _get_message_content, _get_message_type
from .text import extract_project_request, format_plan, format_history

# Alias for logging
MAX_LOG_CHARS = MAX_OUTPUT_CHARS

# Track last agent for overwrite logic
_last_input_messages_agent = None


def _write_to_log(text: str, file_path: Path = None, mode: str = 'a') -> None:
    """Helper function to write text to conversation log file.
    
    Args:
        text: Text to write
        file_path: Path to log file (defaults to conversation.md)
        mode: File mode - 'a' for append, 'w' for overwrite (default: 'a')
    """
    if file_path is None:
        file_path = LOGS_DIR / "conversation.md"
    try:
        with open(file_path, mode, encoding='utf-8') as f:
            f.write(_safe_utf8_text(text))
    except Exception:
        pass


def log_agent_header(agent: str, task_index: int, action: str = "Working") -> None:
    """Log a markdown header for an agent's activity."""
    # Markdown headers already provide visual separation, no need for horizontal rules
    header = f"\n## [{agent.title()}]: {action}\n\n"
    _write_to_log(header)


def log_tool_call(tool_name: str, target: str = None, status: str = "completed", agent: str = None) -> None:
    """Log a tool call in markdown format.
    
    Only logs when status is 'completed' to avoid duplication.
    """
    if status != "completed":
        return  # Only log completed calls
    
    # Prepend agent name if provided
    agent_header = f"[{agent.upper()}] " if agent else ""
    
    # Improved formatting with better visual hierarchy
    if target:
        line = f"### **{agent_header}`{tool_name}`** → `{target}`\n\n"
    else:
        line = f"### **{agent_header}`{tool_name}`**\n\n"
    _write_to_log(line)


def log_code_block(code: str, language: str = "python") -> None:
    """Log a code block in markdown format."""
    block = f"```{language}\n{code}\n```\n\n"
    _write_to_log(block)


def log_result(status: str, summary: str = "") -> None:
    """Log a result with pass/fail status in markdown format."""
    status_text = status.upper()
    truncated_summary = truncate_content(summary, max_length=MAX_LOG_CHARS)
    
    # Wrap summary in blockquotes
    lines = truncated_summary.split('\n')
    blockquote = '\n'.join(f"> {line}" if line.strip() else ">" for line in lines)
    result = f"\n---\n\n### **Evaluation Result:** {status_text}\n\n{blockquote}\n\n"
    _write_to_log(result)


def log_message(role: str, content: str, truncate: int = 500) -> None:
    """Log a message from an agent or tool in markdown format.
    
    Args:
        role: The role/source of the message (e.g., 'Operator', 'Tool Result')
        content: The message content
        truncate: Max characters to show (0 for no truncation)
    """
    if truncate > 0 and len(content) > truncate:
        display_content = content[:truncate] + "... [truncated]"
    else:
        display_content = content
    
    # Wrap content in blockquotes
    lines = display_content.split('\n')
    blockquote = '\n'.join(f"> {line}" if line.strip() else ">" for line in lines)
    msg = f"\n**{role}:**\n\n{blockquote}\n\n"
    _write_to_log(msg)


def get_project_context(project_request: str, formatted_plan: str, formatted_history: str) -> str:
    """Format the common project context (request, plan, history) into markdown."""
    return f"""## Project Request
{project_request}

## The Plan
{formatted_plan}

## Task Summaries
{formatted_history}
"""


def write_execution_log(project_request: str, formatted_plan: str, formatted_history: str) -> None:
    """Write execution log to workspace/execution_overview.md.
    
    Args:
        project_request: The original user request
        formatted_plan: The current plan
        formatted_history: Summary of completed tasks
    """
    try:
        log_content = get_project_context(project_request, formatted_plan, formatted_history)
        log_content = _safe_utf8_text(log_content)
        log_path = LOGS_DIR / "execution_overview.md"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, 'w', encoding='utf-8') as f:
            f.write(log_content)
    except Exception:
        pass  # Errors shouldn't stop execution


def _write_input_messages(messages, agent_name: str, task_index: int = None):
    """Write input messages to input_messages.md for debugging with full markdown details.
    
    If the same agent (and task) logs consecutively, it replaces only that section.
    Different tasks for the same agent will append.
    Other agents' sections are preserved.
    
    Args:
        messages: List of messages to log
        agent_name: Name of the agent (e.g., "OPERATOR", "STRATEGIST")
        task_index: Optional task index for operators to differentiate tasks (0-based)
    """
    global _last_input_messages_agent
    
    try:
        import json
        import re
        
        msg_file = LOGS_DIR / "input_messages.md"
        
        # Create a unique identifier that includes task index for operators
        if task_index is not None:
            section_id = f"{agent_name}_Task{task_index + 1}"
            section_header = f"[{agent_name}] Task {task_index + 1} Input Messages"
        else:
            section_id = agent_name
            section_header = f"[{agent_name}] Input Messages"
        
        # Build the new content for this agent/task
        new_section_lines = []
        new_section_lines.append(f"\n---\n\n# {section_header}\n\n")
        
        # Format timestamp nicely
        timestamp = datetime.now().isoformat()
        try:
            dt = datetime.fromisoformat(timestamp)
            formatted_time = dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            formatted_time = timestamp
        new_section_lines.append(f"*Logged at: {formatted_time}*\n\n")
        new_section_lines.append("---\n\n")
        
        for i, msg in enumerate(messages, 1):
            msg_type = _get_message_type(msg)
            content = _get_message_content(msg)
            
            new_section_lines.append(f"## Message {i}: `{msg_type}`\n\n")
            
            # For AIMessage, show tool_calls if present
            if isinstance(msg, AIMessage):
                if hasattr(msg, 'tool_calls') and msg.tool_calls:
                    new_section_lines.append("### Tool Calls\n\n")
                    for tc_idx, tc in enumerate(msg.tool_calls, 1):
                        if isinstance(tc, dict):
                            tc_name = tc.get('name', 'unknown')
                            tc_args = tc.get('args', {})
                            tc_id = tc.get('id', 'no_id')
                        else:
                            tc_name = getattr(tc, 'name', 'unknown')
                            tc_args = getattr(tc, 'args', {})
                            tc_id = getattr(tc, 'id', 'no_id')
                        
                        new_section_lines.append(f"#### Tool Call {tc_idx}\n\n")
                        new_section_lines.append(f"- **Tool:** `{tc_name}`\n")
                        new_section_lines.append(f"- **ID:** `{tc_id}`\n")
                        # Pretty print args
                        try:
                            args_str = json.dumps(tc_args, indent=2, ensure_ascii=False)
                        except Exception:
                            args_str = str(tc_args)
                        new_section_lines.append(f"- **Arguments:**\n\n```json\n{args_str}\n```\n\n")
            
            # For ToolMessage, show tool_call_id
            if isinstance(msg, ToolMessage) or (hasattr(msg, '__class__') and 'Tool' in msg.__class__.__name__):
                tool_call_id = getattr(msg, 'tool_call_id', None)
                if tool_call_id:
                    new_section_lines.append(f"**Tool Call ID:** `{tool_call_id}`\n\n")
            
            # Write content
            new_section_lines.append("### Content\n\n")
            # Truncate very long content for readability (first MAX_LOG_CHARS chars)
            # Skip truncation for SystemMessage to preserve full system prompts
            display_content = _safe_utf8_text(content)
            is_system_message = isinstance(msg, SystemMessage)
            if not is_system_message and len(display_content) > MAX_LOG_CHARS:
                display_content = display_content[:MAX_LOG_CHARS] + "\n\n*... [truncated, total {} chars]*".format(len(content))
            
            # Wrap in blockquote for readability
            lines = display_content.split('\n')
            blockquote = '\n'.join(f"> {line}" if line.strip() else ">" for line in lines)
            new_section_lines.append(blockquote + "\n\n")
            
            new_section_lines.append("---\n\n")
        
        new_section = ''.join(new_section_lines)
        
        # If same agent/task as last time, replace that section in the file
        if _last_input_messages_agent == section_id and msg_file.exists():
            existing_content = msg_file.read_text(encoding='utf-8')
            
            # Pattern to find this section (from "---\n\n# [HEADER]" to next "---\n\n# [" or EOF)
            # We need to match the horizontal rule before the header too
            escaped_header = re.escape(section_header)
            # Match from "---\n\n# {header}" up to (but not including) the next "---\n\n# [" 
            # The header section starts with "\n---\n\n# {header}\n\n"
            pattern = rf'\n---\n\n# {escaped_header}\n\n.*?(?=\n---\n\n# \[|$)'
            
            match = re.search(pattern, existing_content, re.DOTALL)
            if match:
                # Replace existing section (keeping the leading newline for proper formatting)
                new_content = existing_content[:match.start()] + new_section.rstrip() + existing_content[match.end():]
                msg_file.write_text(new_content, encoding='utf-8')
            else:
                # Section not found with full pattern, try simpler version
                # Just look for the header line itself
                simple_pattern = rf'\n# {escaped_header}\n'
                if re.search(simple_pattern, existing_content, re.DOTALL):
                    # Find section boundaries manually
                    header_match = re.search(simple_pattern, existing_content)
                    if header_match:
                        start_pos = header_match.start()
                        # Find next section header or end of file
                        next_section = re.search(r'\n---\n\n# \[', existing_content[header_match.end():], re.DOTALL)
                        if next_section:
                            end_pos = header_match.end() + next_section.start()
                        else:
                            end_pos = len(existing_content)
                        # Also include any preceding "---\n" if present
                        if start_pos > 4 and existing_content[start_pos-4:start_pos] == '---\n':
                            start_pos -= 4
                        new_content = existing_content[:start_pos] + new_section.rstrip() + existing_content[end_pos:]
                        msg_file.write_text(new_content, encoding='utf-8')
                    else:
                        # Fallback: append
                        with open(msg_file, 'a', encoding='utf-8') as f:
                            f.write(new_section)
                else:
                    # Section not found, append
                    with open(msg_file, 'a', encoding='utf-8') as f:
                        f.write(new_section)
        else:
            # Different agent/task or file doesn't exist - append
            # Add header if file is empty or doesn't exist
            if not msg_file.exists() or msg_file.stat().st_size == 0:
                header = "# QUASAR Input Messages Log\n\n*This file contains detailed input messages sent to each agent for debugging purposes.*\n\n"
                with open(msg_file, 'w', encoding='utf-8') as f:
                    f.write(header)
            
            with open(msg_file, 'a', encoding='utf-8') as f:
                f.write(new_section)
        
        _last_input_messages_agent = section_id
        
    except Exception:
        # Don't fail if we can't write the log
        pass
