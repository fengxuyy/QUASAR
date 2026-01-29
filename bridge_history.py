"""
Checkpoint history reconstruction utilities for bridge.py.

This module extracts and formats checkpoint history from saved state
for display in the CLI when resuming from a checkpoint.
"""

import os
import re
from collections import defaultdict
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage



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
    'grep_search': 'Searched files',
    'get_hardware_info': 'Checked Hardware',
}


def format_tool_display(tool_name: str, tool_args: dict) -> str:
    """Format a tool call into a display string like 'Listed pseudo' or 'Executed Python code'."""
    # Special handling for read_file with keyword
    if tool_name == 'read_file' and tool_args:
        keyword = tool_args.get('keyword')
        file_path = tool_args.get('file_path', 'file')
        file_name = os.path.basename(file_path) if file_path else 'file'
        
        if keyword:
            return f"Searched {keyword} in {file_name}"
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
    
    # Special handling for grep_search - show pattern
    if tool_name == 'grep_search' and tool_args:
        pattern = tool_args.get('pattern', '')
        directory_path = tool_args.get('directory_path', '.')
        if pattern:
            display_pattern = pattern[:50] + '...' if len(pattern) > 50 else pattern
            if directory_path and directory_path != '.':
                dir_name = os.path.basename(str(directory_path).rstrip('/'))
                return f"Searched files {display_pattern} in {dir_name}"
            return f"Searched files {display_pattern}"
    
    # Special handling for execute_code - show file name or truncated code
    if tool_name in ('execute_code', 'execute_python') and tool_args:
        is_trial = tool_args.get('is_trial_run', False)
        file_path = tool_args.get('file_path')
        code = tool_args.get('code')
        trial_suffix = ' [Trial]' if is_trial else ''
        
        if file_path:
            file_name = os.path.basename(file_path)
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
        target_str = str(target).rstrip('/')
        target_name = os.path.basename(target_str)
        if not target_name or target_str == '.':
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
    file_name = os.path.basename(file_path) if file_path else 'file'
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
            'grep_search': 'Search Files Failed',
        }
        return tool_error_names.get(tool_name, f"{tool_name} Failed")
    
    if tool_name == "list_directory":
        path = tool_args.get("directory_path", ".")
        pattern = tool_args.get("pattern", "*")
        path_display = os.path.basename(path.rstrip('/')) if path and path != '.' else 'workspace'
        
        if "no files found" in content_lower:
            if pattern and pattern != '*':
                return f"No files found matching {pattern} in {path_display}"
            return f"No files found in {path_display}"
        return f"{path_display} directory not found"
    
    elif tool_name == "read_file":
        file_path = tool_args.get("file_path", "file")
        file_name = os.path.basename(file_path) if file_path else "file"
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
        file_name = os.path.basename(file_path) if file_path else 'script'
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
            return f"Search timed out for {pattern}"
        elif "no matches found" in content_lower:
            return f"No matches for {pattern}"
        elif "not a directory" in content_lower or "does not exist" in content_lower:
            dir_name = os.path.basename(str(directory_path).rstrip('/')) if directory_path != '.' else 'directory'
            return f"{dir_name} not found"
        return f"Search failed for {pattern}"
    
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
        file_name = os.path.basename(file_path) if file_path else "file"
        
        match_re = re.search(r"at line\(s\) ([\d,\s]+)", content_str)
        if match_re:
            lines_str = match_re.group(1)
            match_count = len([l.strip() for l in lines_str.split(',') if l.strip()])
            return f"Searched {keyword} in {file_name} ({match_count} match{'es' if match_count != 1 else ''})"
        else:
            return f"Searched {keyword} in {file_name}"
    
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
        
        # Count matches by counting lines in the output (each match is typically one line)
        # The output format is: "file_path:line_number:content"
        match_lines = [line for line in content_str.split('\n') if line.strip() and not line.startswith('**Grep Search:**')]
        match_count = len(match_lines)
        
        # Check if results were truncated
        is_truncated = "truncated" in content_str.lower() or "showing first" in content_str.lower()
        
        if match_count > 0:
            match_word = "match" if match_count == 1 else "matches"
            truncated_text = " (truncated)" if is_truncated else ""
            if directory_path and directory_path != '.':
                dir_name = os.path.basename(str(directory_path).rstrip('/'))
                return f"Searched files {pattern} in {dir_name} ({match_count} {match_word}{truncated_text})"
            return f"Searched files {pattern} ({match_count} {match_word}{truncated_text})"
        else:
            if directory_path and directory_path != '.':
                dir_name = os.path.basename(str(directory_path).rstrip('/'))
                return f"Searched files {pattern} in {dir_name}"
            return f"Searched files {pattern}"
    
    return None  # Use default content


def extract_checkpoint_history(state_values: dict, messages: list, is_replan: bool = False) -> dict:
    """
    Extract structured history from checkpoint state for CLI display.
    
    Args:
        state_values: The checkpoint state values dict
        messages: List of messages from checkpoint
        is_replan: Whether this run is a replan
        
    Returns:
        Dictionary with plan, completed_steps, operator/evaluator/strategist items grouped by task
    """
    plan = state_values.get('plan', [])
    completed_steps = state_values.get('completed_steps', [])
    step_results = state_values.get('step_results', {})
    
    # Primacy: 1. state_values flag, 2. is_replan argument, 3. message-based heuristic
    replan_detected = state_values.get('is_replanning', is_replan)
    
    if not replan_detected:
        # Heuristic: search messages for the auto-improvement trigger
        AUTO_IMPROVE_SNIPPET = "Please analyze the previous run results and automatically improve the workflow"
        for msg in messages:
            content = _get_content(msg)
            if AUTO_IMPROVE_SNIPPET in content:
                replan_detected = True
                break
    
    is_replan = replan_detected
    
    # Extract plans from strategist's AIMessages
    all_plans = []
    for msg in messages:
        if isinstance(msg, AIMessage) and msg.content:
            content = _extract_text(msg.content).strip()
            # Heuristic to identify plan messages
            if 'Task' in content and ('Guidance' in content or 'Task 1' in content or '###' in content):
                all_plans.append(content)
    
    # In standard mode, we should have two plans (initial and reviewed)
    # in replanning mode, there might only be one.
    initial_plan_text = all_plans[0] if len(all_plans) > 1 else ""
    full_plan_text = all_plans[-1] if all_plans else ""
    
    # Track items by task
    operator_items_by_task = defaultdict(list)
    evaluator_items_by_task = defaultdict(list)
    strategist_items = []  # Strategist items (happens before any tasks)
    ordered_items_by_task = defaultdict(list)
    current_task_in_history = 0
    in_evaluator = False
    in_planning_phase = True  # Track if we're still in planning phase
    
    # Strategist tools (tools available to strategist during planning - normal mode only, no web search)
    # In replanning mode, strategist also has search_web and fetch_web_page
    STRATEGIST_TOOLS_NORMAL = {'read_file', 'list_directory', 'analyze_image', 'grep_search'}
    STRATEGIST_TOOLS_REPLANNING = {'read_file', 'list_directory', 'analyze_image', 'grep_search', 'search_web', 'fetch_web_page'}
    # Use the combined set for history reconstruction since we need to detect both modes
    STRATEGIST_TOOLS = STRATEGIST_TOOLS_NORMAL | STRATEGIST_TOOLS_REPLANNING
    
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
                # Extract retry info and summary from feedback message
                # Format: "EVALUATION_FEEDBACK:\nTask N requirements are NOT satisfied (attempt X/Y).\n{summary}\n..."
                import re
                retry_match = re.search(r'\(attempt (\d+)/(\d+)\)', content)
                if retry_match:
                    attempt_num = retry_match.group(1)
                    max_attempts = int(retry_match.group(2))
                    # max_attempts is total attempts (4), but display should show max retries (3)
                    max_retries = max_attempts - 1
                    # Extract summary - everything after the attempt line, before the "Please resolve" part
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
                    
                    # Add evaluation failed item - display as Retry x/3 to match live format
                    failed_item = {
                        "type": "evaluation-failed",
                        "content": f"Evaluation Failed - Retry {attempt_num}/{max_retries}",
                        "summary": summary,
                        "agent": "evaluator"
                    }
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
                
                # Add code snippet for write_file (only for operator)
                if tool_name == 'write_file' and 'content' in tool_args:
                    if agent_name == "operator":
                        item = _create_code_snippet_item(tool_args)
                        item["agent"] = agent_name
                        target_list.append(item)
                        ordered_items_by_task[current_task_in_history].append(item)
                
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
                    # Include code in output for inline execution (no file_path)
                    output_content = content_str
                    code = tool_args.get('code')
                    if code and not tool_args.get('file_path'):
                        output_content = f"**Code:**\n```python\n{code}\n```\n\n{content_str}"
                    code_result = {
                        "type": "code-result",
                        "content": {
                            "output": output_content,
                            "filePath": tool_args.get("file_path", "")
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

        # Handle text content from AIMessage (model thought/text)
        elif isinstance(msg, AIMessage) and msg.content:
            content = _extract_text(msg.content).strip()
            
            # Skip if it is a plan text (already shown in dedicated headers)
            if content == full_plan_text or content == initial_plan_text:
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
