"""
Evaluator agent node implementation.
Validates task outputs and drives corrections through operator feedback loop.
"""

import time
from pathlib import Path
from typing import Dict, List
from langchain_core.messages import AIMessage, SystemMessage, HumanMessage, ToolMessage, BaseMessage

from ..state import State
from ..tools import (
    read_file,
    list_directory,
    analyze_image,
    execute_temporary_python,
    search_web,
    fetch_web_page,
    submit_evaluation,
    grep_search,
)
from .utils import (
    get_project_context,
    write_execution_log,
    execute_with_timeout,
    _write_input_messages,
    log_agent_header,
    log_tool_call,
    log_result,
    is_api_connection_error,
    handle_api_retry,
    MAX_LOG_CHARS,
    truncate_content,
    send_agent_event,
    send_text_stream,
    send_thought_stream,
    APIConnectionError,
    extract_tool_call_info,
    extract_target_name,
    extract_project_request,
    format_plan,
    format_history,
    execute_tool_with_logging,
    detect_repeated_tool_calls,
    MAX_REPEATED_TOOL_CALLS,
    stream_with_token_tracking,
    send_tool_status,
    update_agent_status,
)
from ..context_summarizer import maybe_summarize_messages
from ..prompting import (
    build_evaluation_feedback_injection,
    build_evaluator_messages,
    build_evaluator_repeated_tool_warning_injection,
    clear_prompt_runtime_events_for_task,
    prompt_identity_from_state,
    prompt_metadata_update,
    upsert_prompt_runtime_event,
)
from ..prompting.debug import log_prompt_assembly, log_prompt_injection

EVALUATOR_TOOL_TIMEOUT = 60
MAX_TOOL_ITERATIONS = 50
MAX_RETRIES = 3  # Allow 3 retry attempts (4 total tries)

EVALUATOR_TOOL_MAP = {
    'read_file': read_file,
    'list_directory': list_directory,
    'analyze_image': analyze_image,
    'execute_temporary_python': execute_temporary_python,
    'search_web': search_web,
    'fetch_web_page': fetch_web_page,
    'submit_evaluation': submit_evaluation,
    'grep_search': grep_search,
}


def _get_message_role(msg: BaseMessage) -> str:
    """Get role name for a message."""
    if isinstance(msg, AIMessage):
        return "Operator"
    if isinstance(msg, HumanMessage):
        return "Evaluator"
    if isinstance(msg, ToolMessage):
        return "Tool Result"
    return "Unknown"


def _build_chat_history(messages: List[BaseMessage]) -> str:
    """Build chat history text from messages, filtering out system messages."""
    history_parts = []
    for msg in messages:
        if isinstance(msg, SystemMessage):
            continue
        
        role = _get_message_role(msg)
        content = getattr(msg, 'content', '')
        
        if len(content) > MAX_LOG_CHARS:
            content = content[:MAX_LOG_CHARS] + "... [truncated]"
        
        history_parts.append(f"{role}: {content}\n\n")
    
    return "".join(history_parts)


def _write_unresolved_summary(task: str, issues: str) -> Path:
    """Write unresolved issues to final_results/summary.md."""
    project_root = Path(__file__).resolve().parents[2]
    results_dir = project_root / "final_results"
    results_dir.mkdir(exist_ok=True)
    summary_path = results_dir / "summary.md"
    summary_body = f"# Unresolved Task\n\n## Task\n{task}\n\n## Outstanding Issues\n{issues}\n"
    summary_path.write_text(summary_body)
    return summary_path


def _is_operator_context(msg: BaseMessage) -> bool:
    """Check if a HumanMessage is the operator's initial context."""
    if isinstance(msg, HumanMessage):
        content = getattr(msg, 'content', '')
        return content.strip().startswith('### PROJECT STATE') or content.strip().startswith('### Context & Scope')
    return False


def _is_meaningful_operator_work(msg: BaseMessage) -> bool:
    """Check if a message represents actual operator work."""
    if isinstance(msg, ToolMessage):
        return True
    if isinstance(msg, AIMessage):
        content = getattr(msg, 'content', '')
        msg_content = content.strip() if isinstance(content, str) else ''
        
        if msg_content in ('DONE', 'GIVE_UP'):
            return False
        return bool(msg_content) or bool(getattr(msg, 'tool_calls', None))
    return False


def evaluator_setup_node(state: State, llm_with_tools=None) -> State:
    """Evaluator setup node - prepares context and handles edge cases.
    
    Returns early if operator hasn't worked or gave up.
    Otherwise, prepares evaluation_messages for the loop node.
    """
    from ..debug_logger import log_custom
    
    # Send both start (to activate indicator) and update (to show status in log)
    send_agent_event("evaluator", "start", "Evaluating Task Completion")
    send_agent_event("evaluator", "update", "Evaluating Task Completion")
    
    if llm_with_tools is None:
        return {
            "messages": [HumanMessage(content="EVALUATION_ERROR: LLM with tools not properly initialized.")]
        }
    
    plan = state.get('plan', [])
    completed_steps = state.get('completed_steps', [])
    step_results = state.get('step_results', {})
    current_task_messages = state.get('current_task_messages', [])
    evaluation_attempts = state.get('evaluation_attempts', 0)
    messages = state.get('messages', [])
    
    project_request = state.get('user_input', '') or extract_project_request(messages)
    formatted_plan = format_plan(plan)
    formatted_history = format_history(step_results, completed_steps)
    
    current_task_index = len(completed_steps)
    if current_task_index >= len(plan):
        return {}
    
    current_task = plan[current_task_index]
    
    # Check if operator has done any work
    operator_has_worked = False
    if current_task_messages:
        non_system_msgs = [
            msg for msg in current_task_messages 
            if not isinstance(msg, SystemMessage) and 
            not (isinstance(msg, HumanMessage) and (
                msg.content.strip().startswith('### PROJECT STATE') or 
                msg.content.strip().startswith('### Context & Scope') or
                msg.content.strip().startswith('Task') and 'completed successfully' in msg.content or
                msg.content.strip().startswith('Please start working on') or
                'EVALUATION_FEEDBACK' in msg.content
            ))
        ]
        operator_has_worked = any(_is_meaningful_operator_work(msg) for msg in non_system_msgs)
    
    if not operator_has_worked:
        return {
            "messages": [HumanMessage(content=f"Please start working on Task {current_task_index + 1}.")],
            "current_task_messages": current_task_messages,
            "evaluation_messages": [],  # Clear any stale evaluation messages
        }
    
    # Check if operator gave up
    operator_gave_up = False
    for msg in reversed(current_task_messages):
        content = getattr(msg, 'content', '')
        msg_content = content.strip() if isinstance(content, str) else ''
        if isinstance(msg, AIMessage) and msg_content == "GIVE_UP":
            operator_gave_up = True
            break
            
    if operator_gave_up:
        summary = "Operator failed to execute this step, stop here\n"
        new_results = step_results.copy()
        new_results[current_task_index] = summary
        
        formatted_history_failed = "\n".join([
            f"Task {i+1}: {new_results.get(i, 'No summary recorded.')}"
            for i in range(current_task_index + 1)
        ])
        write_execution_log(project_request, formatted_plan, formatted_history_failed)
        
        return {
            "completed_steps": completed_steps + [current_task],
            "step_results": new_results,
            "current_task_messages": [],
            "messages": [AIMessage(content=f"Task {current_task_index + 1} Summary: {summary}")],
            "evaluation_attempts": 0,
            "evaluation_messages": [],
            "prompt_runtime_events": clear_prompt_runtime_events_for_task(
                state.get("prompt_runtime_events", []),
                task_index=current_task_index,
            ),
        }



    
    operator_messages_only = [
        msg for msg in current_task_messages 
        if not isinstance(msg, SystemMessage) and not _is_operator_context(msg)
    ]
    operator_history = _build_chat_history(operator_messages_only)
    
    prompt_profile, prompt_version = prompt_identity_from_state(state)
    prompt_assembly = build_evaluator_messages(
        project_context=get_project_context(project_request, formatted_plan, formatted_history),
        current_task=current_task,
        current_task_index=current_task_index,
        total_tasks=len(plan),
        operator_history=operator_history,
        profile=prompt_profile,
        version=prompt_version,
    )
    log_prompt_assembly(prompt_assembly, task_index=current_task_index, context="setup")
    
    log_agent_header("Evaluator", current_task_index, "Evaluating Task Completion")
    
    evaluation_messages = prompt_assembly.messages
    _write_input_messages(evaluation_messages, "EVALUATOR")
    
    log_custom("EVALUATOR_SETUP", "Prepared evaluation context", {
        "current_task_index": current_task_index,
    })
    
    # Return state with evaluation_messages for loop node
    return {
        "evaluation_messages": evaluation_messages,
        **prompt_metadata_update(state, prompt_assembly),
    }


def evaluator_loop_node(state: State, llm_with_tools=None) -> State:
    """Evaluator loop node - single iteration of LLM call + tool execution.
    
    Performs one LLM invocation and processes tool calls.
    Returns with updated evaluation_messages for checkpointing.
    Returns final state when submit_evaluation is called or max iterations reached.
    """
    from ..debug_logger import log_custom
    
    if llm_with_tools is None:
        return {
            "messages": [HumanMessage(content="EVALUATION_ERROR: LLM with tools not properly initialized.")],
            "evaluation_messages": [],
        }
    
    evaluation_messages = list(state.get('evaluation_messages', []))
    
    # If no evaluation messages, we shouldn't be here
    if not evaluation_messages:
        log_custom("EVALUATOR_LOOP", "No evaluation messages, returning")
        return {"evaluation_messages": []}
    
    # Check for repeated identical tool calls
    repeated_tool = detect_repeated_tool_calls(evaluation_messages)
    if repeated_tool:
        tool_name, count = repeated_tool
        warning_injection = build_evaluator_repeated_tool_warning_injection(tool_name, count)
        loop_warning = warning_injection.content
        already_has_loop_warning = any(
            isinstance(m, HumanMessage) and getattr(m, "content", "") == loop_warning
            for m in evaluation_messages
        )
        if not already_has_loop_warning:
            log_custom("EVALUATOR_LOOP", f"Detected {count} repeated calls to {tool_name}, injecting warning")
            log_prompt_injection(warning_injection, context="repeated_tool")
            evaluation_messages.append(warning_injection.to_human_message())
            return {"evaluation_messages": evaluation_messages}
    
    plan = state.get('plan', [])
    completed_steps = state.get('completed_steps', [])
    step_results = state.get('step_results', {})
    current_task_messages = state.get('current_task_messages', [])
    evaluation_attempts = state.get('evaluation_attempts', 0)
    prompt_runtime_events = list(state.get("prompt_runtime_events", []) or [])
    
    current_task_index = len(completed_steps)
    if current_task_index >= len(plan):
        return {"evaluation_messages": []}
    
    current_task = plan[current_task_index]
    

    
    # Count iterations from evaluation_messages length (each iteration adds at least 1 AI response)
    ai_response_count = sum(1 for msg in evaluation_messages if isinstance(msg, AIMessage))
    
    try:
        # Use shared streaming helper - stream text to UI for real-time display
        accumulated_text = ""
        accumulated_thoughts = ""
        
        def on_content(text):
            nonlocal accumulated_text
            accumulated_text += text
            # Stream delta to UI — frontend accumulates progressively
            send_text_stream("evaluator", text, is_complete=False)
        
        def on_thought(text):
            nonlocal accumulated_thoughts
            accumulated_thoughts += text
            send_thought_stream("evaluator", accumulated_thoughts, is_complete=False)
        
        full_content, tool_calls, _, _ = stream_with_token_tracking(
            llm_with_tools, evaluation_messages, on_content=on_content, on_thought=on_thought,
            agent_name='evaluator'
        )
        
        # Send completion signal for text streaming
        if full_content:
            send_text_stream("evaluator", full_content, is_complete=True)
        if accumulated_thoughts:
            send_thought_stream("evaluator", accumulated_thoughts, is_complete=True)
        
        # Create AIMessage with content and tool_calls and append to messages
        ai_response = AIMessage(content=full_content)
        if tool_calls:
            ai_response.tool_calls = tool_calls
        evaluation_messages.append(ai_response)
        
        if not tool_calls:
            if full_content:
                reminder = "Please provide your final decision by calling the `submit_evaluation` function with either status='pass' or status='fail' and a summary."
                evaluation_messages.append(HumanMessage(content=reminder))
                
                if ai_response_count >= MAX_TOOL_ITERATIONS:
                    return {
                        "messages": [HumanMessage(content="EVALUATION_ERROR: Evaluator provided text but failed to call submit_evaluation after multiple attempts.")],
                        "evaluation_messages": [],
                    }
                # Return for next iteration
                return {"evaluation_messages": evaluation_messages}
            
            retry_msg = "Your last response was empty. Please continue your evaluation and remember to call `submit_evaluation` when finished."
            evaluation_messages.append(HumanMessage(content=retry_msg))
            
            if ai_response_count >= MAX_TOOL_ITERATIONS:
                return {
                    "messages": [HumanMessage(content="EVALUATION_ERROR: The evaluator sent multiple empty responses.")],
                    "evaluation_messages": [],
                }
            return {"evaluation_messages": evaluation_messages}

        # Execute tools
        tool_messages = []
        evaluation_decision = None
        
        for tool_call in tool_calls:
            tool_name, tool_args, tool_call_id = extract_tool_call_info(tool_call)
            target_name = extract_target_name(tool_name, tool_args)
            
            if tool_name == 'submit_evaluation':
                status_arg = tool_args.get('status', '').lower()
                summary_arg = tool_args.get('summary', '')
                
                if status_arg in ['pass', 'fail'] and summary_arg:
                    evaluation_decision = {
                        'status': status_arg,
                        'summary': summary_arg.strip()
                    }
                continue
            
            def on_evaluator_status_update(tn: str, tool_args: dict, is_complete: bool):
                """Update evaluator status based on tool execution using shared helper."""
                if tn == 'submit_evaluation':
                    return
                
                # Skip analyze_image completion here - handled separately with output
                if tn == 'analyze_image' and is_complete:
                    return
                
                # Use shared helper for consistent formatting
                send_tool_status(
                    "evaluator", tn, tool_args, 
                    is_complete=is_complete, 
                    idle_status="Evaluating Task Completion" if is_complete else None
                )
            
            result, tool_message = execute_tool_with_logging(
                tool_call=tool_call,
                tool_map=EVALUATOR_TOOL_MAP,
                timeout=EVALUATOR_TOOL_TIMEOUT,
                agent_name="evaluator",
                status_messages=None,  # Using shared helper via callback
                on_status_update=on_evaluator_status_update,
                log_result=True,
                max_result_chars=MAX_LOG_CHARS
            )
            
            # Send detailed status update with tool_result for context-aware messages
            # This ensures tools like read_file display properly at runtime (not just in history)
            if tool_name not in ('submit_evaluation', 'analyze_image'):
                update_agent_status("evaluator", tool_name, tool_args, is_complete=True, tool_result=result)
            
            # Special handling for analyze_image - use shared helper for step_complete with output
            if tool_name == 'analyze_image' and result:
                from .utils import handle_analyze_image_status
                handle_analyze_image_status("evaluator", tool_args, result)
            
            tool_messages.append(tool_message)
        
        evaluation_messages.extend(tool_messages)
        
        # Process evaluation decision if we have one
        if evaluation_decision:
            status = evaluation_decision['status']
            summary = evaluation_decision['summary']
            
            messages_list = state.get('messages', [])
            project_request = state.get('user_input', '') or extract_project_request(messages_list)
            formatted_plan = format_plan(plan)
            
            if status == "pass":
                display_summary = summary
                
                display_summary += "\n"
                
                new_results = step_results.copy()
                new_results[current_task_index] = display_summary
                
                formatted_history_passed = "\n".join([
                    f"Task {i+1}: {new_results.get(i, 'No summary recorded.')}"
                    for i in range(current_task_index + 1)
                ])
                
                write_execution_log(project_request, formatted_plan, formatted_history_passed)
                
                send_agent_event("evaluator", "complete", "Evaluation Passed", output=display_summary)
                log_result("PASS", summary)
                
                # Persist evaluator's AIMessages and ToolMessages to main messages for checkpoint history
                # Skip SystemMessage and context HumanMessage (first two), keep actual evaluation messages
                evaluator_history_messages = [
                    msg for msg in evaluation_messages[2:] 
                    if isinstance(msg, (AIMessage, ToolMessage))
                ]
                
                return {
                    "completed_steps": completed_steps + [current_task],
                    "step_results": new_results,
                    "current_task_messages": [],
                    "messages": evaluator_history_messages + [HumanMessage(content=f"Task {current_task_index + 1} completed successfully. Please proceed to the next task.")],
                    "evaluation_attempts": 0,
                    "evaluation_messages": [],  # Clear for next task
                    "prompt_runtime_events": clear_prompt_runtime_events_for_task(
                        prompt_runtime_events,
                        task_index=current_task_index,
                    ),
                }
            
            elif status == "fail":
                if evaluation_attempts < MAX_RETRIES:
                    retry_num = evaluation_attempts + 1
                    send_agent_event("evaluator", "complete", f"Evaluation Failed - Retry {retry_num}/{MAX_RETRIES}", output=summary)
                    log_result("FAIL", summary)
                    
                    feedback_injection = build_evaluation_feedback_injection(
                        current_task_index=current_task_index,
                        retry_num=retry_num,
                        max_retries=MAX_RETRIES,
                        summary=summary,
                    )
                    log_prompt_injection(feedback_injection, task_index=current_task_index, context="evaluation_feedback")
                    feedback_msg = feedback_injection.to_human_message()
                    prompt_runtime_events = upsert_prompt_runtime_event(
                        prompt_runtime_events,
                        feedback_injection,
                        task_index=current_task_index,
                    )
                    
                    # Persist evaluator's AIMessages and ToolMessages for checkpoint history
                    evaluator_history_messages = [
                        msg for msg in evaluation_messages[2:] 
                        if isinstance(msg, (AIMessage, ToolMessage))
                    ]
                    
                    return {
                        "messages": evaluator_history_messages + [feedback_msg],
                        "current_task_messages": current_task_messages + [feedback_msg],
                        "evaluation_attempts": evaluation_attempts + 1,
                        "evaluation_messages": [],  # Clear for retry
                        "prompt_runtime_events": prompt_runtime_events,
                    }
                
                else:
                    log_result("FAIL", summary)
                    send_agent_event("evaluator", "complete", "Evaluation Failed - Task Skipped", output=f"Unresolved: {summary}")
                    
                    _write_unresolved_summary(current_task, summary)
                    
                    failure_msg = AIMessage(content="GIVE_UP")
                    new_results = step_results.copy()
                    new_results[current_task_index] = f"Unresolved: {summary}"
                    
                    return {
                        "messages": [failure_msg],
                        "current_task_messages": [],
                        "step_results": new_results,
                        "evaluation_attempts": 0,
                        "evaluation_messages": [],
                        "prompt_runtime_events": clear_prompt_runtime_events_for_task(
                            prompt_runtime_events,
                            task_index=current_task_index,
                        ),
                    }

        # No final decision yet, return for next iteration with updated messages
        if ai_response_count >= MAX_TOOL_ITERATIONS:
            return {
                "messages": [HumanMessage(content="EVALUATION_ERROR: Max tool iterations reached without final decision.")],
                "evaluation_messages": [],
            }
        
        evaluation_messages, did_summarize_context, effective_model, trigger_input = maybe_summarize_messages(
            evaluation_messages,
            llm_with_tools,
            agent_name='evaluator',
            runtime_events=prompt_runtime_events,
            task_index=current_task_index,
        )
        if did_summarize_context:
            from ..debug_logger import log_custom as _log
            _log(
                "EVALUATOR",
                f"Context summarization triggered for {effective_model}: {trigger_input:,} input tokens exceeds threshold",
            )
            send_agent_event("evaluator", "update", "Summarizing context (token limit approaching)")
            _log("EVALUATOR", f"Context summarized, new message count: {len(evaluation_messages)}")
        
        return {"evaluation_messages": evaluation_messages}

    except Exception as e:
        if is_api_connection_error(e):
            # Let graph handle retry by returning with current state
            raise APIConnectionError(f"API connection error: {str(e)}")
        else:
            import traceback
            error_trace = traceback.format_exc()
            log_result("ERROR", f"{str(e)}\n{error_trace}")
            
            if ai_response_count >= MAX_TOOL_ITERATIONS:
                return {
                    "messages": [HumanMessage(content=f"EVALUATION_ERROR: {str(e)}")],
                    "evaluation_messages": [],
                }
            # Return current state for potential retry
            return {"evaluation_messages": evaluation_messages}


# Keep old function name as alias for backward compatibility (deprecated)
def evaluator_node(state: State, llm_with_tools=None) -> State:
    """DEPRECATED: Use evaluator_setup_node and evaluator_loop_node instead.
    
    This function is kept for backward compatibility but should not be used.
    """
    from ..debug_logger import log_custom
    log_custom("EVALUATOR", "WARNING: Using deprecated evaluator_node")
    # Run setup first, then loop until done
    setup_result = evaluator_setup_node(state, llm_with_tools)
    if setup_result.get('evaluation_messages'):
        # Merge setup result into state and run loop
        merged_state = {**state, **setup_result}
        while merged_state.get('evaluation_messages'):
            loop_result = evaluator_loop_node(merged_state, llm_with_tools)
            if not loop_result.get('evaluation_messages'):
                return loop_result
            merged_state = {**merged_state, **loop_result}
    return setup_result
