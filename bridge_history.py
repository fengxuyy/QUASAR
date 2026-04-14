"""
Checkpoint history reconstruction utilities for bridge.py.

This module extracts and formats checkpoint history from saved state
for display in the CLI when resuming from a checkpoint.
"""

import os
import re
from collections import defaultdict
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from src.agents.utils.tool_helpers import _get_execute_python_status_pair


CHECKIN_DECISION_TOOLS = {"continue_execution", "interrupt_execution"}
CHECKIN_CONTROL_PHRASES = (
    "Continue this execution check-in and finish with either",
    "Please call either `continue_execution(summary='...')` or",
    'Please call either `continue_execution(summary="...")` or',
)

# Strategist planning / revision prompts (also used to pick the richest transcript for metadata)
REVISION_PROMPT_MARKER = (
    "Please revise your latest reviewed plan above based on the user's feedback below."
)
USER_FEEDBACK_SECTION = "User feedback:\n"
AUTO_IMPROVE_SNIPPET = (
    "Please analyze the previous run results and automatically improve the workflow"
)


def _truncate_collapsible_output(
    content_str: str,
    max_length: int = 5000,
    truncation_msg: str = "\n\n... [Results truncated for display]",
) -> str:
    """Trim stored tool output for compact collapsible history sections."""
    if len(content_str) <= max_length:
        return content_str
    return content_str[:max_length] + truncation_msg


def _is_checkin_prompt_text(content: str) -> bool:
    """Return True when the message is the periodic execution check-in prompt."""
    return (
        content.startswith("The Python script `")
        and "has been running for" in content
        and "**Current Resource Usage:**" in content
    )


def _is_checkin_control_text(content: str) -> bool:
    """Return True for helper prompts emitted only inside a check-in session."""
    return any(phrase in content for phrase in CHECKIN_CONTROL_PHRASES)


def _filter_checkin_session_messages(messages: list) -> list:
    """Remove transient check-in transcript entries from checkpoint history."""
    filtered_messages = []
    in_checkin_session = False
    skipped_tool_call_ids = set()

    for msg in messages:
        msg_type = _get_message_type(msg)
        content = _get_content(msg).strip()
        tool_calls = _get_tool_calls(msg) if msg_type == "AIMessage" else []
        tool_names = {
            _extract_tool_info(tc)[0]
            for tc in tool_calls
            if _extract_tool_info(tc)[0]
        }

        if msg_type == "HumanMessage" and (
            _is_checkin_prompt_text(content) or _is_checkin_control_text(content)
        ):
            in_checkin_session = True
            continue

        if msg_type == "AIMessage":
            starts_checkin_without_prompt = (
                "execute_temporary_python" in tool_names
                or bool(tool_names & CHECKIN_DECISION_TOOLS)
            )
            if starts_checkin_without_prompt:
                in_checkin_session = True

            if in_checkin_session:
                for tc in tool_calls:
                    _, _, tool_id = _extract_tool_info(tc)
                    if tool_id:
                        skipped_tool_call_ids.add(tool_id)
                if tool_names & CHECKIN_DECISION_TOOLS:
                    in_checkin_session = False
                continue

        if msg_type == "ToolMessage":
            if isinstance(msg, dict):
                tool_call_id = msg.get("tool_call_id")
            else:
                tool_call_id = getattr(msg, "tool_call_id", None)

            if tool_call_id in skipped_tool_call_ids:
                skipped_tool_call_ids.discard(tool_call_id)
                continue

            if in_checkin_session and (
                content.startswith("CONTINUE_EXECUTION")
                or content.startswith("INTERRUPT_EXECUTION:")
            ):
                in_checkin_session = False
                continue

        if in_checkin_session and msg_type == "HumanMessage":
            continue

        filtered_messages.append(msg)

    return filtered_messages


def _parse_checkin_summary_message(content: str) -> dict | None:
    """Extract fields from a compact operator check-in summary message."""
    if "[EXECUTION CHECK-IN SUMMARY]" not in content:
        return None

    parsed = {"decision": "", "reason": "", "summary": ""}
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("Decision:"):
            parsed["decision"] = stripped.partition(":")[2].strip()
        elif stripped.startswith("Reason:"):
            parsed["reason"] = stripped.partition(":")[2].strip()
        elif stripped.startswith("Summary:"):
            parsed["summary"] = stripped.partition(":")[2].strip()

    return parsed


def _extract_interrupt_reason_items(current_task_messages: list) -> list[dict]:
    """Build synthetic history items for compact interrupt decisions."""
    items = []
    seen_reasons = set()

    for msg in current_task_messages or []:
        if _get_message_type(msg) != "HumanMessage":
            continue

        parsed = _parse_checkin_summary_message(_get_content(msg).strip())
        if not parsed or parsed.get("decision") != "interrupt_execution":
            continue

        reason = (parsed.get("reason") or "").strip()
        if not reason or reason in seen_reasons:
            continue

        seen_reasons.add(reason)
        items.append({
            "type": "tool",
            "content": "Interrupted Execution",
            "output": reason,
            "agent": "operator",
            "isError": True,
        })

    return items


def _extract_evaluation_failed_item(content: str) -> dict | None:
    """Extract a structured evaluation-failed item from evaluator feedback text."""
    if "EVALUATION_FEEDBACK" not in content:
        return None

    retry_match = re.search(r'\(attempt (\d+)/(\d+)\)', content)
    if not retry_match:
        return None

    attempt_num = retry_match.group(1)
    max_attempts = int(retry_match.group(2))
    max_retries = max_attempts - 1

    lines = content.split('\n')
    summary_lines = []
    capture = False
    for line in lines:
        if 'NOT satisfied' in line:
            capture = True
            continue
        if 'Please resolve' in line:
            break
        if capture and line.strip():
            summary_lines.append(line)

    summary = '\n'.join(summary_lines).strip()
    return {
        "type": "evaluation-failed",
        "content": f"Evaluation Failed - Retry {attempt_num}/{max_retries}",
        "summary": summary,
        "agent": "evaluator"
    }


def _extract_target_name(val) -> str:
    """Convert a path value to string, handling list-typed values from tool args.
    Formats multiple paths as 'path1, path2' or 'N items' for display."""
    if isinstance(val, list):
        if not val:
            return ''
        import os
        names = []
        for v in val:
            if v is None:
                continue
            v_str = str(v).strip().rstrip('/')
            if v_str in ('', '.'):
                names.append('workspace')
                continue
            if v_str.startswith('./'):
                v_str = v_str[2:]
            if os.path.isabs(v_str):
                names.append(os.path.basename(v_str))
            else:
                names.append(v_str or os.path.basename(str(v)))
        if len(names) <= 3:
            return ', '.join(names)
        return f"{len(names)} items"
    
    import os
    if val is None:
        return ''
    target_str = str(val).strip().rstrip('/')
    if target_str.startswith('./'):
        target_str = target_str[2:]
    if os.path.isabs(target_str):
        return os.path.basename(target_str)
    return target_str or os.path.basename(str(val))


def _extract_text(content_obj) -> str:
    """Normalize provider-specific chunk content into plain text."""
    if not content_obj:
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


# Tool name -> display message mapping
TOOL_DISPLAY_MESSAGES = {
    'query_rag': 'Queried RAG',
    'read_file': 'Read',
    'write_file': 'Wrote',
    'edit_file': 'Edited',
    'delete_file': 'Deleted',
    'list_directory': 'Listed',
    'move_file': 'Moved',
    'rename_file': 'Renamed',
    'execute_code': 'Executed',
    'execute_python': 'Executed',  # Legacy alias
    'analyze_image': 'Analyzed image',
    'search_web': 'Searched web',
    'fetch_web_page': 'Fetched web page',
    'grep_search': 'Grepped files',
    'get_hardware_info': 'Checked Hardware',
}


def _execute_python_panel_output(tool_args: dict, content_str: str) -> str:
    """Build execute_python/execute_code panel text to match runtime (_handle_execute_python_status)."""
    if not isinstance(tool_args, dict):
        tool_args = {}
    file_path = tool_args.get("file_path") or ""
    code = tool_args.get("code") or ""
    parts: list[str] = []
    if code and not file_path:
        parts.append(f"**Code:**\n```python\n{code}\n```\n\n")
    if content_str:
        truncated = content_str[:2000] if len(content_str) > 2000 else content_str
        parts.append(truncated)
    return "".join(parts)


def _step_complete_status_execute_python(tool_name: str, tool_args: dict) -> str:
    """Status line for execute_python/execute_code step_complete — matches live UI."""
    if tool_name in ("execute_python", "execute_code") and isinstance(tool_args, dict):
        _, complete = _get_execute_python_status_pair(tool_args)
        return complete
    return format_tool_display(tool_name, tool_args or {})


def format_tool_display(tool_name: str, tool_args: dict) -> str:
    """Format a tool call into a display string like 'Listed pseudo' or 'Executed Python code'."""
    # Special handling for read_file with keyword
    if tool_name == 'read_file' and tool_args:
        keyword = tool_args.get('keyword')
        file_path = tool_args.get('file_path', 'file')
        file_name = _extract_target_name(file_path) if file_path else 'file'
        
        if keyword:
            return f"Read {file_name} ({keyword})"
        else:
            return f"Read {file_name}"
    
    # Special handling for query_rag - show query
    if tool_name == 'query_rag' and tool_args:
        query = tool_args.get('query', '')
        library = tool_args.get('library', '')
        display_query = query[:40] + '...' if len(query) > 40 else query
        status_text = f"{display_query} in {library}" if library else f"{display_query}"
        return f"Queried RAG {status_text}"
    
    # Special handling for search_web - show query
    if tool_name == 'search_web' and tool_args:
        query = tool_args.get('query', '')
        display_query = query[:50] + '...' if len(query) > 50 else query
        return f"Searched {display_query}"
    
    # Special handling for fetch_web_page - show domain/URL
    if tool_name == 'fetch_web_page' and tool_args:
        url = tool_args.get('url', '')
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            domain = parsed.netloc or url[:40]
            path = parsed.path[:20] if parsed.path else ''
            display_url = f"{domain}{path}" if len(domain + path) <= 50 else domain
        except:
            display_url = url[:50] + '...' if len(url) > 50 else url
        return f"Fetched {display_url}"
    
    # Special handling for submit_evaluation - show status
    if tool_name == 'submit_evaluation' and tool_args:
        status = tool_args.get('status', '').lower()
        if status == 'pass':
            return "Evaluation Passed"
        elif status == 'fail':
            return "Evaluation Failed"
        return "Submitted evaluation"
    
    # Special handling for move_file — args use source_path/destination_path (match _handle_move_file_status)
    if tool_name == 'move_file' and tool_args:
        source_path = tool_args.get('source_path')
        destination_path = tool_args.get('destination_path')
        src_display = (
            os.path.basename(str(source_path).strip().rstrip('/'))
            if source_path
            else 'file'
        )
        dst_display = str(destination_path).strip() if destination_path else 'destination'
        return f"Moved {src_display} to {dst_display}"
    
    # Special handling for rename_file — match _handle_rename_file_status (not just file_path)
    if tool_name == 'rename_file' and tool_args:
        file_path = tool_args.get('file_path')
        new_name = tool_args.get('new_name')
        src_display = (
            os.path.basename(str(file_path).strip().rstrip('/'))
            if file_path
            else 'file'
        )
        dst_display = str(new_name).strip() if new_name else 'new name'
        return f"Renamed {src_display} to {dst_display}"
    
    # Special handling for grep_search - show pattern
    if tool_name == 'grep_search' and tool_args:
        pattern = tool_args.get('pattern', '')
        directory_path = tool_args.get('directory_path', '.')
        if pattern:
            display_pattern = pattern[:50] + '...' if len(pattern) > 50 else pattern
            if directory_path and directory_path != '.':
                dir_name = _extract_target_name(directory_path)
                return f"Grepped files {display_pattern} in {dir_name}"
            return f"Grepped files {display_pattern}"
    
    # Special handling for execute_code - show file name or truncated code
    if tool_name in ('execute_code', 'execute_python') and tool_args:
        is_trial = tool_args.get('is_trial_run', False)
        file_path = tool_args.get('file_path')
        code = tool_args.get('code')
        trial_suffix = ' [Trial]' if is_trial else ''
        
        if file_path:
            file_name = _extract_target_name(file_path)
            return f"Executed {file_name}{trial_suffix}"
        elif code:
            # Truncate to first line, max 50 chars
            first_line = code.strip().split('\n')[0][:50]
            if len(code.strip().split('\n')[0]) > 50 or '\n' in code.strip():
                first_line += '...'
            return f"Executed {first_line}{trial_suffix}"
        else:
            return f"Executed{trial_suffix}"
    
    base_msg = TOOL_DISPLAY_MESSAGES.get(tool_name, f"Executed {tool_name}")
    
    # Try to extract target name from args for file/dir operations
    target = None
    if tool_args:
        for key in ['path', 'directory', 'file_path', 'target', 'filename', 'directory_path']:
            if key in tool_args:
                target = tool_args[key]
                break
    
    if target:
        target_name = _extract_target_name(target)
        if not target_name or target_name == '.':
            target_name = 'workspace'
        if target_name:
            return f"{base_msg} {target_name}"
    
    return base_msg


def _extract_tool_info(tc) -> tuple:
    """Extract tool name, args, and id from a tool call object or dict."""
    if isinstance(tc, dict):
        return tc.get('name', ''), tc.get('args', {}), tc.get('id', '')
    return getattr(tc, 'name', ''), getattr(tc, 'args', {}), getattr(tc, 'id', '')


def _get_message_type(msg) -> str:
    """Determine message type (AIMessage, HumanMessage, ToolMessage) from object or dict."""
    if isinstance(msg, dict):
        # Handle various serialization formats
        role = msg.get('role') or msg.get('type')
        if role == 'ai' or role == 'assistant' or role == 'AIMessage':
            return 'AIMessage'
        if role == 'human' or role == 'user' or role == 'HumanMessage':
            return 'HumanMessage'
        if role == 'tool' or role == 'ToolMessage':
            return 'ToolMessage'
        return 'Unknown'
    
    # Handle objects
    if isinstance(msg, AIMessage): return 'AIMessage'
    if isinstance(msg, HumanMessage): return 'HumanMessage'
    if isinstance(msg, ToolMessage): return 'ToolMessage'
    return 'Unknown'


def _get_tool_calls(msg) -> list:
    """Extract tool calls from an AI message object or dict."""
    if isinstance(msg, dict):
        return msg.get('tool_calls', [])
    return getattr(msg, 'tool_calls', []) or []


def _get_content(msg) -> str:
    """Extract content from any message object or dict."""
    if isinstance(msg, dict):
        return _extract_text(msg.get('content', ''))
    return _extract_text(getattr(msg, 'content', ''))


def _create_code_snippet_item(tool_args: dict) -> dict:
    """Create a code-snippet item for write_file tool calls."""
    file_path = tool_args.get('file_path', 'file')
    file_name = _extract_target_name(file_path) if file_path else 'file'
    return {
        "type": "code-snippet",
        "content": {
            "name": file_name,
            "content": tool_args['content'],
            "isComplete": True,
            "isContinuation": False
        }
    }


def _detect_error_in_content(content_str: str, status: str = '') -> bool:
    """Detect if a tool message content indicates an error."""
    content_lower = content_str.lower()
    return (
        status == 'error' or
        content_str.startswith("Error:") or
        'validation error' in content_lower or
        'field required' in content_lower or
        'no files found' in content_lower or
        'exit code: 1' in content_lower or
        'executed failed' in content_lower or
        'code executed failed' in content_lower or
        ("not found" in content_lower and "found keyword" not in content_lower) or
        "does not exist" in content_lower or
        "permission denied" in content_lower or
        "no such file or directory" in content_lower or
        "syntaxerror" in content_lower or
        "indentationerror" in content_lower or
        "attributeerror" in content_lower or
        "importerror" in content_lower or
        "valueerror" in content_lower or
        "keyerror" in content_lower or
        "filenotfounderror" in content_lower
    )


def _format_error_content(tool_name: str, tool_args: dict, content_str: str) -> str:
    """Format an error message with descriptive content based on tool type."""
    content_lower = content_str.lower()
    
    # Handle validation errors (missing required fields, etc.)
    if 'validation error' in content_lower or 'field required' in content_lower:
        # Map tool names to user-friendly failure messages
        tool_error_names = {
            'query_rag': 'Query RAG Failed',
            'read_file': 'Read File Failed',
            'write_file': 'Write File Failed',
            'edit_file': 'Edit File Failed',
            'delete_file': 'Delete File Failed',
            'list_directory': 'List Directory Failed',
            'move_file': 'Move File Failed',
            'rename_file': 'Rename File Failed',
            'execute_python': 'Execute Python Failed',
            'execute_code': 'Execute Code Failed',
            'analyze_image': 'Analyze Image Failed',
            'search_web': 'Search Web Failed',
            'fetch_web_page': 'Fetch Web Page Failed',
            'grep_search': 'Grep Files Failed',
        }
        return tool_error_names.get(tool_name, f"{tool_name} Failed")
    
    if tool_name == "list_directory":
        path = tool_args.get("directory_path", ".")
        pattern = tool_args.get("pattern", "*")
        path_display = _extract_target_name(path) if path and path != '.' else 'workspace'
        
        if "no files found" in content_lower:
            if pattern and pattern != '*':
                return f"No files found matching {pattern} in {path_display}"
            return f"No files found in {path_display}"
        return f"{path_display} directory not found"
    
    elif tool_name == "read_file":
        file_path = tool_args.get("file_path", "file")
        file_name = _extract_target_name(file_path) if file_path else "file"
        keyword = tool_args.get("keyword")
        
        if "file" in content_lower and ("not found" in content_lower or "does not exist" in content_lower):
            return f"{file_name} not found"
        elif keyword and "keyword" in content_lower and "not found" in content_lower:
            return f"{keyword} not found in {file_name}"
        elif keyword:
            return f"{keyword} not found in {file_name}"
        else:
            return f"{file_name} not found"
    
    elif tool_name == "query_rag":
        query = tool_args.get("query", "")[:40]
        return f"RAG query failed: {query}"
    
    elif tool_name == "search_web":
        query = tool_args.get("query", "")[:50]
        if "no results found" in content_lower:
            return f"No results for {query}"
        return f"Search failed for {query}"
    
    elif tool_name == "fetch_web_page":
        url = tool_args.get("url", "")
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            domain = parsed.netloc or url[:40]
            display_url = domain
        except:
            display_url = url[:40] + '...' if len(url) > 40 else url
        
        if "invalid url" in content_lower:
            return f"Invalid URL: {display_url}"
        elif "failed to fetch" in content_lower:
            return f"Failed to fetch {display_url}"
        return f"Error fetching {display_url}"
    
    elif tool_name in ("execute_code", "execute_python"):
        file_path = tool_args.get("file_path", "script.py")
        file_name = _extract_target_name(file_path) if file_path else 'script'
        is_trial = tool_args.get('is_trial_run', False)
        trial_suffix = ' [Trial]' if is_trial else ''
        if "syntaxerror" in content_lower:
            return f"Executed {file_name} (Syntax Error){trial_suffix}"
        if "indentationerror" in content_lower:
            return f"Executed {file_name} (Indentation Error){trial_suffix}"
        return f"Executed {file_name}{trial_suffix}"  # Use default tool display name style
    
    elif tool_name == "grep_search":
        pattern = tool_args.get("pattern", "")[:50]
        directory_path = tool_args.get("directory_path", ".")
        if "timed out" in content_lower:
            return f"Grep timed out for {pattern}"
        elif "no matches found" in content_lower:
            return f"No matches for {pattern}"
        elif "not a directory" in content_lower or "does not exist" in content_lower:
            dir_name = _extract_target_name(directory_path) if directory_path != '.' else 'directory'
            return f"{dir_name} not found"
        return f"Grep failed for {pattern}"

    elif tool_name == "edit_file":
        # Match the live execution log: edit_file keeps its normal status row and
        # relies on the error flag for styling/details instead of collapsing to a
        # generic "Not Found" label when the replacement text is missing.
        return format_tool_display(tool_name, tool_args)
    
    # Generic fallback for other tools if error detected but no specific mapping
    if "not found" in content_lower or "does not exist" in content_lower or "no such file" in content_lower:
        return "Not Found"
    
    return None  # Use default content


def _format_success_content(tool_name: str, tool_args: dict, content_str: str) -> str:
    """Format a success message, adding match count for keyword searches."""
    if tool_name == "query_rag":
        query = tool_args.get("query", "")[:40]
        library = tool_args.get("library", "")
        if library:
            return f"Queried RAG {query} in {library}"
        return f"Queried RAG {query}"
        
    if tool_name == "read_file" and tool_args.get("keyword"):
        keyword = tool_args.get("keyword")
        file_path = tool_args.get("file_path", "file")
        file_name = _extract_target_name(file_path) if file_path else "file"
        
        match_re = re.search(r"at line\(s\) ([\d,\s]+)", content_str)
        if match_re:
            lines_str = match_re.group(1)
            match_count = len([l.strip() for l in lines_str.split(',') if l.strip()])
            match_word = "match" if match_count == 1 else "matches"
            return f"Read {file_name} ({keyword}: {match_count} {match_word})"
        else:
            return f"Read {file_name} ({keyword})"
    
    elif tool_name == "search_web":
        query = tool_args.get("query", "")[:50]
        # Count results by looking for [Result N] patterns
        matches = re.findall(r'\[Result \d+\]', content_str)
        if matches:
            result_count = len(matches)
            result_word = "result" if result_count == 1 else "results"
            return f"Searched {query} ({result_count} {result_word})"
        return f"Searched {query}"
    
    elif tool_name == "fetch_web_page":
        url = tool_args.get("url", "")
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            domain = parsed.netloc or url[:40]
            path = parsed.path[:20] if parsed.path else ''
            display_url = f"{domain}{path}" if len(domain + path) <= 50 else domain
        except:
            display_url = url[:40] + '...' if len(url) > 40 else url
        
        # Check for truncation and content length
        is_truncated = "truncated" in content_str.lower()
        content_length = len(content_str)
        
        if is_truncated:
            return f"Fetched {display_url} (truncated)"
        elif content_length >= 1000:
            return f"Fetched {display_url} ({content_length // 1000}k chars)"
        else:
            return f"Fetched {display_url} ({content_length} chars)"
    
    elif tool_name == "grep_search":
        pattern = tool_args.get("pattern", "")[:50]
        directory_path = tool_args.get("directory_path", ".")
        content_lower = content_str.lower()
        
        # No matches: tool returns "No matches found for pattern ..." - don't count that line as a match
        if "no matches found" in content_lower:
            if directory_path and directory_path != '.':
                dir_name = _extract_target_name(directory_path)
                return f"Grepped files {pattern} in {dir_name}"
            return f"Grepped files {pattern}"
        
        # Extract match count from "Found X matches" in the tool output (success case)
        match_re = re.search(r'Found (\d+) matches', content_str)
        if match_re:
            match_count = int(match_re.group(1))
            is_truncated = "truncated" in content_lower or "showing first" in content_lower
            match_word = "match" if match_count == 1 else "matches"
            truncated_text = " (truncated)" if is_truncated else ""
            if directory_path and directory_path != '.':
                dir_name = _extract_target_name(directory_path)
                return f"Grepped files {pattern} in {dir_name} ({match_count} {match_word}{truncated_text})"
            return f"Grepped files {pattern} ({match_count} {match_word}{truncated_text})"
        
        # Fallback: no "Found X matches" and no "no matches found"
        if directory_path and directory_path != '.':
            dir_name = _extract_target_name(directory_path)
            return f"Grepped files {pattern} in {dir_name}"
        return f"Grepped files {pattern}"
    
    return None  # Use default content


def _model_text_looks_like_tool_validation(text: str) -> bool:
    """True when AIMessage body is a Pydantic-style tool validation error."""
    if not text:
        return False
    cl = text.lower()
    if "validation error" in cl:
        return True
    return "field required" in cl and (
        "field '" in cl or 'field "' in cl or "issues):" in cl
    )


def _merge_orphan_execute_tool_validation_items(items: list) -> None:
    """In-place: merge execute_python/execute_code tool row + following validation model-text.

    When tool.invoke raises ValidationError there is no ToolMessage; the next AIMessage
    carries format_validation_error text. Without this merge the UI only shows a bare
    'Executed' tool row from format_tool_display.
    """
    i = 0
    while i < len(items) - 1:
        cur = items[i]
        nxt = items[i + 1]
        if (
            isinstance(cur, dict)
            and cur.get("type") == "tool"
            and cur.get("name") in ("execute_python", "execute_code")
            and isinstance(nxt, dict)
            and nxt.get("type") == "model-text"
            and _model_text_looks_like_tool_validation((nxt.get("content") or "").strip())
        ):
            raw = (nxt.get("content") or "").strip()
            tool_name = cur.get("name") or "execute_python"
            tool_args = cur.get("args") or {}
            merged = dict(cur)
            merged["content"] = _format_error_content(tool_name, tool_args, raw)
            merged["isError"] = True
            detail = raw
            if detail and not detail.lower().startswith("error:"):
                detail = f"Error: {detail}"
            merged["output"] = detail
            items[i : i + 2] = [merged]
            i += 1
            continue
        i += 1


def _apply_orphan_execute_merges(
    strategist_items: list,
    operator_items_by_task,
    evaluator_items_by_task,
    ordered_items_by_task,
) -> None:
    """Apply validation-followup merge across all checkpoint history item lists."""
    _merge_orphan_execute_tool_validation_items(strategist_items)
    for bucket in (operator_items_by_task, evaluator_items_by_task, ordered_items_by_task):
        for _key in list(bucket.keys()):
            _merge_orphan_execute_tool_validation_items(bucket[_key])


def _normalize_snapshot_values(snapshot) -> dict | None:
    """Extract a state-values dict from a checkpoint-history snapshot-like object."""
    if snapshot is None:
        return None

    if isinstance(snapshot, dict):
        values = snapshot.get("values")
        if isinstance(values, dict):
            return values
        if any(
            key in snapshot
            for key in ("completed_steps", "current_task_messages", "evaluation_messages", "plan")
        ):
            return snapshot
        return None

    values = getattr(snapshot, "values", None)
    return values if isinstance(values, dict) else None


def _count_relevant_task_messages(messages: list) -> int:
    """Estimate how much recoverable task history a message list contains."""
    count = 0
    for msg in messages or []:
        msg_type = _get_message_type(msg)
        content = _get_content(msg).strip()
        if msg_type in {"AIMessage", "ToolMessage"}:
            count += 1
        elif msg_type == "HumanMessage" and (
            "EVALUATION_FEEDBACK" in content or _parse_checkin_summary_message(content)
        ):
            count += 1
    return count


def _history_item_signature(item: dict):
    """Create a stable signature for deduplicating reconstructed history items."""
    def _normalize(value):
        if isinstance(value, dict):
            return tuple(sorted((k, _normalize(v)) for k, v in value.items()))
        if isinstance(value, list):
            return tuple(_normalize(v) for v in value)
        return value

    filtered = {
        key: value
        for key, value in item.items()
        if key not in {"tool_id", "name", "args"}
    }
    return _normalize(filtered)


def _merge_unique_history_items(*item_lists: list[dict]) -> list[dict]:
    """Merge item lists while preserving order and removing duplicates."""
    merged = []
    seen = set()
    for items in item_lists:
        for item in items or []:
            signature = _history_item_signature(item)
            if signature in seen:
                continue
            seen.add(signature)
            merged.append(item)
    return merged


def _insert_before_or_append(items: list[dict], marker_item: dict, new_item: dict) -> None:
    """Insert an item immediately before a marker item, falling back to append."""
    try:
        idx = items.index(marker_item)
        items.insert(idx, new_item)
    except ValueError:
        items.append(new_item)


def _apply_tool_message_to_task_history(
    tool_call_id,
    status: str,
    content_str: str,
    ordered_items: list[dict],
    operator_items: list[dict],
    evaluator_items: list[dict],
) -> None:
    """Apply a ToolMessage result onto previously reconstructed tool-call items."""
    matching_tool = None
    target_list = None

    for item in ordered_items:
        if item.get("tool_id") == tool_call_id:
            matching_tool = item
            if item.get("agent") == "evaluator":
                target_list = evaluator_items
            else:
                target_list = operator_items
            break

    if not matching_tool or target_list is None:
        return

    tool_name = matching_tool.get("name", "")
    tool_args = matching_tool.get("args", {})
    agent_name = matching_tool.get("agent", "operator")
    is_error = _detect_error_in_content(content_str, status)

    if is_error:
        matching_tool["isError"] = True
        error_content = _format_error_content(tool_name, tool_args, content_str)
        if error_content:
            matching_tool["content"] = error_content
    else:
        success_content = _format_success_content(tool_name, tool_args, content_str)
        if success_content:
            matching_tool["content"] = success_content

    if tool_name in ("execute_code", "execute_python"):
        code_result = {
            "type": "code-result",
            "content": {
                "output": _execute_python_panel_output(tool_args, content_str),
                "filePath": tool_args.get("file_path", ""),
                "status": _step_complete_status_execute_python(tool_name, tool_args),
            },
            "isError": is_error,
            "agent": agent_name
        }
        _insert_before_or_append(ordered_items, matching_tool, code_result)
        _insert_before_or_append(target_list, matching_tool, code_result)

    if tool_name == "analyze_image":
        analysis_output = content_str
        if content_str.startswith("**Analyze Image:**"):
            lines = content_str.split('\n', 1)
            if len(lines) > 1:
                analysis_output = lines[1].lstrip('> ').strip()

        image_result = {
            "type": "image-analysis-result",
            "content": {
                "output": analysis_output,
                "filePath": tool_args.get("file_path", "")
            },
            "isError": is_error,
            "agent": agent_name
        }
        _insert_before_or_append(ordered_items, matching_tool, image_result)
        _insert_before_or_append(target_list, matching_tool, image_result)

    if tool_name == "edit_file":
        old_string = tool_args.get('old_string', '')
        new_string = tool_args.get('new_string', '')
        if old_string or new_string:
            max_len = 1500
            old_display = old_string[:max_len] + "..." if len(old_string) > max_len else old_string
            new_display = new_string[:max_len] + "..." if len(new_string) > max_len else new_string
            diff_lines = [f"- {line}" for line in old_display.split('\n')]
            diff_lines.extend(f"+ {line}" for line in new_display.split('\n'))
            matching_tool["output"] = "```diff\n" + "\n".join(diff_lines) + "\n```"

    if tool_name in ("query_rag", "grep_search", "search_web", "fetch_web_page") and content_str:
        matching_tool["output"] = _truncate_collapsible_output(content_str)


def _should_skip_task_ai_content(content: str) -> bool:
    """Return True for task-local AIMessage content that should not render in history."""
    if not content:
        return True
    return (
        content == "DONE"
        or content == "GIVE_UP"
        or content == "Please provide a valid input or question."
        or content.startswith("Please start working on Task ")
        or ("completed successfully" in content and "Please proceed" in content)
        or _is_checkin_prompt_text(content)
        or _is_checkin_control_text(content)
    )


def _reconstruct_task_history_from_state(
    current_task_messages: list,
    evaluation_messages: list | None = None,
) -> tuple[list[dict], list[dict], list[dict]]:
    """Rebuild task-local operator/evaluator timeline items from checkpoint state."""
    operator_items = []
    evaluator_items = []
    ordered_items = []

    filtered_task_messages = _filter_checkin_session_messages(current_task_messages or [])
    filtered_eval_messages = _filter_checkin_session_messages(evaluation_messages or [])

    for msg in filtered_task_messages:
        msg_type = _get_message_type(msg)
        content = _get_content(msg).strip()

        if msg_type == "HumanMessage":
            failed_item = _extract_evaluation_failed_item(content)
            if failed_item:
                evaluator_items.append(failed_item)
                ordered_items.append(failed_item)
            continue

        if msg_type == "AIMessage":
            tool_calls = _get_tool_calls(msg)
            for tc in tool_calls:
                tool_name, tool_args, tool_id = _extract_tool_info(tc)
                if not tool_name or tool_name in {"complete_task", "submit_evaluation"}:
                    continue
                tool_item = {
                    "type": "tool",
                    "content": format_tool_display(tool_name, tool_args),
                    "tool_id": tool_id,
                    "name": tool_name,
                    "args": tool_args,
                    "agent": "operator",
                }
                operator_items.append(tool_item)
                ordered_items.append(tool_item)

            if content and not _should_skip_task_ai_content(content):
                item = {
                    "type": "model-text",
                    "content": content,
                    "agent": "operator",
                }
                operator_items.append(item)
                ordered_items.append(item)
            continue

        if msg_type == "ToolMessage":
            if isinstance(msg, dict):
                tool_call_id = msg.get("tool_call_id")
                status = msg.get("status", "")
            else:
                tool_call_id = msg.tool_call_id
                status = getattr(msg, "status", "")
            _apply_tool_message_to_task_history(
                tool_call_id,
                status,
                content,
                ordered_items,
                operator_items,
                evaluator_items,
            )

    for msg in filtered_eval_messages:
        msg_type = _get_message_type(msg)
        content = _get_content(msg).strip()

        if msg_type == "AIMessage":
            for tc in _get_tool_calls(msg):
                tool_name, tool_args, tool_id = _extract_tool_info(tc)
                if not tool_name or tool_name == "submit_evaluation":
                    continue
                tool_item = {
                    "type": "tool",
                    "content": format_tool_display(tool_name, tool_args),
                    "tool_id": tool_id,
                    "name": tool_name,
                    "args": tool_args,
                    "agent": "evaluator",
                }
                evaluator_items.append(tool_item)
                ordered_items.append(tool_item)
            continue

        if msg_type == "ToolMessage":
            if isinstance(msg, dict):
                tool_call_id = msg.get("tool_call_id")
                status = msg.get("status", "")
            else:
                tool_call_id = msg.tool_call_id
                status = getattr(msg, "status", "")
            _apply_tool_message_to_task_history(
                tool_call_id,
                status,
                content,
                ordered_items,
                operator_items,
                evaluator_items,
            )

    interrupt_items = _extract_interrupt_reason_items(current_task_messages or [])
    if interrupt_items:
        operator_items = _merge_unique_history_items(operator_items, interrupt_items)
        ordered_items = _merge_unique_history_items(ordered_items, interrupt_items)

    _merge_orphan_execute_tool_validation_items(operator_items)
    _merge_orphan_execute_tool_validation_items(evaluator_items)
    _merge_orphan_execute_tool_validation_items(ordered_items)

    return operator_items, evaluator_items, ordered_items


def _supplement_task_history_from_snapshots(
    state_values: dict,
    state_history: list | None,
    operator_items_by_task,
    evaluator_items_by_task,
    ordered_items_by_task,
) -> None:
    """Backfill task histories from per-checkpoint task-local state snapshots."""
    snapshot_values = []
    current_values = _normalize_snapshot_values(state_values)
    if current_values:
        snapshot_values.append(current_values)
    for snapshot in state_history or []:
        values = _normalize_snapshot_values(snapshot)
        if values:
            snapshot_values.append(values)

    if not snapshot_values:
        return

    richest_snapshot_by_task = {}
    for order, values in enumerate(reversed(snapshot_values)):
        task_idx = len(values.get("completed_steps", []) or [])
        plan = values.get("plan", []) or []
        if plan and task_idx >= len(plan):
            continue

        richness = _count_relevant_task_messages(values.get("current_task_messages", []))
        richness += _count_relevant_task_messages(values.get("evaluation_messages", []))
        if richness <= 0:
            continue

        existing = richest_snapshot_by_task.get(task_idx)
        if existing is None or richness > existing["richness"] or (
            richness == existing["richness"] and order > existing["order"]
        ):
            richest_snapshot_by_task[task_idx] = {
                "values": values,
                "richness": richness,
                "order": order,
            }

    for task_idx, snapshot_info in richest_snapshot_by_task.items():
        values = snapshot_info["values"]
        snapshot_operator_items, snapshot_evaluator_items, snapshot_ordered_items = _reconstruct_task_history_from_state(
            values.get("current_task_messages", []),
            values.get("evaluation_messages", []),
        )

        existing_operator_items = list(operator_items_by_task[task_idx])
        existing_evaluator_items = list(evaluator_items_by_task[task_idx])
        existing_ordered_items = list(ordered_items_by_task[task_idx])

        if len(snapshot_operator_items) > len(existing_operator_items):
            operator_items_by_task[task_idx] = _merge_unique_history_items(
                snapshot_operator_items,
                existing_operator_items,
            )

        if len(snapshot_evaluator_items) > len(existing_evaluator_items):
            evaluator_items_by_task[task_idx] = _merge_unique_history_items(
                snapshot_evaluator_items,
                existing_evaluator_items,
            )

        should_prioritize_snapshot = (
            len(snapshot_ordered_items) > len(existing_ordered_items)
            or len(snapshot_operator_items) > len(existing_operator_items)
            or len(snapshot_evaluator_items) > len(existing_evaluator_items)
        )
        if should_prioritize_snapshot and snapshot_ordered_items:
            ordered_items_by_task[task_idx] = _merge_unique_history_items(
                snapshot_ordered_items,
                existing_ordered_items,
            )


def _plan_metadata_candidate_score(msgs: list) -> tuple:
    has_revision = any(
        _get_message_type(m) == "HumanMessage"
        and REVISION_PROMPT_MARKER in _get_content(m)
        for m in msgs
    )
    has_auto_improve = any(AUTO_IMPROVE_SNIPPET in _get_content(m) for m in msgs)
    return (1 if has_revision else 0, 1 if has_auto_improve else 0, len(msgs))


def _select_messages_for_plan_metadata(
    messages: list,
    state_history: list | None,
) -> list:
    """Pick the message list that still has strategist revision / replan signals.

    Live `messages` are often shortened by summarization; older LangGraph snapshots
    may retain full planner HumanMessages needed for revised-plan history.
    """
    candidates: list[list] = []
    if messages:
        candidates.append(messages)
    for snap in state_history or []:
        vals = _normalize_snapshot_values(snap)
        if not vals:
            continue
        hist_msgs = vals.get("messages")
        if hist_msgs:
            candidates.append(_filter_checkin_session_messages(hist_msgs))
    if not candidates:
        return []
    return max(candidates, key=_plan_metadata_candidate_score)


def extract_checkpoint_history(
    state_values: dict,
    messages: list,
    is_replan: bool = False,
    state_history: list | None = None,
) -> dict:
    """
    Extract structured history from checkpoint state for CLI display.
    
    Args:
        state_values: The checkpoint state values dict
        messages: List of messages from checkpoint
        is_replan: Whether this run is a replan
        
    Returns:
        Dictionary with plan, completed_steps, operator/evaluator/strategist items grouped by task
    """
    messages = _filter_checkin_session_messages(messages)
    messages_for_plan_metadata = _select_messages_for_plan_metadata(
        messages, state_history
    )

    plan = state_values.get('plan', [])
    completed_steps = state_values.get('completed_steps', [])
    current_task_messages = state_values.get('current_task_messages', [])
    step_results = state_values.get('step_results', {})
    
    # Primacy: 1. state_values flag, 2. is_replan argument, 3. message-based heuristic
    replan_detected = state_values.get('is_replanning', is_replan)
    
    if not replan_detected:
        # Heuristic: search messages for the auto-improvement trigger
        for msg in messages_for_plan_metadata:
            content = _get_content(msg)
            if AUTO_IMPROVE_SNIPPET in content:
                replan_detected = True
                break
    
    is_replan = replan_detected
    
    # Strategist tools (tools available to strategist during planning - normal mode only, no web search)
    # In replanning mode, strategist also has search_web and fetch_web_page
    STRATEGIST_TOOLS_NORMAL = {'read_file', 'list_directory', 'analyze_image', 'grep_search'}
    STRATEGIST_TOOLS_REPLANNING = {'read_file', 'list_directory', 'analyze_image', 'grep_search', 'search_web', 'fetch_web_page'}
    # Use the combined set for history reconstruction since we need to detect both modes
    STRATEGIST_TOOLS = STRATEGIST_TOOLS_NORMAL | STRATEGIST_TOOLS_REPLANNING
    
    def _user_request_from_revision_prompt(prompt: str) -> str:
        if not prompt or USER_FEEDBACK_SECTION not in prompt:
            return ""
        return prompt.split(USER_FEEDBACK_SECTION, 1)[1].strip()

    # Extract plans from strategist's AIMessages
    # Only scan messages from the planning phase (before operator starts working)
    # to avoid matching operator analysis text that contains "Task" and "###"
    plan_events = []
    last_human_prompt = ""
    
    # Use initial_plan_content from state if available (more reliable)
    state_initial_plan = state_values.get('initial_plan_content', '').strip()
    
    for msg in messages_for_plan_metadata:
        msg_type = _get_message_type(msg)
        content = _get_content(msg).strip()

        if msg_type == 'HumanMessage' and content:
            last_human_prompt = content

        if msg_type == 'AIMessage' and content:
            tool_calls = _get_tool_calls(msg)
            
            # If this AIMessage has tool calls that are NOT strategist tools,
            # the planning phase is over — stop scanning for plans
            if tool_calls:
                tool_names = {_extract_tool_info(tc)[0] for tc in tool_calls if _extract_tool_info(tc)[0]}
                non_strategist_tools = tool_names - STRATEGIST_TOOLS
                if non_strategist_tools:
                    break
            
            # Heuristic to identify plan messages
            if 'Task' in content and ('Guidance' in content or 'Task 1' in content or '###' in content):
                plan_events.append({
                    "content": content,
                    "prompt": last_human_prompt,
                })
    
    # In standard mode, we should have two plans (initial and reviewed)
    # in replanning mode, there might only be one.
    all_plans = [event["content"] for event in plan_events]
    initial_plan_text = all_plans[0] if len(all_plans) > 1 else (state_initial_plan if state_initial_plan else "")
    full_plan_text = all_plans[-1] if all_plans else ""
    final_plan_status = "Reviewed Replan" if is_replan else "Reviewed Plan"
    final_plan_update_status = ""
    if plan_events:
        last_prompt = plan_events[-1].get("prompt", "")
        if REVISION_PROMPT_MARKER in last_prompt:
            final_plan_status = "Revised Replan from user feedback" if is_replan else "Revised Plan from user feedback"
            final_plan_update_status = "Revising plan from user feedback"

    # Every AIMessage plan that followed a user revision HumanMessage (may be multiple rounds).
    user_revised_plan_texts = [
        event["content"]
        for event in plan_events
        if REVISION_PROMPT_MARKER in event.get("prompt", "")
    ]
    user_revised_plan_feedbacks = [
        _user_request_from_revision_prompt(event.get("prompt", ""))
        for event in plan_events
        if REVISION_PROMPT_MARKER in event.get("prompt", "")
    ]
    first_user_revision_idx = next(
        (
            i
            for i, event in enumerate(plan_events)
            if REVISION_PROMPT_MARKER in event.get("prompt", "")
        ),
        None,
    )
    # Plan shown as "Reviewed Plan" before any user-requested revision (not the last intermediate revision).
    reviewed_plan_text = ""
    if first_user_revision_idx is not None and first_user_revision_idx > 0:
        reviewed_plan_text = all_plans[first_user_revision_idx - 1]

    # Track items by task
    operator_items_by_task = defaultdict(list)
    evaluator_items_by_task = defaultdict(list)
    strategist_items = []  # Strategist items (happens before any tasks)
    ordered_items_by_task = defaultdict(list)
    current_task_in_history = 0
    in_evaluator = False
    in_planning_phase = True  # Track if we're still in planning phase
    
    # STRATEGIST_TOOLS, STRATEGIST_TOOLS_NORMAL, STRATEGIST_TOOLS_REPLANNING defined above (before plan extraction)
    
    # Evaluator-specific tools (these are the only tools available to the evaluator)
    EVALUATOR_TOOLS = {'read_file', 'list_directory', 'analyze_image', 'search_web', 'fetch_web_page', 'submit_evaluation', 'grep_search'}
    
    # Pre-scan messages to identify AIMessage indices that belong to evaluator phases
    # An evaluator phase starts after DONE and ends at task completion or EVALUATION_FEEDBACK
    evaluator_message_indices = set()
    temp_in_evaluator = False
    for idx, msg in enumerate(messages):
        msg_type = _get_message_type(msg)
        content = _get_content(msg).strip()
        
        if msg_type == 'AIMessage' and content:
            if content == "DONE":
                temp_in_evaluator = True
        
        if msg_type == 'HumanMessage' and content:
            if ("completed successfully" in content and "Please proceed" in content) or "EVALUATION_FEEDBACK" in content:
                temp_in_evaluator = False
        
        # Mark AIMessages with evaluator tool calls as evaluator messages
        tool_calls = _get_tool_calls(msg)
        if temp_in_evaluator and msg_type == 'AIMessage' and tool_calls:
            tool_names = {_extract_tool_info(tc)[0] for tc in tool_calls if _extract_tool_info(tc)[0]}
            # If any tool is an evaluator tool, mark this message as evaluator message
            if tool_names & EVALUATOR_TOOLS:
                evaluator_message_indices.add(idx)
    
    # Also get evaluation_messages from state for evaluator tool calls (current task only)
    evaluation_messages = state_values.get('evaluation_messages', [])
    
    
    for msg_idx, msg in enumerate(messages):
        msg_type = _get_message_type(msg)
        content = _get_content(msg).strip()
        
        # Detect task transitions
        # Note: DONE comes from AIMessage (operator), but "completed successfully" comes from HumanMessage (evaluator)
        if msg_type == 'AIMessage' and content:
            if content == "DONE":
                in_evaluator = True
        
        # Task completion message is a HumanMessage from evaluator
        if msg_type == 'HumanMessage' and content:
            # Pass case: task completed successfully
            if "completed successfully" in content and "Please proceed" in content:
                current_task_in_history += 1
                in_evaluator = False
                # Fail case: evaluator sends feedback, operator will retry
            elif "EVALUATION_FEEDBACK" in content:
                failed_item = _extract_evaluation_failed_item(content)
                if failed_item:
                    evaluator_items_by_task[current_task_in_history].append(failed_item)
                    ordered_items_by_task[current_task_in_history].append(failed_item)
                in_evaluator = False
        
        # Extract tool calls from AIMessage
        tool_calls = _get_tool_calls(msg)
        if msg_type == 'AIMessage' and (content or tool_calls):
            # FIRST: Process tool calls BEFORE checking plan content
            # This ensures strategist tool calls are identified even if the same message contains plan content
            for tc in tool_calls:
                tool_name, tool_args, tool_id = _extract_tool_info(tc)
                
                # Skip complete_task and submit_evaluation with status='pass' (summary comes from step_results)
                # But keep submit_evaluation with status='fail' to show failed evaluations
                if not tool_name or tool_name == 'complete_task':
                    continue
                if tool_name == 'submit_evaluation' and tool_args.get('status', '').lower() == 'pass':
                    continue
                
                # Determine which agent made this tool call:
                # 1. If in_planning_phase and tool is in STRATEGIST_TOOLS -> strategist
                # 2. If in_evaluator or in evaluator_message_indices -> evaluator
                # 3. Otherwise -> operator
                is_evaluator_msg = in_evaluator or msg_idx in evaluator_message_indices
                is_strategist_msg = in_planning_phase and tool_name in STRATEGIST_TOOLS and not is_evaluator_msg
                
                if is_strategist_msg:
                    agent_name = "strategist"
                    target_list = strategist_items
                elif is_evaluator_msg:
                    agent_name = "evaluator"
                    target_list = evaluator_items_by_task[current_task_in_history]
                else:
                    agent_name = "operator"
                    target_list = operator_items_by_task[current_task_in_history]
                
                # Add tool item
                display_str = format_tool_display(tool_name, tool_args)
                tool_item = {
                    "type": "tool", 
                    "content": display_str, 
                    "tool_id": tool_id, 
                    "name": tool_name, 
                    "args": tool_args,
                    "agent": agent_name
                }
                target_list.append(tool_item)
                if not is_strategist_msg:  # Don't add strategist items to task-based ordered list
                    ordered_items_by_task[current_task_in_history].append(tool_item)
            
            # THEN: Check if there's also text content that should be displayed
            # (AIMessage can have both content AND tool_calls)
            if content:
                # Check if this is a plan message - if so, planning phase is complete
                # Do this AFTER processing tool calls so strategist tool calls are identified first
                is_plan_content = (
                    content == full_plan_text or
                    content == initial_plan_text or
                    (reviewed_plan_text and content == reviewed_plan_text) or
                    '<PLAN>' in content or 
                    '</PLAN>' in content or
                    content.startswith('### **Task 1:') or 
                    content.startswith('### Task 1:') or
                    ('### **Task' in content and '**Guidance:**' in content)
                )
                if is_plan_content:
                    in_planning_phase = False
                
                # Apply same filters as for text-only AIMessages
                should_skip = (
                    is_plan_content or
                    ("Please review your plan above" in content and "improved version" in content) or
                    "Does the plan address all aspects" in content or
                    content == "DONE" or
                    ("completed successfully" in content and "Please proceed" in content) or
                    # Skip strategist error message when user_input was empty
                    content == "Please provide a valid input or question."
                )
                
                if not should_skip:
                    # Use both in_evaluator flag and pre-computed indices for reliable detection
                    is_evaluator_msg = in_evaluator or msg_idx in evaluator_message_indices
                    agent_name = "evaluator" if is_evaluator_msg else "operator"
                    target_list = evaluator_items_by_task[current_task_in_history] if is_evaluator_msg else operator_items_by_task[current_task_in_history]
                    # Skip model-text for evaluator - the summary is captured in step_results
                    # Only add model-text for operator
                    if not is_evaluator_msg:
                        item = {
                            "type": "model-text",
                            "content": content,
                            "agent": agent_name
                        }
                        target_list.append(item)
                        ordered_items_by_task[current_task_in_history].append(item)
        
        # Handle ToolMessage (output of tools)
        elif msg_type == 'ToolMessage':
            if isinstance(msg, dict):
                tool_call_id = msg.get('tool_call_id')
                status = msg.get('status', '')
            else:
                tool_call_id = msg.tool_call_id
                status = getattr(msg, 'status', '')
            
            content_str = content
            is_error = _detect_error_in_content(content_str, status)
            
            # Search for matching tool in all lists (strategist, operator, evaluator)
            # This handles cases where the tool call was attributed to different lists
            matching_tool = None
            target_list = None
            
            # First check strategist items (not task-based)
            for item in strategist_items:
                if item.get("tool_id") == tool_call_id:
                    matching_tool = item
                    target_list = strategist_items
                    break
            
            # Then check ordered items (they contain operator and evaluator)
            if not matching_tool:
                for item in ordered_items_by_task[current_task_in_history]:
                    if item.get("tool_id") == tool_call_id:
                        matching_tool = item
                        # Also find which specific list it belongs to for the code-result insertion
                        if item.get("agent") == "evaluator":
                            target_list = evaluator_items_by_task[current_task_in_history]
                        else:
                            target_list = operator_items_by_task[current_task_in_history]
                        break
            
            if matching_tool:
                tool_name = matching_tool.get("name", "")
                tool_args = matching_tool.get("args", {})
                agent_name = matching_tool.get("agent", "operator")
                
                if is_error:
                    matching_tool["isError"] = True
                    error_content = _format_error_content(tool_name, tool_args, content_str)
                    if error_content:
                        matching_tool["content"] = error_content
                else:
                    success_content = _format_success_content(tool_name, tool_args, content_str)
                    if success_content:
                        matching_tool["content"] = success_content
                
                # Add code-result for execute_code/execute_python
                if tool_name in ("execute_code", "execute_python"):
                    # Match runtime behavior: same status line as step_complete and panel
                    # (code preamble + truncated stdout), not only the raw ToolMessage body.
                    code_result = {
                        "type": "code-result",
                        "content": {
                            "output": _execute_python_panel_output(tool_args, content_str),
                            "filePath": tool_args.get("file_path", ""),
                            "status": _step_complete_status_execute_python(tool_name, tool_args),
                        },
                        "isError": is_error,
                        "agent": agent_name
                    }
                    
                    # Insert into ordered list before the tool call
                    try:
                        idx = ordered_items_by_task[current_task_in_history].index(matching_tool)
                        ordered_items_by_task[current_task_in_history].insert(idx, code_result)
                    except ValueError:
                        ordered_items_by_task[current_task_in_history].append(code_result)
                        
                    # Also insert into the specific agent list
                    try:
                        idx = target_list.index(matching_tool)
                        target_list.insert(idx, code_result)
                    except ValueError:
                        target_list.append(code_result)
                
                # Add image-analysis-result for analyze_image
                if tool_name == "analyze_image":
                    # Extract just the analysis text (remove header if present)
                    analysis_output = content_str
                    if content_str.startswith("**Analyze Image:**"):
                        lines = content_str.split('\n', 1)
                        if len(lines) > 1:
                            analysis_output = lines[1].lstrip('> ').strip()
                    
                    image_result = {
                        "type": "image-analysis-result",
                        "content": {
                            "output": analysis_output,
                            "filePath": tool_args.get("file_path", "")
                        },
                        "isError": is_error,
                        "agent": agent_name
                    }
                    
                    # Insert into ordered list before the tool call
                    try:
                        idx = ordered_items_by_task[current_task_in_history].index(matching_tool)
                        ordered_items_by_task[current_task_in_history].insert(idx, image_result)
                    except ValueError:
                        ordered_items_by_task[current_task_in_history].append(image_result)
                        
                    # Also insert into the specific agent list
                    try:
                        idx = target_list.index(matching_tool)
                        target_list.insert(idx, image_result)
                    except ValueError:
                        target_list.append(image_result)
                
                # Add diff output for edit_file
                if tool_name == "edit_file":
                    old_string = tool_args.get('old_string', '')
                    new_string = tool_args.get('new_string', '')
                    
                    if old_string or new_string:
                        # Truncate strings if too long
                        max_len = 1500
                        old_display = old_string[:max_len] + "..." if len(old_string) > max_len else old_string
                        new_display = new_string[:max_len] + "..." if len(new_string) > max_len else new_string
                        
                        # Format as diff - each line prefixed with - or +
                        old_lines = old_display.split('\n')
                        new_lines = new_display.split('\n')
                        
                        diff_lines = []
                        for line in old_lines:
                            diff_lines.append(f"- {line}")
                        for line in new_lines:
                            diff_lines.append(f"+ {line}")
                        
                        diff_output = "```diff\n" + "\n".join(diff_lines) + "\n```"
                        
                        # Store the output in the tool item for display
                        matching_tool["output"] = diff_output

                # Add output for tools that expose collapsible details in history.
                if tool_name in ("query_rag", "grep_search", "search_web", "fetch_web_page") and content_str:
                    matching_tool["output"] = _truncate_collapsible_output(content_str)

        # Handle text content from AIMessage (model thought/text)
        elif isinstance(msg, AIMessage) and msg.content:
            content = _extract_text(msg.content).strip()
            
            # Skip if it is a plan text (already shown in dedicated headers)
            if content == full_plan_text or content == initial_plan_text or (
                reviewed_plan_text and content == reviewed_plan_text
            ):
                continue
            
            # Skip any content that looks like a plan (contains PLAN tags or Task/Guidance structure)
            if '<PLAN>' in content or '</PLAN>' in content:
                continue
            if content.startswith('### **Task 1:') or content.startswith('### Task 1:'):
                continue
            # Check if content looks like a full plan (has multiple tasks with guidance)
            if '### **Task' in content and '**Guidance:**' in content:
                continue
                
            # Skip self-review prompts
            if "Please review your plan above" in content and "improved version" in content:
                continue
            
            # Skip review feedback that contains plan-like structure  
            if "Does the plan address all aspects" in content:
                continue
                
            # Skip control messages
            if content == "DONE":
                continue
                
            # Skip "completed successfully" messages that bridge task transition
            if "completed successfully" in content and "Please proceed" in content:
                continue
            
            # Skip strategist error message when user_input was empty
            if content == "Please provide a valid input or question.":
                continue

            # Add model text item - skip for evaluator since summary is in step_results
            if not in_evaluator:
                item = {
                    "type": "model-text",
                    "content": content,
                    "agent": "operator"
                }
                operator_items_by_task[current_task_in_history].append(item)
                ordered_items_by_task[current_task_in_history].append(item)
    
    # Process evaluation_messages for the current task (evaluator's own messages)
    # These contain the evaluator's AIMessages with tool calls and ToolMessages with results
    if evaluation_messages:
        eval_target_list = evaluator_items_by_task[current_task_in_history]
        
        for msg in evaluation_messages:
            msg_type = _get_message_type(msg)
            content = _get_content(msg).strip()
            tool_calls = _get_tool_calls(msg)
            
            # Extract tool calls from evaluator's AIMessage
            if msg_type == 'AIMessage' and tool_calls:
                for tc in tool_calls:
                    tool_name, tool_args, tool_id = _extract_tool_info(tc)
                    
                    if not tool_name or tool_name == 'submit_evaluation':
                        continue
                    
                    # Add tool item
                    display_str = format_tool_display(tool_name, tool_args)
                    tool_item = {
                        "type": "tool", 
                        "content": display_str, 
                        "tool_id": tool_id, 
                        "name": tool_name, 
                        "args": tool_args,
                        "agent": "evaluator"
                    }
                    eval_target_list.append(tool_item)
                    ordered_items_by_task[current_task_in_history].append(tool_item)
            
            # Handle ToolMessage (output of tools)
            elif msg_type == 'ToolMessage':
                if isinstance(msg, dict):
                    tool_call_id = msg.get('tool_call_id')
                    status = msg.get('status', '')
                else:
                    tool_call_id = msg.tool_call_id
                    status = getattr(msg, 'status', '')
                
                content_str = content
                is_error = _detect_error_in_content(content_str, status)
                
                # Find matching tool call
                matching_tool = None
                for item in ordered_items_by_task[current_task_in_history]:
                    if item.get("tool_id") == tool_call_id and item.get("agent") == "evaluator":
                        matching_tool = item
                        break
                
                if matching_tool:
                    tool_name = matching_tool.get("name", "")
                    tool_args = matching_tool.get("args", {})
                    
                    if is_error:
                        matching_tool["isError"] = True
                        error_content = _format_error_content(tool_name, tool_args, content_str)
                        if error_content:
                            matching_tool["content"] = error_content
                    else:
                        success_content = _format_success_content(tool_name, tool_args, content_str)
                        if success_content:
                            matching_tool["content"] = success_content
                    
                    # Add output for tools that expose collapsible details in history.
                    if tool_name in ("query_rag", "grep_search", "search_web", "fetch_web_page") and content_str:
                        matching_tool["output"] = _truncate_collapsible_output(content_str)

    current_task_index = len(completed_steps)
    for item in _extract_interrupt_reason_items(current_task_messages):
        operator_items_by_task[current_task_index].append(item)
        ordered_items_by_task[current_task_index].append(item)

    _supplement_task_history_from_snapshots(
        state_values,
        state_history,
        operator_items_by_task,
        evaluator_items_by_task,
        ordered_items_by_task,
    )

    _apply_orphan_execute_merges(
        strategist_items,
        operator_items_by_task,
        evaluator_items_by_task,
        ordered_items_by_task,
    )
    
    # Build backward-compatible flat list
    operator_tools = []
    for i in range(current_task_in_history + 1):
        for item in operator_items_by_task[i]:
            if item["type"] == "tool":
                operator_tools.append(item["content"])
    
    # Clean items for JSON (remove internal fields)
    def clean_items(items_dict):
        return {
            str(k): [
                {key: val for key, val in item.items() if key not in ['tool_id', 'name', 'args']}
                for item in v
            ]
            for k, v in items_dict.items()
        }
    
    def clean_list(items_list):
        """Clean a list of items (for strategist which isn't task-based)."""
        return [
            {key: val for key, val in item.items() if key not in ['tool_id', 'name', 'args']}
            for item in items_list
        ]
    
    
    return {
        "plan": plan,
        "initial_plan_text": initial_plan_text,
        "full_plan_text": full_plan_text,
        "reviewed_plan_text": reviewed_plan_text,
        "user_revised_plan_texts": user_revised_plan_texts,
        "user_revised_plan_feedbacks": user_revised_plan_feedbacks,
        "final_plan_status": final_plan_status,
        "final_plan_update_status": final_plan_update_status,
        "completed_steps": completed_steps,
        "step_results": {str(k): v for k, v in step_results.items()},
        "current_task": len(completed_steps) + 1,
        "total_tasks": len(plan),
        "operator_tools": operator_tools,
        "operator_items_by_task": clean_items(operator_items_by_task),
        "evaluator_items_by_task": clean_items(evaluator_items_by_task),
        "ordered_items_by_task": clean_items(ordered_items_by_task),
        "strategist_items": clean_list(strategist_items),
        "is_replan": is_replan
    }
