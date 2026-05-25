"""
Operator agent node implementation.
"""

import os
import re
import time
from pathlib import Path
from langchain_core.messages import AIMessage, SystemMessage, HumanMessage, ToolMessage
from ..debug_logger import log_operator_start, log_exception, log_custom
from ..pending_execution import save_pending_execution, load_pending_execution, clear_pending_execution
from ..usage_tracker import was_hardware_changed_on_resume, get_previous_hardware_signature
from ..resume_steering import RESUME_STEERING_MARKER
from .utils import update_operator_status, TOOL_STATUS_MESSAGES

from ..state import State
from ..tools.rag_tools import query_rag
from ..tools import (
    read_file,
    edit_file,
    list_directory,
    analyze_image,
    execute_python,
    resume_execution,
    interrupt_running_execution,
    has_running_process,
    continue_execution,
    interrupt_execution,
    execute_temporary_python,
    search_web,
    fetch_web_page,
    complete_task,
    is_rag_enabled,
    grep_search,
    get_hardware_info,
)
from ..tools.execution import _parse_check_in_after_seconds
from .utils import (
    _write_input_messages,
    _extract_text,
    execute_with_timeout,
    StreamingTimeoutError,
    _write_to_log,
    log_agent_header,
    log_tool_call,
    get_project_context,
    write_execution_log,
    is_api_connection_error,
    handle_api_retry,
    MAX_LOG_CHARS,
    truncate_content,
    send_agent_event,
    send_json,
    send_text_stream,
    send_thought_stream,
    APIConnectionError,
    extract_tool_call_info,
    extract_target_name,
    get_execute_python_status,
    extract_project_request,
    format_plan,
    format_history,
    execute_tool_with_logging,
    ValidationError,
    format_validation_error,
    detect_repeated_tool_calls,
    MAX_REPEATED_TOOL_CALLS,
    stream_with_token_tracking,
    format_tool_status,
)
from ..tools.base import get_all_files
from ..context_summarizer import maybe_summarize_messages
from ..prompting import (
    build_checkin_control_reminder_injection,
    build_checkin_empty_response_injection,
    build_checkin_history_message as build_prompt_checkin_history_message,
    build_checkin_prompt_injection,
    build_hardware_change_injection,
    build_operator_messages,
    build_operator_repeated_tool_warning_injection,
    build_resume_steering_injection,
    build_summarized_checkin_reminder_injection,
    merge_prompt_events_from_messages,
    prompt_identity_from_state,
    prompt_metadata_update,
    upsert_prompt_runtime_event,
)
from ..prompting.builders import build_interrupted_execution_recovery_content
from ..prompting.debug import log_prompt_assembly, log_prompt_injection

# Tool execution mapping
TOOL_MAP = {
    'query_rag': query_rag,
    'read_file': read_file,
    'edit_file': edit_file,
    'list_directory': list_directory,
    'analyze_image': analyze_image,
    'search_web': search_web,
    'fetch_web_page': fetch_web_page,
    'execute_python': execute_python,
    'complete_task': complete_task,
    'grep_search': grep_search,
    'get_hardware_info': get_hardware_info,
}

OTHER_TOOL_TIMEOUT = 600
LLM_RESPONSE_TIMEOUT = 600
MAX_RETRIES = 2


def _send_checkin_tool_status(
    tool_name: str,
    tool_args: dict,
    *,
    is_complete: bool = False,
    tool_result: str | None = None,
    elapsed_display: str | None = None,
) -> None:
    """Emit transient operator check-in tool events using shared status formatting."""
    status_text, is_error = format_tool_status(
        tool_name,
        tool_args,
        is_complete=is_complete,
        tool_result=tool_result,
    )

    if is_complete:
        send_agent_event("operator", "step_complete", status_text, is_error=is_error)
        if elapsed_display:
            send_agent_event("operator", "update", f"Awaiting decision after {elapsed_display}")
    else:
        send_agent_event("operator", "update", status_text, is_error=is_error)


def _extract_checkin_summary_text(
    provided_summary: str,
    decision_response,
    checkin_messages: list,
    *,
    default_summary: str,
) -> str:
    """Return a compact human-readable summary for a completed check-in."""
    summary = (provided_summary or "").strip()
    if summary:
        return truncate_content(summary, 2000, "\n... [summary truncated]\n").strip()

    decision_text = _extract_text(getattr(decision_response, "content", ""))
    if decision_text.strip():
        return truncate_content(decision_text.strip(), 2000, "\n... [summary truncated]\n").strip()

    recent_findings = []
    for msg in reversed(checkin_messages):
        if not isinstance(msg, ToolMessage):
            continue
        content = getattr(msg, "content", "")
        if not isinstance(content, str) or not content.strip():
            continue
        recent_findings.append(content.strip())
        if len(recent_findings) >= 3:
            break

    if recent_findings:
        joined = "\n\n".join(reversed(recent_findings))
        return truncate_content(joined, 2000, "\n... [summary truncated]\n").strip()

    return default_summary


def _build_checkin_history_message(
    script_name: str,
    elapsed_display: str,
    *,
    decision: str,
    summary: str,
    reason: str = "",
    next_check_in_after: float | str | None = None,
) -> HumanMessage:
    """Build the single compact operator-history message for a completed check-in."""
    return build_prompt_checkin_history_message(
        script_name,
        elapsed_display,
        decision=decision,
        summary=summary,
        reason=reason,
        next_check_in_after=next_check_in_after,
    )


def operator_node(state: State, llm_with_tools, all_tools) -> State:
    """Operator agent that executes individual steps from the plan."""
    log_operator_start(state)

    plan = state.get('plan', [])
    completed_steps = state.get('completed_steps', [])
    step_results = state.get('step_results', {})
    current_task_messages = state.get('current_task_messages', [])
    current_task_index = len(completed_steps)
    resume_steering = (state.get('resume_steering') or '').strip()
    resume_steering_applied = False
    prompt_metadata = {}
    prompt_runtime_events = merge_prompt_events_from_messages(
        state.get("prompt_runtime_events", []),
        current_task_messages,
        task_index=current_task_index,
    )
    prompt_runtime_events_changed = prompt_runtime_events != list(state.get("prompt_runtime_events", []) or [])

    def record_runtime_event(injection):
        nonlocal prompt_runtime_events, prompt_runtime_events_changed
        updated_events = upsert_prompt_runtime_event(
            prompt_runtime_events,
            injection,
            task_index=current_task_index,
        )
        if updated_events != prompt_runtime_events:
            prompt_runtime_events_changed = True
            prompt_runtime_events = updated_events
        return injection.to_human_message()

    def finalize_update(update: dict) -> dict:
        if resume_steering_applied:
            update["resume_steering"] = ""
        if prompt_metadata:
            update.update(prompt_metadata)
        if prompt_runtime_events_changed:
            update["prompt_runtime_events"] = prompt_runtime_events
        return update
    
    if current_task_index >= len(plan):
        send_json("task_progress", {"current": len(plan), "total": len(plan)})
        update = {"messages": [AIMessage(content="DONE")]}
        if resume_steering:
            update["resume_steering"] = ""
        return update

    if plan:
        current_task = plan[current_task_index]
        # Extract clean task title for progress event
        task_title = current_task.split('\n')[0].strip()
        # Remove markdown headers
        while task_title.startswith('#'):
            task_title = task_title.lstrip('#').strip()
        # Remove all ** pairs (markdown bold)
        task_title = task_title.replace('**', '')
        # Remove single * at start/end
        task_title = task_title.strip().lstrip('*').rstrip('*').strip()
        # Remove Task N: prefix
        task_title = re.sub(r'^Task\s+\d+[:：]\s*', '', task_title, flags=re.IGNORECASE).strip()
        send_json("task_progress", {"current": current_task_index + 1, "total": len(plan), "title": task_title})
    
    send_agent_event("operator", "start", "Analysing Task")
    current_task = plan[current_task_index]
    
    if not current_task_messages:
        task_desc = current_task.split('\n')[0].strip()
        
        # Remove markdown prefixes
        while task_desc.startswith('#'):
            task_desc = task_desc.lstrip('#').strip()
        # Remove all ** pairs (markdown bold)
        task_desc = task_desc.replace('**', '')
        # Remove single * at start/end
        task_desc = task_desc.strip().lstrip('*').rstrip('*').strip()
        # Remove Task N: prefix
        task_desc = re.sub(r'^Task\s+\d+[:：]\s*', '', task_desc, flags=re.IGNORECASE).strip()
        
        log_agent_header("Operator", current_task_index, f"Executing: **{task_desc}**")
    
    formatted_plan = format_plan(plan)
    formatted_history = format_history(step_results, completed_steps)
    messages = state.get('messages', [])
    project_request = state.get('user_input', '') or extract_project_request(messages)
    write_execution_log(project_request, formatted_plan, formatted_history)
    
    initial_files = None
    if not current_task_messages:
        initial_files = list(get_all_files())
        
        is_last_step = current_task_index == len(plan) - 1
        pmg_mapi_available = "; `Materials Project API` (env: PMG_MAPI_KEY); " if os.getenv("PMG_MAPI_KEY") else "."
        rag_enabled = is_rag_enabled()

        # Read accuracy mode from environment (same source as strategist)
        _accuracy_raw = os.getenv("ACCURACY", "").lower()
        _valid_accuracy_modes = {"eco", "standard", "pro", "adaptive"}
        accuracy_mode = _accuracy_raw if _accuracy_raw in _valid_accuracy_modes else "standard"
        prompt_profile, prompt_version = prompt_identity_from_state(state)
        prompt_assembly = build_operator_messages(
            project_request=project_request,
            formatted_history=formatted_history,
            current_task=current_task,
            is_last_step=is_last_step,
            pmg_mapi_available=pmg_mapi_available,
            rag_enabled=rag_enabled,
            accuracy_mode=accuracy_mode,
            profile=prompt_profile,
            version=prompt_version,
        )
        log_prompt_assembly(prompt_assembly, task_index=current_task_index, context="initial_task")
        current_task_messages = prompt_assembly.messages
        prompt_metadata = prompt_metadata_update(state, prompt_assembly)
    else:
        # Check for pending execution from SIGKILL scenario (file-based recovery)
        pending_exec = load_pending_execution()
        if pending_exec and pending_exec.get('task_index') == current_task_index:
            # Found a pending execution that was interrupted by SIGKILL
            # Inject AIMessage + synthetic ToolMessage to inform the LLM
            tool_call = pending_exec['tool_call']
            ai_msg = AIMessage(
                content=pending_exec.get('ai_message_content', ''),
                tool_calls=[tool_call]
            )
            tool_msg = ToolMessage(
                content=build_interrupted_execution_recovery_content(),
                tool_call_id=tool_call['id']
            )
            
            # Check if already added to avoid duplicates
            last_ai_msg = None
            for msg in reversed(current_task_messages):
                if isinstance(msg, AIMessage):
                    last_ai_msg = msg
                    break
            
            # Only add if the AI message isn't already there
            if not last_ai_msg or getattr(last_ai_msg, 'tool_calls', None) != [tool_call]:
                current_task_messages.append(ai_msg)
                current_task_messages.append(tool_msg)
                log_custom("OPERATOR", "Injected interrupted execution messages", {"tool_call_id": tool_call['id']})
            
            # Clear the pending execution file
            clear_pending_execution()
        
        # Notify the LLM if hardware changed since the interrupted run
        if was_hardware_changed_on_resume():
            prev_hw = get_previous_hardware_signature()
            from .utils.system import get_hardware_info as _get_hw_str
            current_hw_str = _get_hw_str()
            hw_injection = build_hardware_change_injection(prev_hw, current_hw_str)
            hw_change_notice = hw_injection.content
            already_has_hw_notice = any(
                isinstance(m, HumanMessage) and "Hardware configuration has changed" in getattr(m, "content", "")
                for m in current_task_messages
            )
            if not already_has_hw_notice:
                log_prompt_injection(hw_injection, task_index=current_task_index, context="hardware_change")
                current_task_messages.append(record_runtime_event(hw_injection))
                log_custom("OPERATOR", "Injected hardware change notice", {
                    "prev_cpu_cores": prev_hw.get('cpu_cores') if prev_hw else None,
                    "prev_gpu": prev_hw.get('gpu_info') if prev_hw else None,
                })
        
        # Check for repeated identical tool calls (infinite loop detection)
        repeated_tool = detect_repeated_tool_calls(current_task_messages)
        if repeated_tool:
            tool_name, count = repeated_tool
            warning_injection = build_operator_repeated_tool_warning_injection(tool_name, count)
            loop_warning = warning_injection.content
            already_has_loop_warning = any(
                isinstance(m, HumanMessage) and getattr(m, "content", "") == loop_warning
                for m in current_task_messages
            )
            if not already_has_loop_warning:
                _write_to_log(f"\n**[SYSTEM]** Detected {count} repeated calls to `{tool_name}`. Injecting warning.\n")
                log_prompt_injection(warning_injection, task_index=current_task_index, context="repeated_tool")
                current_task_messages.append(warning_injection.to_human_message())

    if resume_steering:
        already_has_steering = any(
            isinstance(m, HumanMessage)
            and RESUME_STEERING_MARKER in getattr(m, "content", "")
            and resume_steering in getattr(m, "content", "")
            for m in current_task_messages
        )
        resume_steering_applied = True
        if not already_has_steering:
            steering_injection = build_resume_steering_injection(resume_steering)
            log_prompt_injection(steering_injection, task_index=current_task_index, context="resume_steering")
            current_task_messages = current_task_messages + [
                record_runtime_event(steering_injection)
            ]
            send_agent_event(
                "operator",
                "step_complete",
                "User Steering Received",
                output=resume_steering,
            )
            log_custom("OPERATOR", "Injected resume steering message", {
                "length": len(resume_steering),
            })
    
    _update_operator_status = update_operator_status
    
    # Write the exact messages being sent to the LLM before the call
    _write_input_messages(current_task_messages, "OPERATOR", current_task_index)

    validation_tool_context = {}
    
    try:
        response = None
        full_content = ""
        tool_calls = []
        completion_request = None
        seen_tool_calls = set()
        
        def on_tool_call_detected(tool_name: str, tool_args: dict):
            """Called immediately when a tool call is first detected in the stream."""
            file_path = tool_args.get('file_path', '') if isinstance(tool_args, dict) else ''
            tool_call_key = (tool_name, str(file_path))
            
            if tool_call_key not in seen_tool_calls:
                seen_tool_calls.add(tool_call_key)
                _update_operator_status(tool_name, tool_args, is_complete=False)
        
        retry_count = 0
        api_error_count = 0
        
        while retry_count <= MAX_RETRIES:
            try:
                if retry_count > 0:
                    retry_msg = f"Retrying ({retry_count}/{MAX_RETRIES})"
                    send_agent_event("operator", "update", retry_msg)

                saw_tool_calls = False
                full_content = ""
                tool_calls = []
                
                start_time = time.time()
                
                try:
                    # Use shared streaming helper with timeout wrapper
                    accumulated_text = ""
                    accumulated_thoughts = ""
                    
                    def on_content(text):
                        nonlocal accumulated_text
                        accumulated_text += text
                        # Check timeout during streaming
                        if time.time() - start_time > LLM_RESPONSE_TIMEOUT:
                            raise StreamingTimeoutError(f"LLM response generation timed out (exceeded {LLM_RESPONSE_TIMEOUT // 60} minutes)")
                        # Stream delta to UI — frontend accumulates progressively
                        send_text_stream("operator", text, is_complete=False)
                    
                    def on_thought(text):
                        nonlocal accumulated_thoughts
                        accumulated_thoughts += text
                        send_thought_stream("operator", accumulated_thoughts, is_complete=False)
                    
                    full_content, tool_calls, response, was_stopped_early = stream_with_token_tracking(
                        llm_with_tools, current_task_messages, on_content=on_content, on_thought=on_thought,
                        detect_repetition=True,  # Auto-stop on repetitive output
                        agent_name='operator'
                    )
                    
                    if was_stopped_early:
                        log_custom("OPERATOR", "Generation stopped early due to repetition detection")
                    
                    # Update UI with detected tool calls after streaming completes
                    for tc in tool_calls:
                        tool_name = tc.get('name', '')
                        tool_args = tc.get('args', {})
                        if tool_name:
                            on_tool_call_detected(tool_name, tool_args if isinstance(tool_args, dict) else {})
                    
                    if accumulated_thoughts:
                        send_thought_stream("operator", accumulated_thoughts, is_complete=True)
                    
                    if tool_calls:
                        saw_tool_calls = True
                    
                    
                    # Create AIMessage if response is None
                    if not response:
                        response = AIMessage(content=full_content)
                    elif full_content and getattr(response, 'content', '') != full_content:
                        response.content = full_content
                    elif not isinstance(getattr(response, 'content', ''), str):
                        response.content = str(full_content) if full_content else ""
                        
                    if tool_calls and (not hasattr(response, 'tool_calls') or not response.tool_calls):
                        response.tool_calls = tool_calls
                    
                    break
                    
                except StreamingTimeoutError as e:
                    retry_count += 1
                    timeout_msg = f"\n[OPERATOR] LLM response generation timed out: {str(e)}\n"
                    _write_to_log(timeout_msg)

                    
                    if retry_count > MAX_RETRIES:
                        raise
                
                except ValueError as e:
                    # Handle empty response errors from LangChain
                    error_msg_str = str(e)
                    if "empty" in error_msg_str.lower() or "must contain" in error_msg_str.lower():
                        retry_count += 1
                        _write_to_log(f"\n[OPERATOR] Empty response from LLM: {error_msg_str}. Retrying ({retry_count}/{MAX_RETRIES})...\n")
                        send_agent_event("operator", "update", "Empty response, retrying")
                        if retry_count > MAX_RETRIES:
                            # Return error to prompt retry
                            _write_to_log("\n[OPERATOR] Max retries exceeded for empty response.\n")
                            error_msg = "Error: Received empty response from LLM after retries. Please retry your last step."
                            update = {
                                'messages': [HumanMessage(content=error_msg)],
                                'current_task_messages': current_task_messages + [HumanMessage(content=error_msg)]
                            }
                            if initial_files is not None:
                                update["files_at_task_start"] = initial_files
                            return finalize_update(update)
                        continue  # Retry the while loop
                    else:
                        raise
                    
                except APIConnectionError as e:
                    api_error_count += 1
                    if handle_api_retry("operator", e, api_error_count, max_retries=3):
                        continue
                    # handle_api_retry already sent error to UI
                    error_message = f"API Error executing step: {str(e)}"
                    error_msg = AIMessage(content=error_message)
                    update = {
                        'messages': [error_msg],
                        'current_task_messages': current_task_messages + [error_msg]
                    }
                    if initial_files is not None:
                        update["files_at_task_start"] = initial_files
                    return finalize_update(update)
                    
                except Exception as e:
                    _write_to_log(f"\n---\n\n**[OPERATOR] Error during LangChain streaming:**\n\n> {str(e)}\n\n")
                    raise
            except Exception as e:
                if is_api_connection_error(e):
                    api_error_count += 1
                    if handle_api_retry("operator", e, api_error_count, max_retries=3):
                        continue
                    # handle_api_retry already sent error to UI
                    error_message = f"API Error executing step: {str(e)}"
                    error_msg = AIMessage(content=error_message)
                    update = {
                        'messages': [error_msg],
                        'current_task_messages': current_task_messages + [error_msg]
                    }
                    if initial_files is not None:
                        update["files_at_task_start"] = initial_files
                    return finalize_update(update)
                raise
        
        if response is None or (not full_content.strip() and not tool_calls):
            _write_to_log("\n---\n\n**[OPERATOR] Warning:**\n\n> Received empty response from LLM. Prompting to retry...\n\n")
            error_msg = "Error: You sent an empty response. Please retry your last step or provide a status update."
            
            # Update messages with warning and log it to input_messages.md
            updated_messages = current_task_messages + [HumanMessage(content=error_msg)]
            _write_input_messages(updated_messages, "OPERATOR", current_task_index)
            
            update = {
                'messages': [HumanMessage(content=error_msg)],
                'current_task_messages': updated_messages
            }
            if initial_files is not None:
                update["files_at_task_start"] = initial_files
            return finalize_update(update)
        
        tool_messages = []
        called_tools = set()
        
        # Send text stream completion signal if there was content
        if full_content.strip():
            send_text_stream("operator", full_content, is_complete=True)
        
        # Add response to current_task_messages immediately (before tool execution)
        # This ensures the AIMessage is persisted to checkpoint if interrupted during tool execution
        if response:
            current_task_messages = current_task_messages + [response]
            _write_input_messages(current_task_messages, "OPERATOR", current_task_index)
        
        if tool_calls:
            for tc in tool_calls:
                tool_name, tool_args, _ = extract_tool_call_info(tc)
                called_tools.add(tool_name)
                if tool_name == 'complete_task':
                    completion_request = True
            
            def on_operator_status_update(tool_name: str, tool_args: dict, is_complete: bool):
                """Update operator status - preserves special handling for various tools."""
                if not is_complete:
                    _update_operator_status(tool_name, tool_args, is_complete=False, tool_result=None)
                else:
                    # Skip these tools here - we handle them specially after execution to pass tool_result for error detection
                    skip_step_complete = tool_name in ('complete_task', 'read_file', 'query_rag', 'list_directory', 'search_web', 'fetch_web_page', 'grep_search', 'get_hardware_info')
                    if not skip_step_complete:
                        _update_operator_status(tool_name, tool_args, is_complete=True, tool_result=None)

            
            for tool_call in tool_calls:
                tool_name, tool_args, tool_call_id = extract_tool_call_info(tool_call)
                tool = TOOL_MAP.get(tool_name)
                
                if tool_name == 'execute_python' and tool:
                    target_name = extract_target_name(tool_name, tool_args) if tool_args else None

                    def get_resumed_execution_status(next_interval):
                        resumed_tool_args = dict(tool_args) if isinstance(tool_args, dict) else {}
                        if next_interval is None:
                            resumed_tool_args.pop("check_in_after", None)
                        else:
                            resumed_tool_args["check_in_after"] = next_interval
                        return get_execute_python_status(resumed_tool_args) if resumed_tool_args else "Executing"
                    
                    # Save pending execution state in case of SIGKILL
                    save_pending_execution(
                        ai_message_content=getattr(response, 'content', ''),
                        tool_call={
                            "id": tool_call_id,
                            "name": tool_name,
                            "args": tool_args
                        },
                        task_index=current_task_index
                    )
                    
                    log_tool_call(tool_name, target_name, status="started", agent="operator")

                    validation_tool_context = {
                        "tool_name": tool_name,
                        "tool_call_id": tool_call_id,
                    }
                    result = tool.invoke(tool_args)
                    validation_tool_context = {}
                    initial_check_in_after = (
                        tool_args.get('check_in_after')
                        if isinstance(tool_args, dict)
                        else None
                    )
                    
                    # Handle check-in flow if result is a dict with check_in_required status
                    while isinstance(result, dict) and result.get('status') == 'check_in_required':
                        elapsed_display = result.get('elapsed_display', 'unknown time')
                        file_path_display = result.get('file_path', 'script')
                        
                        # Update status to show waiting for decision
                        send_agent_event("operator", "update", f"Awaiting decision after {elapsed_display}")
                        
                        # Log the check-in
                        checkin_msg = f"\n[OPERATOR] Python script has been running for {elapsed_display}. Prompting for continue/interrupt decision.\n"
                        _write_to_log(checkin_msg)
                        
                        script_name = os.path.basename(file_path_display)
                        checkin_injection = build_checkin_prompt_injection(
                            script_name=script_name,
                            elapsed_display=elapsed_display,
                        )
                        log_prompt_injection(checkin_injection, task_index=current_task_index, context="execution_checkin")
                        
                        # Create tool set for check-in decision (includes inspection helpers)
                        checkin_tools = [
                            continue_execution,
                            interrupt_execution,
                            read_file,
                            list_directory,
                            grep_search,
                            execute_temporary_python,
                        ]
                        checkin_llm = llm_with_tools.bind_tools(checkin_tools)
                        
                        # Tool map for check-in inspection tools
                        checkin_tool_map = {
                            'read_file': read_file,
                            'list_directory': list_directory,
                            'grep_search': grep_search,
                            'execute_temporary_python': execute_temporary_python,
                        }
                        
                        # Build check-in messages (add to current context)
                        checkin_human_msg = checkin_injection.to_human_message()
                        checkin_messages = current_task_messages + [checkin_human_msg]
                        
                        decision_response = None
                        try:
                            # Loop until LLM makes a continue/interrupt decision
                            # LLM may call filesystem tools first to inspect output files
                            decision_made = False
                            should_continue = True  # Default to continue
                            interrupt_reason = ""
                            decision_summary = ""
                            next_check_in_after = None
                            max_checkin_iterations = 25  # Prevent infinite loops
                            checkin_iteration = 0
                            
                            while not decision_made and checkin_iteration < max_checkin_iterations:
                                checkin_iteration += 1

                                checkin_messages, did_summarize_checkin, effective_model, trigger_input = maybe_summarize_messages(
                                    checkin_messages,
                                    checkin_llm,
                                    agent_name='operator',
                                )
                                if did_summarize_checkin:
                                    log_custom(
                                        "OPERATOR",
                                        f"Check-in context summarized for {effective_model}: {trigger_input:,} input tokens",
                                    )
                                    send_agent_event("operator", "update", "Summarizing check-in context (token limit approaching)")
                                    reminder_injection = build_summarized_checkin_reminder_injection()
                                    log_prompt_injection(reminder_injection, task_index=current_task_index, context="checkin_summary")
                                    checkin_messages = checkin_messages + [reminder_injection.to_human_message()]
                                
                                # Get LLM decision with timeout (default to continue if timeout)
                                start_decision_time = time.time()
                                decision_timeout = 120  # 2 minutes per iteration
                                
                                decision_tool_calls = []
                                
                                # Stream the decision
                                def on_checkin_content(text):
                                    if time.time() - start_decision_time > decision_timeout:
                                        raise StreamingTimeoutError("Decision timeout")
                                
                                _, decision_tool_calls, decision_response, _ = stream_with_token_tracking(
                                    checkin_llm, checkin_messages, on_content=on_checkin_content,
                                    detect_repetition=False,
                                    agent_name='operator'
                                )
                                
                                # Handle empty response by prompting again; continuation requires a next check-in.
                                if not decision_tool_calls and (not decision_response or not getattr(decision_response, 'content', '').strip()):
                                    _write_to_log("\n[OPERATOR] Empty LLM response during check-in, prompting again for a decision.\n")
                                    empty_response_injection = build_checkin_empty_response_injection()
                                    log_prompt_injection(empty_response_injection, task_index=current_task_index, context="checkin_empty_response")
                                    checkin_messages = checkin_messages + [empty_response_injection.to_human_message()]
                                    continue
                                
                                # Add decision response to messages
                                if decision_response:
                                    checkin_messages = checkin_messages + [decision_response]
                                
                                # Process tool calls
                                if decision_tool_calls:
                                    checkin_tool_messages = []
                                    
                                    for dtc in decision_tool_calls:
                                        dtc_name = dtc.get('name', '') if isinstance(dtc, dict) else getattr(dtc, 'name', '')
                                        dtc_args = dtc.get('args', {}) if isinstance(dtc, dict) else getattr(dtc, 'args', {})
                                        dtc_id = dtc.get('id', '') if isinstance(dtc, dict) else getattr(dtc, 'id', '')
                                        
                                        if dtc_name == 'continue_execution':
                                            requested_next_check = (
                                                dtc_args.get('next_check_in_after')
                                                if isinstance(dtc_args, dict)
                                                else None
                                            )
                                            if requested_next_check is None:
                                                interval_error = (
                                                    "Error: 'next_check_in_after' is required and must be "
                                                    "an agent-selected positive number of minutes."
                                                )
                                            else:
                                                _, interval_error = _parse_check_in_after_seconds(
                                                    requested_next_check,
                                                    field_name="next_check_in_after",
                                                )
                                            if interval_error:
                                                checkin_tool_messages.append(ToolMessage(
                                                    content=interval_error,
                                                    tool_call_id=dtc_id
                                                ))
                                                _write_to_log(f"\n[OPERATOR] Check-in continue_execution error: {interval_error}\n")
                                                send_agent_event("operator", "update", f"Invalid check-in schedule, awaiting decision after {elapsed_display}")
                                                continue

                                            decision_made = True
                                            should_continue = True
                                            decision_summary = dtc_args.get('summary', '') if isinstance(dtc_args, dict) else ''
                                            next_check_in_after = requested_next_check
                                            _write_to_log("\n[OPERATOR] LLM decided to continue execution.\n")
                                            # Add tool message for continue_execution
                                            continue_content = f"CONTINUE_EXECUTION\nSUMMARY: {decision_summary or 'No summary provided.'}"
                                            if next_check_in_after is not None:
                                                continue_content += f"\nNEXT_CHECK_IN_AFTER_MINUTES: {float(next_check_in_after):g}"
                                            checkin_tool_messages.append(ToolMessage(
                                                content=continue_content,
                                                tool_call_id=dtc_id
                                            ))
                                            break
                                        elif dtc_name == 'interrupt_execution':
                                            decision_made = True
                                            should_continue = False
                                            interrupt_reason = dtc_args.get('reason', 'No reason provided') if isinstance(dtc_args, dict) else 'No reason provided'
                                            decision_summary = ""
                                            _write_to_log(f"\n[OPERATOR] LLM decided to interrupt execution. Reason: {interrupt_reason}\n")
                                            send_agent_event(
                                                "operator",
                                                "step_complete",
                                                "Interrupted Execution",
                                                is_error=True,
                                                output=interrupt_reason,
                                            )
                                            send_agent_event("operator", "update", "Interrupting execution")
                                            # Add tool message for interrupt_execution
                                            checkin_tool_messages.append(ToolMessage(
                                                content=f"INTERRUPT_EXECUTION: {interrupt_reason}",
                                                tool_call_id=dtc_id
                                            ))
                                            break
                                        elif dtc_name in checkin_tool_map:
                                            # Execute filesystem tool
                                            _write_to_log(f"\n[OPERATOR] Check-in: Executing {dtc_name}...\n")
                                            checkin_args = dtc_args if isinstance(dtc_args, dict) else {}
                                            _send_checkin_tool_status(dtc_name, checkin_args, is_complete=False)
                                            
                                            try:
                                                tool_func = checkin_tool_map[dtc_name]
                                                tool_result = execute_with_timeout(
                                                    tool_func.invoke, 
                                                    180,  # 3 minute timeout for check-in inspection tools
                                                    checkin_args
                                                )
                                                checkin_tool_messages.append(ToolMessage(
                                                    content=str(tool_result)[:10000],  # Limit result size
                                                    tool_call_id=dtc_id
                                                ))
                                                _write_to_log(f"\n[OPERATOR] Check-in {dtc_name} result:\n{str(tool_result)[:2000]}\n")
                                                _send_checkin_tool_status(
                                                    dtc_name,
                                                    checkin_args,
                                                    is_complete=True,
                                                    tool_result=str(tool_result),
                                                    elapsed_display=elapsed_display,
                                                )
                                            except Exception as tool_err:
                                                error_result = f"Error executing {dtc_name}: {str(tool_err)}"
                                                checkin_tool_messages.append(ToolMessage(
                                                    content=error_result,
                                                    tool_call_id=dtc_id
                                                ))
                                                _write_to_log(f"\n[OPERATOR] Check-in {dtc_name} error: {str(tool_err)}\n")
                                                send_agent_event("operator", "update", f"Check-in tool error, awaiting decision after {elapsed_display}")
                                    
                                    # Add tool messages to conversation
                                    if checkin_tool_messages:
                                        checkin_messages = checkin_messages + checkin_tool_messages
                                else:
                                    # No tool calls - LLM responded with text only, prompt again
                                    _write_to_log("\n[OPERATOR] Check-in: LLM responded without tool call, prompting for decision...\n")
                                    control_injection = build_checkin_control_reminder_injection()
                                    log_prompt_injection(control_injection, task_index=current_task_index, context="checkin_control")
                                    checkin_messages = checkin_messages + [control_injection.to_human_message()]
                            
                            # Check if we hit max iterations without decision
                            if not decision_made:
                                _write_to_log(
                                    f"\n[OPERATOR] Check-in max iterations ({max_checkin_iterations}) reached; "
                                    "continuing with the previous agent-selected check-in interval.\n"
                                )
                                should_continue = True
                                decision_summary = (
                                    f"Defaulted to continue after {max_checkin_iterations} check-in iterations "
                                    f"while assessing the current execution state."
                                )
                                next_check_in_after = initial_check_in_after
                            
                            history_message = _build_checkin_history_message(
                                script_name,
                                elapsed_display,
                                decision="continue_execution" if should_continue else "interrupt_execution",
                                reason=interrupt_reason,
                                summary=_extract_checkin_summary_text(
                                    decision_summary,
                                    decision_response,
                                    checkin_messages,
                                    default_summary=(
                                        "Execution appears healthy and should continue."
                                        if should_continue else
                                        "Execution should be interrupted based on the inspected outputs."
                                    ),
                                ),
                                next_check_in_after=next_check_in_after if should_continue else None,
                            )
                            current_task_messages = current_task_messages + [history_message]
                            _write_input_messages(current_task_messages, "OPERATOR", current_task_index)

                            if should_continue:
                                send_agent_event("operator", "update", "Continuing execution")
                                send_agent_event("operator", "update", get_resumed_execution_status(next_check_in_after))
                                result = resume_execution(check_in_after=next_check_in_after)
                            else:
                                result = interrupt_running_execution(interrupt_reason)
                                
                        except (StreamingTimeoutError, ValueError) as e:
                            # Keep monitoring on check-in errors using the previous agent-selected interval.
                            error_msg = str(e)
                            _write_to_log(
                                f"\n[OPERATOR] Check-in decision error: {error_msg}. "
                                "Continuing with the previous agent-selected check-in interval.\n"
                            )
                            
                            current_task_messages = current_task_messages + [_build_checkin_history_message(
                                script_name,
                                elapsed_display,
                                decision="continue_execution",
                                summary=_extract_checkin_summary_text(
                                    "",
                                    decision_response,
                                    checkin_messages,
                                    default_summary=f"Defaulted to continue after check-in error: {error_msg}",
                                ),
                                reason=f"Decision error: {error_msg}",
                                next_check_in_after=initial_check_in_after,
                            )]
                            _write_input_messages(current_task_messages, "OPERATOR", current_task_index)

                            send_agent_event("operator", "update", f"Check-in error ({error_msg[:50]}), continuing execution")
                            send_agent_event("operator", "update", get_resumed_execution_status(initial_check_in_after))
                            result = resume_execution(check_in_after=initial_check_in_after)
                        except Exception as e:
                            # Catch-all for any other exceptions; keep monitoring with the previous agent-selected interval.
                            error_msg = str(e)
                            _write_to_log(
                                f"\n[OPERATOR] Unexpected check-in error: {error_msg}. "
                                "Continuing with the previous agent-selected check-in interval.\n"
                            )
                            
                            current_task_messages = current_task_messages + [_build_checkin_history_message(
                                script_name,
                                elapsed_display,
                                decision="continue_execution",
                                summary=_extract_checkin_summary_text(
                                    "",
                                    decision_response,
                                    checkin_messages,
                                    default_summary=f"Defaulted to continue after unexpected check-in error: {error_msg}",
                                ),
                                reason=f"Unexpected decision error: {error_msg}",
                                next_check_in_after=initial_check_in_after,
                            )]
                            _write_input_messages(current_task_messages, "OPERATOR", current_task_index)

                            send_agent_event("operator", "update", f"Unexpected error, continuing execution")
                            send_agent_event("operator", "update", get_resumed_execution_status(initial_check_in_after))
                            result = resume_execution(check_in_after=initial_check_in_after)
                    
                    # Clear pending execution after completion
                    clear_pending_execution()
                    
                    log_tool_call(tool_name, target_name, status="completed", agent="operator")
                    
                    if result and isinstance(result, str):
                        log_content = result
                        truncated_log = truncate_content(
                            log_content, 
                            MAX_LOG_CHARS, 
                            "\n\n*... [Output truncated for log brevity]*"
                        )
                        lines = truncated_log.split('\n')
                        blockquote = '\n'.join(f"> {line}" if line.strip() else ">" for line in lines)
                        _write_to_log(f"\n{blockquote}\n\n")
                    
                    _update_operator_status(tool_name, tool_args, is_complete=True, tool_result=result)
                    
                    if result and isinstance(result, str):
                        is_error = False
                        result_lower = result.lower()
                        exit_code_match = re.search(r'exit code:\s*(-?\d+)', result_lower)
                        if exit_code_match:
                            is_error = int(exit_code_match.group(1)) != 0
                        elif 'error executing code' in result_lower:
                            is_error = True
                        elif result.startswith("Error:") or result.startswith("**Execution Error:**"):
                            is_error = True
                        if 'was interrupted' in result_lower:
                            is_error = False
                        send_json("code_result", {
                            "output": result,
                            "success": not is_error,
                            "file_path": tool_args.get('file_path', '') if isinstance(tool_args, dict) else ''
                        })
                    
                    if isinstance(result, list):
                        tool_messages.append(ToolMessage(content=result, tool_call_id=tool_call_id))
                    else:
                        max_tool_content_chars = 10000
                        truncated_result = result if len(result) <= max_tool_content_chars else (
                            result[:max_tool_content_chars] + "... [truncated]"
                        )
                        tool_messages.append(ToolMessage(content=truncated_result, tool_call_id=tool_call_id))
                
                elif tool_name == 'complete_task' and tool:
                    target_name = extract_target_name(tool_name, tool_args) if tool_args else None
                    log_tool_call(tool_name, target_name, status="started", agent="operator")
                    
                    result = execute_with_timeout(tool.invoke, OTHER_TOOL_TIMEOUT, {})
                    
                    log_tool_call(tool_name, target_name, status="completed", agent="operator")
                    
                    if result and isinstance(result, str):
                        log_content = "\n" + result + "\n"
                        truncated_log = truncate_content(
                            log_content, 
                            MAX_LOG_CHARS, 
                            "\n... [Output truncated for log brevity]\n"
                        )
                        _write_to_log(truncated_log)
                    
                    # Don't update status for complete_task - transitioning to evaluator
                    tool_messages.append(ToolMessage(content=result, tool_call_id=tool_call_id))
                
                # Use shared function for all other tools
                else:
                    logging_tools = [
                        'read_file', 'edit_file', 'list_directory',
                        'analyze_image', 'query_rag', 'search_web', 'fetch_web_page', 'grep_search',
                        'get_hardware_info'
                    ]
                    
                    result, tool_message = execute_tool_with_logging(
                        tool_call=tool_call,
                        tool_map=TOOL_MAP,
                        timeout=OTHER_TOOL_TIMEOUT,
                        agent_name="operator",
                        status_messages=TOOL_STATUS_MESSAGES,
                        on_status_update=on_operator_status_update,
                        log_result=tool_name in logging_tools if logging_tools else True,
                        max_result_chars=MAX_LOG_CHARS
                    )
                    
                    # These tools are skipped in callback - handle step_complete here with tool_result for error detection
                    if tool_name in ('read_file', 'query_rag', 'list_directory', 'search_web', 'fetch_web_page', 'grep_search', 'get_hardware_info'):
                        _update_operator_status(tool_name, tool_args, is_complete=True, tool_result=result)

                    
                    tool_messages.append(tool_message)
            
            # Log incrementally after tools complete to capture progress in case of interruption
            # Note: current_task_messages already includes response
            if tool_messages:
                interim_messages = current_task_messages + tool_messages
                _write_input_messages(interim_messages, "OPERATOR", current_task_index)

        completion_message = None
        if completion_request:
            completion_message = AIMessage(content="DONE")
            send_agent_event("operator", "complete", "")
            log_custom("OPERATOR", "complete_task called, adding DONE message", {
                "completion_request": completion_request,
                "has_completion_message": completion_message is not None
            })

        # Update state
        # Note: current_task_messages already includes response (added before tool execution)
        messages_update = [response] + tool_messages
        if completion_message:
            messages_update.append(completion_message)
        
        # current_task_messages already has response, so only add tool_messages and completion_message
        updated_task_messages = current_task_messages + tool_messages
        if completion_message:
            updated_task_messages = updated_task_messages + [completion_message]
        
        # Log updated messages (including AI response and tool results) to input_messages.md
        _write_input_messages(updated_task_messages, "OPERATOR", current_task_index)
        
        updated_task_messages, did_summarize_context, effective_model, trigger_input = maybe_summarize_messages(
            updated_task_messages,
            llm_with_tools,
            agent_name='operator',
            runtime_events=prompt_runtime_events,
            task_index=current_task_index,
        )
        if did_summarize_context:
            log_custom(
                "OPERATOR",
                f"Context summarization triggered for {effective_model}: {trigger_input:,} input tokens exceeds threshold",
            )
            send_agent_event("operator", "update", "Summarizing context (token limit approaching)")
            log_custom("OPERATOR", f"Context summarized, new message count: {len(updated_task_messages)}")
        
        update = {
            "messages": messages_update,
            "current_task_messages": updated_task_messages
        }
        if initial_files is not None:
            update["files_at_task_start"] = initial_files
        return finalize_update(update)

    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        _write_to_log(f"\n[DEBUG OPERATOR] Exception: {e}\n{error_trace}\n")
        
        if is_api_connection_error(e):
            raise e
            
        validation_tool_hint = None
        if ValidationError and isinstance(e, ValidationError):
            error_message = format_validation_error(e)
            m = re.search(r"validation error for (\w+)", str(e), re.I)
            if m:
                validation_tool_hint = m.group(1)
        else:
            error_message = f"Error executing step: {str(e)}"

        status_text = (
            error_message
            if isinstance(error_message, str) and error_message.lower().strip().startswith("error:")
            else f"Error: {error_message}"
        )
        send_agent_event(
            "operator",
            "error",
            status_text,
            tool_name=validation_tool_hint or "",
        )
        _write_to_log(f"\n[OPERATOR] Error: {error_message}\n")

        if (
            ValidationError
            and isinstance(e, ValidationError)
            and validation_tool_context.get("tool_call_id")
        ):
            clear_pending_execution()
            error_msg = ToolMessage(
                content=status_text,
                tool_call_id=validation_tool_context["tool_call_id"],
            )
            messages_update = []
            if response is not None:
                messages_update.append(response)
            messages_update.append(error_msg)
            updated_task_messages = current_task_messages + [error_msg]
        else:
            error_msg = AIMessage(content=status_text)
            messages_update = [error_msg]
            updated_task_messages = current_task_messages + [error_msg]

        _write_input_messages(updated_task_messages, "OPERATOR", current_task_index)
        update = {
            'messages': messages_update,
            'current_task_messages': updated_task_messages
        }
        if initial_files is not None:
            update["files_at_task_start"] = initial_files
        return finalize_update(update)
