"""Main execution runner."""

import sys
from langchain_core.messages import AIMessage

from .tools.base import WORKSPACE_DIR, LOGS_DIR
from .state import create_initial_state

from .checkpoint import (
    checkpoint_file_exists,
    create_checkpoint_infrastructure,
    is_connection_valid,
    has_checkpoint_history,
    get_thread_config,
    DB_PATH,
)
from .results import (
    archive_completed_run,
    archive_exists_without_checkpoint,
)
from .graph import build_graph
from .debug_logger import (
    log_runner_event,
    log_graph_stream_start,
    log_exception,
    log_custom
)
from .usage_tracker import start_run, end_run, set_run_status

CONVERSATION_LOG = LOGS_DIR / "conversation.md"

# Auto-improvement mode message for second runs with empty input
AUTO_IMPROVE_MESSAGE = """Please analyze the previous run results and automatically improve the workflow. \
Review what was accomplished, identify any issues or areas for enhancement, and create an improved execution plan."""

# Global graph instance
_graph = None


def get_or_create_graph(llm):
    """Get existing graph or create new one."""
    global _graph
    if _graph is None:
        graph_builder = build_graph(llm)
        _graph = create_checkpoint_infrastructure(graph_builder)
    return _graph


def log_conversation(user_input: str, overwrite: bool = False):
    """Log user input to conversation file in markdown format."""
    try:
        with open(CONVERSATION_LOG, 'w' if overwrite else 'a', encoding='utf-8') as f:
            if overwrite:
                f.write("# QUASAR Conversation Log\n\n")
            f.write(f"## [User]: Request\n\n{user_input}\n\n")
    except Exception:
        pass


def process_prompt(user_input: str, llm, if_restart: bool = False) -> bool:
    """
    Process user prompt and execute the agent workflow.
    Returns: True if execution completed/aborted, False if interrupted by user (second press).
    """
    global _graph
    
    # Start run timing (pass model name for cost calculation)
    import os
    from .usage_tracker import (
        start_run, 
        reset as reset_usage_tracker, 
        load_stats_from_checkpoint,
        generate_interrupted_report_if_needed
    )
    
    # Reset tracking if starting a new project (not resuming)
    is_resuming = checkpoint_file_exists()
    if not if_restart and not is_resuming:
        reset_usage_tracker()
    elif is_resuming:
        # Generate report for any previous interrupted run before loading stats
        # This ensures interrupted runs get their usage reports on resume
        generate_interrupted_report_if_needed()
        # Load and accumulate previous token stats when resuming
        load_stats_from_checkpoint()
        
    model_name = os.getenv("MODEL", "")
    # Preserve start_time if resuming (so we track total run duration across interruptions)
    start_run(model_name, preserve_start_time=is_resuming)


    if if_restart and checkpoint_file_exists():
        from .checkpoint import delete_checkpoint
        delete_checkpoint()

    is_new_project = not checkpoint_file_exists() and not if_restart
    
    # Check if this is a second run (archive exists with no active checkpoint)
    # and user provided empty input. If so, trigger auto-improvement mode
    is_second_run = archive_exists_without_checkpoint()
    
    if is_second_run and (not user_input or not user_input.strip()):
        user_input = AUTO_IMPROVE_MESSAGE

    
    if not is_connection_valid():
        # Re-initialize graph if connection is invalid (or first run)
        _graph = None
        
    graph = get_or_create_graph(llm)
    
    config = get_thread_config()
    has_history = has_checkpoint_history(graph, config)
    # Only log user request for new projects, not when resuming from checkpoint
    if is_new_project:
        log_conversation(user_input, overwrite=True)
   
    # Log execution start
    log_custom("RUNNER", "NEW EXECUTION STARTED", {
        "user_input_length": len(user_input) if user_input else 0,
        "is_new_project": is_new_project,
        "has_history": has_history,
        "if_restart": if_restart
    })
   
    if has_history:
        # Send checkpoint status to CLI
        try:
            import bridge
            # Get state to extract task progress
            state = graph.get_state(config)
            state_values = state.values if state else {}
            plan = state_values.get('plan', [])
            completed = state_values.get('completed_steps', [])
            task_num = len(completed) + 1
            total_tasks = len(plan)
            bridge.send_checkpoint_status(True, task_num, total_tasks)
        except ImportError:
            pass  # Not running in bridge mode

    if has_history:
        if if_restart:
            inputs = None
        else:
            # Use input only if it's not empty/whitespace
            inputs = {"messages": [("user", user_input)]} if user_input and user_input.strip() else None
    else:
        if if_restart:
            pass
        inputs = create_initial_state(user_input)
    
    try:
        last_plan = []
        live = None
        
        # DEBUG: Log stream start
        log_graph_stream_start(inputs if inputs else {})
        
        # Send initial strategist status immediately so UI shows feedback before LLM starts
        try:
            import bridge
            archive_dir = WORKSPACE_DIR / "archive"
            is_replanning = archive_dir.exists() and archive_dir.is_dir()
            status_text = "Replanning" if is_replanning else "Analysing Request"
            # Send both start (to activate indicator) and update (to show status text in log)
            bridge.send_agent_event("strategist", "start", status_text)
            bridge.send_agent_event("strategist", "update", status_text)
        except ImportError:
            pass  # Not running in bridge mode
        
        # Execute graph stream
        iterator = graph.stream(inputs, config=config) if inputs else graph.stream(None, config=config)
            
        # DEBUG: Log iterator creation
        log_custom("RUNNER", "Graph stream iterator created", {"has_inputs": inputs is not None})
        
        # Reset interrupt flag at start of execution
        try:
            import bridge
            bridge.interrupt_event.clear()
        except (ImportError, AttributeError):
            pass  # Not running in bridge mode
        
        event_count = 0
        for event in iterator:
            # Check for interrupt signal from CLI
            try:
                import bridge
                if bridge.interrupt_event.is_set():
                    log_custom("RUNNER", "Interrupt event detected, raising KeyboardInterrupt")
                    raise KeyboardInterrupt("User requested interrupt via CLI")
            except (ImportError, AttributeError):
                pass  # Not running in bridge mode
            
            event_count += 1
            log_custom("RUNNER", f"Received event #{event_count}", {"event_keys": list(event.keys()) if event else []})
            
            for node_name, node_state in event.items():
                # DEBUG: Log node processing with comprehensive state info
                log_runner_event(node_name, node_state)
                
                if node_name == "strategist":
                    plan = node_state.get('plan', [])
                    if plan and plan != last_plan:
                        # Plan is now displayed progressively in the tree view
                        last_plan = plan
                        log_custom("RUNNER", "Plan updated in strategist event", {"plan_length": len(plan)})
                elif node_name == "operator":
                    # Operator is working - keep execution going
                    log_custom("RUNNER", "Operator node event received", {
                        "state_keys": list(node_state.keys()),
                        "plan_length": len(node_state.get('plan', [])),
                        "completed_steps": len(node_state.get('completed_steps', []))
                    })
        
        # Task completion cleanup (handled by bridge in bridge mode)
        pass
        
        # Get final state
        state_values = graph.get_state(config).values
        # Removed "EXECUTION COMPLETE" Header as requested (stop loading implicitly signals completion)
        
        # DEBUG: Log final state
        log_custom("RUNNER", "Execution completed, getting final state", {
            "state_keys": list(state_values.keys()) if state_values else []
        })
        
        messages = state_values.get('messages', [])
        plan = state_values.get('plan', [])
        completed_steps = state_values.get('completed_steps', [])
        step_results = state_values.get('step_results', {})
        
        # DEBUG: Log final state details
        log_custom("RUNNER", "Final state summary", {
            "plan_length": len(plan) if plan else 0,
            "completed_steps": len(completed_steps) if completed_steps else 0,
            "step_results_count": len(step_results) if step_results else 0,
            "messages_count": len(messages) if messages else 0,
            "all_tasks_done": len(completed_steps) >= len(plan) if plan else False
        })
        
        # Check if all tasks are completed (regardless of final message)
        all_tasks_done = len(completed_steps) >= len(plan) if plan else False
        
        # Check if operator gave up (either in final message or in step_results)
        should_delete_checkpoint = False
        if messages:
            final_message = messages[-1]
            if isinstance(final_message, AIMessage):
                content = final_message.content.strip()

                if content == "GIVE_UP" or "Operator failed to execute this step" in content:
                    should_delete_checkpoint = True
        
        # Also check step_results for failure summary
        if not should_delete_checkpoint and step_results:
            for summary in step_results.values():
                if "Operator failed to execute this step" in summary:
                    should_delete_checkpoint = True
                    break
        
        # Set run status based on outcome
        if should_delete_checkpoint:
            set_run_status("fail")
        elif all_tasks_done:
            set_run_status("success")
        
        # Archive everything when all tasks are done or if operator gave up
        if all_tasks_done or should_delete_checkpoint:
            # Generate usage report before archiving
            from .usage_tracker import generate_report
            from .tools.base import LOGS_DIR
            try:
                report_content = generate_report()
                report_path = LOGS_DIR / "usage_report.md"
                report_path.write_text(report_content, encoding='utf-8')
            except Exception:
                pass
            
            # Close DB connection before archiving
            from .checkpoint import _conn
            if _conn:
                try:
                    _conn.close()
                except Exception:
                    pass

            # Notify frontend that cleanup/archiving is starting
            try:
                import bridge
                bridge.send_cleanup_status("starting", "Archiving workspace...")
            except ImportError:
                pass  # Not running in bridge mode
            
            archive_completed_run()
            
            # Notify frontend that cleanup/archiving is complete
            try:
                import bridge
                bridge.send_cleanup_status("complete", "Archiving complete")
            except ImportError:
                pass  # Not running in bridge mode
            
            # Reset global graph as checkpoint is gone
            _graph = None
        
        if plan:
            pass
    except KeyboardInterrupt:
        log_custom("RUNNER", "KeyboardInterrupt received")
        set_run_status("interrupted")
        raise
    finally:
        from .usage_tracker import end_run
        
        # End run timing (always called, even on interruption)
        end_run()

    log_custom("RUNNER", "process_prompt completed", {"returning": True})
    return True

