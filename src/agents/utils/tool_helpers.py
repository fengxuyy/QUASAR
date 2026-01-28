"""
Tool execution helpers - status messages, extraction, and execution utilities.
"""

import os
import queue
import re
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable

from langchain_core.messages import ToolMessage

from .bridge import send_agent_event
from .logging import log_tool_call, _write_to_log
from .text import truncate_content
from .errors import ValidationError, format_validation_error

# Constants
DEFAULT_TIMEOUT_SECONDS = 600
MAX_REPEATED_TOOL_CALLS = 10  # Maximum allowed consecutive identical tool calls

# Tool name to status message mapping (generic for all agents)
TOOL_STATUS_MESSAGES = {
    'query_rag': ('Querying RAG', 'Queried RAG'),
    'read_file': ('Reading', 'Read'),
    'write_file': ('Writing', 'Wrote'),
    'edit_file': ('Editing', 'Edited'),
    'delete_file': ('Deleting', 'Deleted'),
    'list_directory': ('Listing directory', 'Listed directory'),
    'move_file': ('Moving', 'Moved'),
    'rename_file': ('Renaming', 'Renamed'),
    'analyze_image': ('Analyzing image', 'Analyzed image'),
    'search_web': ('Searching web', 'Searched web'),
    'fetch_web_page': ('Fetching web page', 'Fetched web page'),
    'execute_python': ('Executing', 'Executed'),
    'grep_search': ('Searching files', 'Searched files'),
    'get_hardware_info': ('Checking Hardware', 'Checked Hardware'),
    'complete_task': ('Evaluating Task Completion', 'Evaluating Task Completion'),
}

# Default idle status per agent
AGENT_IDLE_STATUS = {
    'operator': 'Analysing Task',
    'evaluator': 'Evaluating Task Completion',
    'strategist': 'Analysing Request',
}


def extract_tool_call_info(tool_call) -> tuple:
    """Extract tool name, args, and ID from tool call (dict or object).
    
    Returns:
        tuple: (tool_name, tool_args, tool_call_id)
    """
    if isinstance(tool_call, dict):
        return tool_call.get('name', ''), tool_call.get('args', {}), tool_call.get('id', '')
    return getattr(tool_call, 'name', ''), getattr(tool_call, 'args', {}), getattr(tool_call, 'id', '')


def extract_target_name(tool_name: str, tool_args: dict) -> Optional[str]:
    """Extract the target file/directory name from tool arguments for status messages."""
    if not isinstance(tool_args, dict):
        return None
    
    target_keys = {
        'read_file': 'file_path',
        'write_file': 'file_path',
        'edit_file': 'file_path',
        'delete_file': 'file_path',
        'list_directory': 'directory_path',
        'move_file': 'source_path',
        'rename_file': 'old_path',
        'analyze_image': 'image_path',
        'execute_python': 'file_path',
    }
    
    key = target_keys.get(tool_name)
    if key and key in tool_args:
        target = tool_args[key]
        if isinstance(target, (str, Path)):
            return os.path.basename(str(target))
    
    # Handle default values for tools with optional path arguments
    if tool_name == 'list_directory' and 'directory_path' not in tool_args:
        return '.'
    
    # Special handling for search_web - show query
    if tool_name == 'search_web':
        query = tool_args.get('query', '')
        if query:
            display_query = query[:50] + '...' if len(query) > 50 else query
            return f"{display_query}"
        return None
    
    # Special handling for fetch_web_page - show domain/URL
    if tool_name == 'fetch_web_page':
        url = tool_args.get('url', '')
        if url:
            try:
                from urllib.parse import urlparse
                parsed = urlparse(url)
                domain = parsed.netloc or url[:40]
                path = parsed.path[:20] if parsed.path else ''
                display_url = f"{domain}{path}" if len(domain + path) <= 50 else domain
                return display_url
            except:
                return url[:50] + '...' if len(url) > 50 else url
        return None
    
    # Special handling for grep_search - show pattern being searched
    if tool_name == 'grep_search':
        pattern = tool_args.get('pattern', '')
        if pattern:
            display_pattern = pattern[:50] + '...' if len(pattern) > 50 else pattern
            return f"{display_pattern}"
        return None
    
    return None


def extract_analyze_image_output(result: str) -> str:
    """Extract just the analysis text from analyze_image result.
    
    Removes the **Analyze Image:** header if present and returns clean text.
    Truncates to 5000 characters for display purposes.
    
    Args:
        result: The raw result string from analyze_image tool
        
    Returns:
        str: Cleaned analysis text
    """
    if not result or not isinstance(result, str):
        return ""
    
    output = result
    if result.startswith("**Analyze Image:**"):
        lines = result.split('\n', 1)
        if len(lines) > 1:
            output = lines[1].lstrip('> ').strip()
    
    return output[:5000] if len(output) > 5000 else output


def handle_analyze_image_status(
    agent: str,
    tool_args: dict,
    result: str
) -> None:
    """Send step_complete event with output for analyze_image tool.
    
    Shared handler for both operator and evaluator to avoid code duplication.
    
    Args:
        agent: Agent name ('operator' or 'evaluator')
        tool_args: Tool arguments dict containing 'file_path'
        result: Raw result string from analyze_image tool
    """
    file_path = tool_args.get('file_path') if isinstance(tool_args, dict) else None
    file_name = os.path.basename(file_path) if file_path else 'image'
    complete_msg = f"Analyzed {file_name}"
    
    output = extract_analyze_image_output(result)
    is_error = result.startswith("Error:") if isinstance(result, str) else False
    
    send_agent_event(agent, "step_complete", complete_msg, is_error=is_error, output=output)
    
    # Reset to idle status after completion
    idle_status = AGENT_IDLE_STATUS.get(agent, "Idle")
    send_agent_event(agent, "update", idle_status)


# ============================================================================
# Detailed Tool Status Handlers (merged from operator_status.py)
# ============================================================================

def _handle_read_file_status(agent: str, tool_args: Dict[str, Any], target_name: Optional[str], is_complete: bool, tool_result: Optional[str]) -> None:
    """Handle read_file status updates with special context awareness."""
    if_pdf = tool_args.get('if_pdf', False) if isinstance(tool_args, dict) else False
    keyword = tool_args.get('keyword') if isinstance(tool_args, dict) else None
    first_lines = tool_args.get('first_lines') if isinstance(tool_args, dict) else None
    last_lines = tool_args.get('last_lines') if isinstance(tool_args, dict) else None
    file_name = target_name  # Don't use fallback 'file' - it gets incorrectly linked
    
    # Detect errors in tool result
    is_error = False
    is_file_not_found = False
    is_validation_error = False
    error_output = None
    if is_complete and tool_result and isinstance(tool_result, str):
        result_lower = tool_result.lower()
        if tool_result.startswith("Error:") or "not found" in result_lower or "does not exist" in result_lower:
            is_error = True
            # Check if it's specifically a file not found error (not keyword not found)
            if "file" in result_lower and ("not found" in result_lower or "does not exist" in result_lower):
                is_file_not_found = True
        # Check for validation errors (e.g., missing file_path)
        if "validation error" in result_lower or "field required" in result_lower:
            is_error = True
            is_validation_error = True
            error_output = tool_result
    
    # Handle validation errors (missing file_path) - show generic error message
    if is_validation_error or not file_name:
        idle_status = AGENT_IDLE_STATUS.get(agent, "Idle")
        if is_complete:
            send_agent_event(agent, "step_complete", "Failed to read file", is_error=True, output=error_output)
            send_agent_event(agent, "update", idle_status)
        else:
            send_agent_event(agent, "update", "Reading file...")
        return
    
    # Priority: if_pdf > keyword > first_lines > last_lines > default
    if if_pdf:
        base_status = f"Reading PDF {file_name}"
        if is_error:
            if is_file_not_found:
                base_complete = f"{file_name} not found"
            else:
                base_complete = f"Failed to read PDF {file_name}"
        else:
            base_complete = f"Read PDF {file_name}"
    elif keyword:
        base_status = f"Searching {keyword} in {file_name}"
        # Extract match count from tool result for completion message
        match_count = None
        if is_complete and tool_result and isinstance(tool_result, str):
            match = re.search(r"at line\(s\) ([\d,\s]+)", tool_result)
            if match:
                lines_str = match.group(1)
                match_count = len([l.strip() for l in lines_str.split(',') if l.strip()])
        if is_error:
            if is_file_not_found:
                base_complete = f"{file_name} not found"
            else:
                # Keyword not found
                base_complete = f"{keyword} not found in {file_name}"
        elif match_count:
            match_word = "match" if match_count == 1 else "matches"
            base_complete = f"Searched {keyword} in {file_name} ({match_count} {match_word})"
        else:
            base_complete = f"Searched {keyword} in {file_name}"
    elif first_lines:
        base_status = f"Reading {file_name} L1-{first_lines}"
        if is_error:
            base_complete = f"{file_name} not found"
        else:
            base_complete = f"Read {file_name} L1-{first_lines}"
    elif last_lines:
        base_status = f"Reading {file_name} last {last_lines} lines"
        if is_error:
            base_complete = f"{file_name} not found"
        else:
            base_complete = f"Read {file_name} last {last_lines} lines"
    else:
        base_status = f"Reading {file_name}"
        if is_error:
            base_complete = f"{file_name} not found"
        else:
            base_complete = f"Read {file_name}"
    
    idle_status = AGENT_IDLE_STATUS.get(agent, "Idle")
    if is_complete:
        send_agent_event(agent, "step_complete", base_complete, is_error=is_error)
        send_agent_event(agent, "update", idle_status)
    else:
        send_agent_event(agent, "update", base_status)


def _handle_query_rag_status(agent: str, tool_args: Dict[str, Any], is_complete: bool, tool_result: Optional[str] = None) -> None:
    """Handle query_rag status updates."""
    query = tool_args.get('query', '') if isinstance(tool_args, dict) else ''
    library = tool_args.get('library', '') if isinstance(tool_args, dict) else ''
    display_query = query[:40] + '...' if len(query) > 40 else query
    
    # Detect errors in tool result (including validation errors)
    is_error = False
    error_output = None
    if is_complete and tool_result and isinstance(tool_result, str):
        result_lower = tool_result.lower()
        if (tool_result.startswith("Error:") or 
            "not found" in result_lower or 
            "no results" in result_lower or
            "validation error" in result_lower or
            "field required" in result_lower):
            is_error = True
            # Include the error message as output for collapsible display
            error_output = tool_result
    
    idle_status = AGENT_IDLE_STATUS.get(agent, "Idle")
    if is_complete:
        if is_error:
            # For validation errors, show a cleaner status message
            if "validation error" in (tool_result or '').lower():
                status_msg = "Query RAG Failed"
            else:
                if library:
                    status_msg = f"Queried RAG {display_query} in {library}"
                else:
                    status_msg = f"Queried RAG {display_query}" if display_query else "Queried RAG"
            send_agent_event(agent, "step_complete", status_msg, is_error=True, output=error_output)
        else:
            if library:
                status_text = f"{display_query} in {library}"
            else:
                status_text = f"{display_query}"
            send_agent_event(agent, "step_complete", f"Queried RAG {status_text}", is_error=False)
        send_agent_event(agent, "update", idle_status)
    else:
        if library:
            send_agent_event(agent, "update", f"Querying RAG {display_query} in {library}")
        else:
            send_agent_event(agent, "update", f"Querying RAG {display_query}")


def _handle_search_web_status(agent: str, tool_args: Dict[str, Any], is_complete: bool, tool_result: Optional[str] = None) -> None:
    """Handle search_web status updates."""
    query = tool_args.get('query', '') if isinstance(tool_args, dict) else ''
    display_query = query[:50] + '...' if len(query) > 50 else query
    
    # Detect errors and extract result count
    is_error = False
    result_count = None
    if is_complete and tool_result and isinstance(tool_result, str):
        if tool_result.startswith("Error:") or "No results found" in tool_result:
            is_error = True
        else:
            # Count results by looking for [Result N] patterns
            matches = re.findall(r'\[Result \d+\]', tool_result)
            if matches:
                result_count = len(matches)
    
    idle_status = AGENT_IDLE_STATUS.get(agent, "Idle")
    if is_complete:
        if is_error:
            if "No results found" in (tool_result or ''):
                msg = f"No results for {display_query}"
            else:
                msg = f"Search failed for {display_query}"
        elif result_count:
            result_word = "result" if result_count == 1 else "results"
            msg = f"Searched {display_query} ({result_count} {result_word})"
        else:
            msg = f"Searched {display_query}"
        send_agent_event(agent, "step_complete", msg, is_error=is_error)
        send_agent_event(agent, "update", idle_status)
    else:
        send_agent_event(agent, "update", f"Searching {display_query}")


def _handle_fetch_web_page_status(agent: str, tool_args: Dict[str, Any], is_complete: bool, tool_result: Optional[str] = None) -> None:
    """Handle fetch_web_page status updates."""
    url = tool_args.get('url', '') if isinstance(tool_args, dict) else ''
    
    # Extract domain or truncated URL for display
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        domain = parsed.netloc or url[:40]
        path = parsed.path[:20] if parsed.path else ''
        display_url = f"{domain}{path}" if len(domain + path) <= 50 else domain
    except:
        display_url = url[:50] + '...' if len(url) > 50 else url
    
    # Detect errors and extract content info
    is_error = False
    content_length = None
    is_truncated = False
    if is_complete and tool_result and isinstance(tool_result, str):
        if tool_result.startswith("Error:"):
            is_error = True
        else:
            # Check if content was truncated
            if "truncated" in tool_result.lower():
                is_truncated = True
            # Estimate content length (rough count)
            content_length = len(tool_result)
    
    idle_status = AGENT_IDLE_STATUS.get(agent, "Idle")
    if is_complete:
        if is_error:
            # Extract specific error type
            if "Invalid URL" in (tool_result or ''):
                msg = f"Invalid URL: {display_url}"
            elif "Failed to fetch" in (tool_result or ''):
                msg = f"Failed to fetch {display_url}"
            else:
                msg = f"Error fetching {display_url}"
        else:
            if is_truncated:
                msg = f"Fetched {display_url} (truncated)"
            elif content_length:
                if content_length < 1000:
                    msg = f"Fetched {display_url} ({content_length} chars)"
                else:
                    msg = f"Fetched {display_url} ({content_length // 1000}k chars)"
            else:
                msg = f"Fetched {display_url}"
        send_agent_event(agent, "step_complete", msg, is_error=is_error)
        send_agent_event(agent, "update", idle_status)
    else:
        send_agent_event(agent, "update", f"Fetching {display_url}")


def _handle_execute_python_status(agent: str, tool_args: Dict[str, Any], is_complete: bool, tool_result: Optional[str] = None) -> None:
    """Handle execute_python status updates."""
    file_path = tool_args.get('file_path') if isinstance(tool_args, dict) else None
    code = tool_args.get('code') if isinstance(tool_args, dict) else None
    
    if file_path:
        # Case 1 & 3: file_path provided (with or without code)
        file_name = os.path.basename(file_path)
        base_status = f"Executing {file_name}"
        base_complete = f"Executed {file_name}"
    elif code:
        # Case 2: Only code provided - show truncated code preview
        # Get first line or first 50 chars, whichever is shorter
        first_line = code.strip().split('\n')[0]
        code_preview = first_line[:50]
        if len(first_line) > 50 or '\n' in code.strip():
            code_preview += "..."
        base_status = f"Executing {code_preview}"
        base_complete = f"Executed {code_preview}"
    else:
        base_status = "Executing"
        base_complete = "Executed"
    
    idle_status = AGENT_IDLE_STATUS.get(agent, "Idle")
    if is_complete:
        # Detect errors in tool result by checking for non-zero exit code
        is_error = False
        if tool_result and isinstance(tool_result, str):
            result_lower = tool_result.lower()
            # Check for non-zero exit code - match "exit code: N" where N != 0
            exit_code_match = re.search(r'exit code:\s*(\d+)', result_lower)
            if exit_code_match:
                exit_code = int(exit_code_match.group(1))
                if exit_code != 0:
                    is_error = True
            # Also check for explicit error messages
            elif 'error executing code' in result_lower or 'traceback' in result_lower:
                is_error = True
        
        # Build output: for code-only execution, prepend the full code
        output = ""
        if code and not file_path:
            # Prepend full code for inline execution (helps with collapsible display)
            output = f"**Code:**\n```python\n{code}\n```\n\n"
        
        if tool_result and isinstance(tool_result, str):
            truncated_result = tool_result[:2000] if len(tool_result) > 2000 else tool_result
            output += truncated_result
        
        send_agent_event(agent, "step_complete", base_complete, is_error=is_error, output=output)
        send_agent_event(agent, "update", idle_status)
    else:
        send_agent_event(agent, "update", base_status + "...")


def _handle_write_file_status(agent: str, tool_args: Dict[str, Any], is_complete: bool) -> None:
    """Handle write_file status updates with content preview."""
    file_path = tool_args.get('file_path') if isinstance(tool_args, dict) else None
    content = tool_args.get('content', '') if isinstance(tool_args, dict) else ''
    
    file_name = os.path.basename(file_path) if file_path else 'file'
    base_status = f"Writing {file_name}"
    base_complete = f"Wrote {file_name}"
    
    idle_status = AGENT_IDLE_STATUS.get(agent, "Idle")
    if is_complete:
        # Truncate content if too long for display
        output = ""
        if content and isinstance(content, str):
            output = content[:3000] if len(content) > 3000 else content
        send_agent_event(agent, "step_complete", base_complete, output=output)
        send_agent_event(agent, "update", idle_status)
    else:
        send_agent_event(agent, "update", base_status + "...")


def _handle_edit_file_status(agent: str, tool_args: Dict[str, Any], is_complete: bool, tool_result: Optional[str] = None) -> None:
    """Handle edit_file status updates with diff display."""
    file_path = tool_args.get('file_path') if isinstance(tool_args, dict) else None
    old_string = tool_args.get('old_string', '') if isinstance(tool_args, dict) else ''
    new_string = tool_args.get('new_string', '') if isinstance(tool_args, dict) else ''
    
    file_name = os.path.basename(file_path) if file_path else 'file'
    base_status = f"Editing {file_name}"
    base_complete = f"Edited {file_name}"
    
    # Detect errors in tool result
    is_error = False
    if is_complete and tool_result and isinstance(tool_result, str):
        result_lower = tool_result.lower()
        if tool_result.startswith("Error:") or "not found" in result_lower or "does not exist" in result_lower:
            is_error = True
    
    idle_status = AGENT_IDLE_STATUS.get(agent, "Idle")
    if is_complete:
        # Build diff output in GitHub-style format
        output = ""
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
            
            output = "```diff\n" + "\n".join(diff_lines) + "\n```"
        
        send_agent_event(agent, "step_complete", base_complete, is_error=is_error, output=output)
        send_agent_event(agent, "update", idle_status)
    else:
        send_agent_event(agent, "update", base_status + "...")


def _handle_list_directory_status(agent: str, tool_args: Dict[str, Any], is_complete: bool, tool_result: Optional[str] = None) -> None:
    """Handle list_directory status updates."""
    directory_path = tool_args.get('directory_path', '.') if isinstance(tool_args, dict) else '.'
    pattern = tool_args.get('pattern', '*') if isinstance(tool_args, dict) else '*'
    
    # Detect errors in tool result
    is_error = False
    if is_complete and tool_result and isinstance(tool_result, str):
        result_lower = tool_result.lower()
        if tool_result.startswith("Error:") or "not found" in result_lower or "does not exist" in result_lower or "no files found" in result_lower:
            is_error = True
    
    # Check if using default values and extract display name (basename only)
    is_default = (directory_path == '.' or directory_path == '') and (pattern == '*' or pattern == '')
    path_display = os.path.basename(directory_path.rstrip('/')) if directory_path and directory_path != '.' else 'workspace'
    # Determine error type for appropriate message
    is_no_files_error = is_error and tool_result and "no files found" in tool_result.lower()
    
    if is_default:
        base_status = "Listing workspace"
        if is_error:
            if is_no_files_error:
                base_complete = "No files found in workspace"
            else:
                base_complete = "Workspace not found"
        else:
            base_complete = "Listed workspace"
    else:
        if pattern and pattern != '*':
            base_status = f"Listing {path_display} ({pattern})"
            if is_error:
                if is_no_files_error:
                    base_complete = f"No files found matching {pattern} in {path_display}"
                else:
                    base_complete = f"{path_display} directory not found"
            else:
                base_complete = f"Listed {path_display} ({pattern})"
        else:
            base_status = f"Listing {path_display}"
            if is_error:
                if is_no_files_error:
                    base_complete = f"No files found in {path_display}"
                else:
                    base_complete = f"{path_display} directory not found"
            else:
                base_complete = f"Listed {path_display}"
    
    idle_status = AGENT_IDLE_STATUS.get(agent, "Idle")
    if is_complete:
        send_agent_event(agent, "step_complete", base_complete, is_error=is_error)
        send_agent_event(agent, "update", idle_status)
    else:
        send_agent_event(agent, "update", base_status)


def _handle_analyze_image_detailed_status(agent: str, tool_args: Dict[str, Any], is_complete: bool, tool_result: Optional[str] = None) -> None:
    """Handle analyze_image status updates with analysis output."""
    if is_complete and tool_result:
        # Use shared helper for step_complete with output
        handle_analyze_image_status(agent, tool_args, tool_result)
    else:
        file_path = tool_args.get('file_path') if isinstance(tool_args, dict) else None
        file_name = os.path.basename(file_path) if file_path else 'image'
        send_agent_event(agent, "update", f"Analyzing {file_name}")


def _handle_grep_search_status(agent: str, tool_args: Dict[str, Any], is_complete: bool, tool_result: Optional[str] = None) -> None:
    """Handle grep_search status updates with match count and error detection."""
    pattern = tool_args.get('pattern', '') if isinstance(tool_args, dict) else ''
    directory_path = tool_args.get('directory_path', '.') if isinstance(tool_args, dict) else '.'
    
    # Truncate pattern for display
    display_pattern = pattern[:50] + '...' if len(pattern) > 50 else pattern
    
    # Format directory for display
    if directory_path and directory_path != '.':
        dir_name = os.path.basename(str(directory_path).rstrip('/'))
        dir_suffix = f" in {dir_name}"
    else:
        dir_suffix = ""
    
    # Detect errors and extract match count from tool result
    is_error = False
    match_count = None
    is_truncated = False
    if is_complete and tool_result and isinstance(tool_result, str):
        result_lower = tool_result.lower()
        if tool_result.startswith("Error:") or "no matches found" in result_lower or "timed out" in result_lower:
            is_error = True
        elif "does not exist" in result_lower or "not a directory" in result_lower:
            is_error = True
        else:
            # Count matches by looking for "Found X matches" pattern
            import re
            match_re = re.search(r'Found (\d+) matches', tool_result)
            if match_re:
                match_count = int(match_re.group(1))
            
            # Check for truncation
            is_truncated = "truncated" in result_lower or "showing" in result_lower
    
    idle_status = AGENT_IDLE_STATUS.get(agent, "Idle")
    if is_complete:
        if is_error:
            if "timed out" in (tool_result or '').lower():
                msg = f"Search timed out for {display_pattern}"
            elif "no matches found" in (tool_result or '').lower():
                msg = f"No matches for {display_pattern}{dir_suffix}"
            elif "does not exist" in (tool_result or '').lower() or "not a directory" in (tool_result or '').lower():
                msg = f"Directory not found{dir_suffix}"
            else:
                msg = f"Search failed for {display_pattern}"
        elif match_count is not None:
            match_word = "match" if match_count == 1 else "matches"
            truncated_text = " (truncated)" if is_truncated else ""
            msg = f"Searched files {display_pattern}{dir_suffix} ({match_count} {match_word}{truncated_text})"
        else:
            msg = f"Searched files {display_pattern}{dir_suffix}"
        send_agent_event(agent, "step_complete", msg, is_error=is_error)
        send_agent_event(agent, "update", idle_status)
    else:
        send_agent_event(agent, "update", f"Searching files {display_pattern}{dir_suffix}")


def _handle_get_hardware_info_status(agent: str, is_complete: bool, tool_result: Optional[str] = None) -> None:
    """Handle get_hardware_info status updates."""
    # Detect errors in tool result
    is_error = False
    if is_complete and tool_result and isinstance(tool_result, str):
        if tool_result.startswith("Error:") or "error" in tool_result.lower():
            is_error = True
    
    idle_status = AGENT_IDLE_STATUS.get(agent, "Idle")
    if is_complete:
        if is_error:
            send_agent_event(agent, "step_complete", "Hardware Check Failed", is_error=True)
        else:
            send_agent_event(agent, "step_complete", "Checked Hardware", is_error=False)
        send_agent_event(agent, "update", idle_status)
    else:
        send_agent_event(agent, "update", "Checking Hardware")




# ============================================================================
# Main Status Update Function (generic for any agent)
# ============================================================================

def update_agent_status(
    agent: str,
    tool_name: Optional[str],
    tool_args: Optional[Dict[str, Any]],
    is_complete: bool = False,
    tool_result: Optional[str] = None
) -> None:
    """Update agent status with context-aware messages.
    
    This function handles special cases for different tools to provide
    meaningful status updates to the CLI. Works for any agent.
    
    Args:
        agent: Agent name ('operator', 'evaluator', 'strategist')
        tool_name: Name of the tool being executed
        tool_args: Tool arguments dictionary
        is_complete: Whether the tool execution is complete
        tool_result: Optional tool result (used for extracting match counts, etc.)
    """
    idle_status = AGENT_IDLE_STATUS.get(agent, "Idle")
    
    if tool_name is None:
        send_agent_event(agent, "update", idle_status)
        return
    
    target_name = extract_target_name(tool_name, tool_args) if tool_args else None
    
    # Special handling for read_file - context-aware status messages
    if tool_name == 'read_file':
        _handle_read_file_status(agent, tool_args, target_name, is_complete, tool_result)
        return
    
    # Special handling for query_rag - show query and library in status
    if tool_name == 'query_rag':
        _handle_query_rag_status(agent, tool_args, is_complete, tool_result)
        return
    
    # Special handling for search_web - show query in status
    if tool_name == 'search_web':
        _handle_search_web_status(agent, tool_args, is_complete, tool_result)
        return
    
    # Special handling for fetch_web_page - show URL in status
    if tool_name == 'fetch_web_page':
        _handle_fetch_web_page_status(agent, tool_args, is_complete, tool_result)
        return
    
    # Special handling for execute_python
    if tool_name == 'execute_python':
        _handle_execute_python_status(agent, tool_args, is_complete, tool_result)
        return
    
    # Special handling for list_directory - show directory and pattern
    if tool_name == 'list_directory':
        _handle_list_directory_status(agent, tool_args, is_complete, tool_result)
        return
    
    # Special handling for write_file - show content being written
    if tool_name == 'write_file':
        _handle_write_file_status(agent, tool_args, is_complete)
        return
    
    # Special handling for edit_file - show diff of old and new content
    if tool_name == 'edit_file':
        _handle_edit_file_status(agent, tool_args, is_complete, tool_result)
        return
    
    # Skip complete_task entirely - the evaluator handles its own "start" event
    if tool_name == 'complete_task':
        return
    
    # Special handling for analyze_image - include the analysis in output
    if tool_name == 'analyze_image':
        _handle_analyze_image_detailed_status(agent, tool_args, is_complete, tool_result)
        return
    
    # Special handling for grep_search - show pattern and match count
    if tool_name == 'grep_search':
        _handle_grep_search_status(agent, tool_args, is_complete, tool_result)
        return
    
    # Special handling for get_hardware_info
    if tool_name == 'get_hardware_info':
        _handle_get_hardware_info_status(agent, is_complete, tool_result)
        return

    
    # Default handling for other tools
    send_tool_status(
        agent, tool_name, tool_args, 
        is_complete=is_complete, 
        tool_result=tool_result,
        idle_status=idle_status if is_complete else None
    )


def update_operator_status(
    tool_name: Optional[str],
    tool_args: Optional[Dict[str, Any]],
    is_complete: bool = False,
    tool_result: Optional[str] = None
) -> None:
    """Update operator status with context-aware messages.
    
    This is a convenience wrapper for update_agent_status with agent='operator'.
    Maintained for backwards compatibility.
    """
    update_agent_status("operator", tool_name, tool_args, is_complete, tool_result)


# ============================================================================
# Simple Tool Status Helpers
# ============================================================================

def format_tool_status(
    tool_name: str,
    tool_args: dict,
    is_complete: bool = False,
    tool_result: str = None
) -> tuple:
    """Generate consistent tool status messages for any agent.
    
    Returns formatted status/complete messages based on tool name and arguments.
    This is a simple helper for basic status formatting. For detailed status 
    with error detection and result parsing, use update_agent_status instead.
    
    Args:
        tool_name: Name of the tool being executed
        tool_args: Tool arguments dictionary
        is_complete: Whether the tool execution is complete
        tool_result: Optional tool result (used for error detection)
        
    Returns:
        tuple: (message, is_error) - the formatted message and error flag
    """
    # Detect errors in tool result
    is_error = False
    is_validation_error = False
    if is_complete and tool_result and isinstance(tool_result, str):
        result_lower = tool_result.lower()
        if tool_result.startswith("Error:") or "not found" in result_lower:
            is_error = True
        if "validation error" in result_lower or "field required" in result_lower:
            is_error = True
            is_validation_error = True
    
    # Handle validation errors with friendly failure messages
    if is_validation_error:
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
            'grep_search': 'Search Files Failed',
            'get_hardware_info': 'Hardware Check Failed',
        }
        return tool_error_names.get(tool_name, f"{tool_name} Failed"), is_error
    
    # Get target name for display
    target_name = extract_target_name(tool_name, tool_args) if tool_args else None
    
    # Use TOOL_STATUS_MESSAGES for basic formatting
    if tool_name in TOOL_STATUS_MESSAGES:
        status_verb, complete_verb = TOOL_STATUS_MESSAGES[tool_name]
        if target_name:
            msg = f"{complete_verb} {target_name}" if is_complete else f"{status_verb} {target_name}"
        else:
            msg = complete_verb if is_complete else status_verb
        return msg, is_error
    
    # Fallback for unknown tools
    if target_name:
        msg = f"Used {tool_name}: {target_name}" if is_complete else f"Using {tool_name}: {target_name}"
    else:
        msg = f"Used {tool_name}" if is_complete else f"Using {tool_name}"
    return msg, is_error


def send_tool_status(
    agent: str,
    tool_name: str,
    tool_args: dict,
    is_complete: bool = False,
    tool_result: str = None,
    idle_status: str = None
) -> None:
    """Send tool status update/step_complete event for any agent.
    
    Convenience wrapper that combines format_tool_status with send_agent_event.
    
    Args:
        agent: Agent name ('operator', 'evaluator', 'strategist')
        tool_name: Name of the tool being executed
        tool_args: Tool arguments dictionary
        is_complete: Whether the tool execution is complete
        tool_result: Optional tool result (used for error detection)
        idle_status: Optional idle status to send after completion
    """
    msg, is_error = format_tool_status(tool_name, tool_args, is_complete, tool_result)
    
    if is_complete:
        send_agent_event(agent, "step_complete", msg, is_error=is_error)
        if idle_status:
            send_agent_event(agent, "update", idle_status)
    else:
        send_agent_event(agent, "update", msg)


# ============================================================================
# Tool Call Detection and Execution
# ============================================================================

def detect_repeated_tool_calls(
    messages: List[Any],
    threshold: int = None
) -> Optional[tuple]:
    """Detect if the same tool is being called with identical arguments repeatedly.
    
    Scans the message history for consecutive AIMessage tool calls with the same
    tool name and arguments. If the count exceeds the threshold, returns the
    tool name and count.
    
    Args:
        messages: List of messages to scan
        threshold: Number of consecutive calls to trigger detection (default: MAX_REPEATED_TOOL_CALLS)
        
    Returns:
        tuple: (tool_name, call_count) if threshold exceeded, None otherwise
    """
    if threshold is None:
        threshold = MAX_REPEATED_TOOL_CALLS
    
    from langchain_core.messages import AIMessage
    import json
    
    # Collect last N tool calls from AIMessages
    tool_call_signatures = []
    
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and hasattr(msg, 'tool_calls') and msg.tool_calls:
            for tc in msg.tool_calls:
                tc_name, tc_args, _ = extract_tool_call_info(tc)
                if tc_name:
                    # Create a signature for comparison
                    try:
                        args_str = json.dumps(tc_args, sort_keys=True)
                    except:
                        args_str = str(tc_args)
                    signature = f"{tc_name}:{args_str}"
                    tool_call_signatures.append((tc_name, signature))
        
        # Only look at recent messages
        if len(tool_call_signatures) >= threshold + 5:
            break
    
    if not tool_call_signatures:
        return None
    
    # Check for consecutive identical calls (in chronological order)
    tool_call_signatures.reverse()
    
    if len(tool_call_signatures) < threshold:
        return None
    
    # Count consecutive identical calls at the end
    last_signature = tool_call_signatures[-1][1]
    consecutive_count = 0
    
    for tool_name, signature in reversed(tool_call_signatures):
        if signature == last_signature:
            consecutive_count += 1
        else:
            break
    
    if consecutive_count >= threshold:
        tool_name = tool_call_signatures[-1][0]
        return (tool_name, consecutive_count)
    
    return None


def _execute_with_timeout(func, timeout_seconds, *args, **kwargs):
    """Execute a function with a timeout using threading.
    
    Returns:
        tuple: (result, exception, timed_out)
    """
    result_queue = queue.Queue()
    exception_queue = queue.Queue()
    
    def target():
        try:
            result_queue.put(func(*args, **kwargs))
        except Exception as e:
            exception_queue.put(e)
    
    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(timeout=timeout_seconds)
    
    timed_out = thread.is_alive()
    exception = exception_queue.get() if not exception_queue.empty() else None
    result = result_queue.get() if not result_queue.empty() else None
    
    return result, exception, timed_out


def execute_with_timeout(func, timeout_seconds, *args, **kwargs):
    """Execute a function with a timeout. Returns the result or a timeout message."""
    result, exception, timed_out = _execute_with_timeout(func, timeout_seconds, *args, **kwargs)
    
    if timed_out:
        return f"Tool execution timed out (exceeded {timeout_seconds // 60} minutes). Please try a different approach or optimize the operation."
    if exception:
        if ValidationError and isinstance(exception, ValidationError):
            return format_validation_error(exception)
        return f"Error during tool execution: {str(exception)}"
    if result is not None:
        return result
    return "Tool execution completed but no result was returned."


def execute_tool_with_logging(
    tool_call,
    tool_map: Dict[str, Any],
    timeout: int,
    agent_name: str = "agent",
    status_messages: Dict[str, tuple] = None,
    on_status_update: Callable[[str, dict, bool], None] = None,
    log_result: bool = True,
    max_result_chars: int = None
) -> tuple:
    """Execute a tool call with logging and status updates.
    
    This is a shared function for executing tools across all agents.
    
    Args:
        tool_call: Tool call object or dict with 'name', 'args', 'id'
        tool_map: Dictionary mapping tool names to tool functions
        timeout: Timeout in seconds for tool execution
        agent_name: Name of the agent (for logging)
        status_messages: Optional dict mapping tool names to (status_msg, complete_msg) tuples
        on_status_update: Optional callback(tool_name, tool_args, is_complete) for status updates
        log_result: Whether to log tool results to conversation.md
        max_result_chars: Maximum characters for result logging (None = no limit)
        
    Returns:
        tuple: (result, tool_message) where tool_message is a ToolMessage object
    """
    tool_name, tool_args, tool_call_id = extract_tool_call_info(tool_call)
    target_name = extract_target_name(tool_name, tool_args)
    
    tool = tool_map.get(tool_name)
    
    if not tool:
        error_msg = f"Error: Tool {tool_name} not available to {agent_name}."
        return None, ToolMessage(content=error_msg, tool_call_id=tool_call_id)
    
    # Update status before execution
    if status_messages and tool_name in status_messages and on_status_update:
        status_msg, _ = status_messages[tool_name]
        on_status_update(tool_name, tool_args, False)
    
    # Log tool call start
    log_tool_call(tool_name, target_name, status="started", agent=agent_name)
    
    # Execute tool with timeout
    result = execute_with_timeout(tool.invoke, timeout, tool_args)
    
    # Log tool completion
    log_tool_call(tool_name, target_name, status="completed", agent=agent_name)
    
    # Update status after execution
    if status_messages and tool_name in status_messages and on_status_update:
        _, complete_msg = status_messages[tool_name]
        on_status_update(tool_name, tool_args, True)
    
    # Log tool result if requested
    if log_result and result and isinstance(result, str):
        # Improved formatting: wrap result in blockquotes
        log_content = result
        if max_result_chars:
            log_content = truncate_content(
                log_content,
                max_result_chars,
                "\n\n*... [Output truncated for log brevity]*"
            )
        # Wrap content in blockquotes for consistency with input_messages.md
        lines = log_content.split('\n')
        blockquote = '\n'.join(f"> {line}" if line.strip() else ">" for line in lines)
        formatted_result = f"\n{blockquote}\n\n"
        _write_to_log(formatted_result)
    
    # Create tool message
    if isinstance(result, list):
        # Multimodal content - don't truncate
        tool_message = ToolMessage(content=result, tool_call_id=tool_call_id)
    else:
        # String content - may need truncation for tool message
        max_tool_content_chars = 20000
        if tool_name == 'read_file':
            truncated_result = result  # No truncation for read_file
        else:
            truncated_result = result if len(result) <= max_tool_content_chars else (
                result[:max_tool_content_chars] + "... [truncated]"
            )
        tool_message = ToolMessage(content=truncated_result, tool_call_id=tool_call_id)
    
    return result, tool_message
