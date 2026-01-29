
import sys
import os
import json
import io
import threading
import traceback
import signal

# Global interrupt event for coordinated interruption
interrupt_event = threading.Event()

if __name__ == "__main__":
    # Alias this module as 'bridge' so that 'import bridge' anywhere in the application
    # returns this same module instance with the shared interrupt_event and other state.
    # This prevents creating a second separate instance of the bridge module.
    sys.modules["bridge"] = sys.modules["__main__"]

def _save_stats_on_interrupt(signum, frame):
    """Signal handler to save usage stats and report on SIGINT/SIGTERM.
    
    For graceful SIGINT/SIGTERM, we generate the report immediately and kill
    any running subprocesses (like mpirun/LAMMPS) by killing their process group.
    For SIGKILL, the report is generated on next startup.
    """
    # Signal that an interrupt has occurred so other threads/tools can stop
    interrupt_event.set()
    
    try:
        # FIRST: Kill any running subprocess before anything else
        # This ensures child processes (mpirun, LAMMPS, etc.) are terminated
        try:
            from src.tools.execution import interrupt_running_execution, has_running_process
            if has_running_process():
                interrupt_running_execution()
        except Exception:
            pass  # Continue even if this fails
        
        from src.usage_tracker import save_stats_to_checkpoint, generate_report, set_run_status, end_run
        from src.tools.base import LOGS_DIR
        
        # Set status to interrupted
        set_run_status("interrupted")
        
        # Save token stats to checkpoint
        save_stats_to_checkpoint()
        
        # Generate and save usage report (for graceful SIGINT)
        try:
            report_content = generate_report()
            report_path = LOGS_DIR / "usage_report.md"
            report_path.write_text(report_content, encoding='utf-8')
        except Exception:
            pass
        
        # End run timing
        end_run()
    except Exception:
        pass  # Fail silently - we're in a signal handler
    
    # Re-raise to propagate the interrupt
    raise KeyboardInterrupt("Interrupted by SIGINT")

# Register signal handlers before anything else
try:
    if threading.current_thread() is threading.main_thread():
        signal.signal(signal.SIGINT, _save_stats_on_interrupt)
        signal.signal(signal.SIGTERM, _save_stats_on_interrupt)
except (ValueError, AttributeError):
    pass  # Not in main thread or signal module issues


# Cache stdout fd at module load time
_STDOUT_FD = os.dup(sys.stdout.fileno())

# Optional debug logging
try:
    from src.debug_logger import log_bridge_send, log_custom
    _HAS_DEBUG_LOGGER = True
except ImportError:
    _HAS_DEBUG_LOGGER = False

def send_json(type_: str, payload: dict):
    """Send a structured JSON message to stdout."""
    if _HAS_DEBUG_LOGGER:
        log_bridge_send(type_, payload)
    message = json.dumps({"type": type_, "payload": payload}) + "\n"
    try:
        os.write(_STDOUT_FD, message.encode('utf-8'))
    except OSError:
        pass

# --- Agent Event API ---
# These functions are called directly by agents to send events to Node.js CLI

def send_agent_event(agent: str, event: str, status: str = "", is_error: bool = False, output: str = ""):
    """Send agent lifecycle event (start, update, complete)."""
    payload = {
        "agent": agent,
        "event": event,
        "status": status,
        "is_error": is_error
    }
    if output:
        payload["output"] = output
    send_json("agent_event", payload)

def send_plan_stream(content: str, is_complete: bool = False, parsed_plan: list = None, is_replanning: bool = False):
    """Send streaming execution plan content.
    
    Args:
        content: Raw streaming content (for display during streaming)
        is_complete: Whether the plan is complete
        parsed_plan: Optional list of parsed task strings (sent when complete)
        is_replanning: Whether this is a replanning operation (vs initial plan or review)
    """
    payload = {
        "content": content,
        "is_complete": is_complete
    }
    if parsed_plan is not None:
        payload["parsed_plan"] = parsed_plan
    if is_replanning:
        payload["_isReplanning"] = True
    send_json("plan_stream", payload)

def send_system_status(status: str):
    """Send system lifecycle status (running, completed)."""
    send_json("system_status", {"status": status})

def send_checkpoint_status(is_resuming: bool, task_num: int = 0, total_tasks: int = 0):
    """Send checkpoint resume status to CLI."""
    send_json("checkpoint_status", {
        "is_resuming": is_resuming,
        "task_num": task_num,
        "total_tasks": total_tasks
    })

def send_cleanup_status(status: str, message: str = ""):
    """Send cleanup/archiving status to CLI.
    
    Args:
        status: One of "starting", "complete", or "error"
        message: Optional status message
    """
    send_json("cleanup_status", {
        "status": status,
        "message": message
    })

def send_text_stream(agent: str, content: str, is_complete: bool = False):
    """Send streaming LLM text content to CLI.
    
    Args:
        agent: Agent name (e.g., 'operator', 'evaluator')
        content: Accumulated text content
        is_complete: Whether the streaming is complete
    """
    send_json("text_stream", {
        "agent": agent,
        "content": content,
        "is_complete": is_complete
    })

def send_thought_stream(agent: str, content: str, is_complete: bool = False):
    """Send streaming LLM thought content to CLI.
    
    Args:
        agent: Agent name (e.g., 'operator', 'evaluator')
        content: Accumulated thought content
        is_complete: Whether the streaming is complete
    """
    send_json("thought_stream", {
        "agent": agent,
        "content": content,
        "is_complete": is_complete
    })

# --- Environment Setup ---
from dotenv import load_dotenv
load_dotenv()
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["TQDM_DISABLE"] = "1"
os.environ["TERM"] = "xterm-256color"

# --- Import System ---
from src import runner
from src.llm_config import initialize_llm
from src.usage_tracker import generate_report, reset as reset_usage_tracker
from src.tools.base import LOGS_DIR


class BridgeConsole:
    """Console that routes prints to the Node.js UI."""

    def print(self, *objects, **kwargs):
        content = " ".join(str(obj) for obj in objects)
        if content.strip():
            send_json("log", {"text": content})

    def input(self, prompt: str = "", *args, **kwargs):
        return ""


# Patch input function to avoid blocking
def patched_get_input(console, prompt, *args, **kwargs):
    return ""

# Override stdout to avoid interfering with JSON framing
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)




def _read_previous_input_from_conversation():
    """Read previous input from conversation.md file."""
    from src.tools.base import LOGS_DIR
    conv_file = LOGS_DIR / "conversation.md"
    if conv_file.exists():
        try:
            content = conv_file.read_text(encoding='utf-8')
            # Parse markdown format - look for ## [User]: Request header
            lines = content.split('\n')
            in_user_request = False
            user_input_lines = []
            
            for line in lines:
                if line.startswith("## [User]: Request"):
                    in_user_request = True
                    continue
                elif in_user_request:
                    # Stop at any markdown header or separator
                    if line.strip() == "---" or line.startswith("#"):
                        break
                    if line.strip():  # Collect non-empty lines
                        user_input_lines.append(line)
            
            if user_input_lines:
                result = '\n'.join(user_input_lines).strip()
                
                # If it's the auto-improve message, return a clean label
                from src.runner import AUTO_IMPROVE_MESSAGE
                if result == AUTO_IMPROVE_MESSAGE:
                    return "Auto-improve"
                
                return result
            
            # Fallback: try old formats for backward compatibility
            for line in lines:
                if line.startswith("You: "):
                    result = line[5:].strip()
                    from src.runner import AUTO_IMPROVE_MESSAGE
                    if result == AUTO_IMPROVE_MESSAGE:
                        return "Auto-improve"
                    return result
        except Exception:
            pass
    return ""


def main():
    send_json("ready", {})
    
    try:
        llm, model_name = initialize_llm()
        send_json("init", {"model": model_name})
    except Exception as e:
        send_json("error", {"message": str(e)})
        return
    
    # Initialize RAG system
    enable_rag = os.getenv("ENABLE_RAG", "true").lower() in ("true", "1", "yes", "on")
    skip_rag = os.getenv("SKIP_RAG", "false").lower() in ("true", "1", "yes", "on")
    
    if enable_rag and not skip_rag:
        try:
            # Create status tracker callback
            def status_tracker(message: str):
                send_json("rag_status", {"status": "loading", "message": "Initializing QUASAR RAG System", "detail": message})
                
            send_json("rag_status", {"status": "initializing", "message": "Initializing QUASAR RAG System"})
            
            from src.rag import initialize_embeddings, initialize_rag
            from src.tools.base import WORKSPACE_DIR
            
            status_tracker("Loading Model...")
            # Pass status_tracker to initialization functions
            # Note: The function signature updates for initialize_embeddings and initialize_rag will be done in subsequent steps
            initialize_embeddings(workspace_dir=WORKSPACE_DIR, status_tracker=status_tracker)
            initialize_rag(workspace_dir=WORKSPACE_DIR, status_tracker=status_tracker)
            send_json("rag_status", {"status": "done", "message": "Initialized QUASAR RAG System"})
        except Exception as e:
            send_json("rag_status", {"status": "error", "message": str(e)})

    send_json("system_ready", {})

    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                break
            
            data = json.loads(line)
            command = data.get("command")
            
            if command == "prompt":
                prompt = data.get("content", "")
                restart = data.get("restart", False)
                
                if _HAS_DEBUG_LOGGER:
                    log_custom("BRIDGE", "Prompt command received", {
                        "prompt_length": len(prompt) if prompt else 0,
                        "restart": restart
                    })
                
                def run_prompt_in_thread():
                    send_system_status("running")
                    run_error = None
                    try:
                        runner.process_prompt(prompt, llm, if_restart=restart)
                    except KeyboardInterrupt:
                         # Handled interruption
                         send_json("done", {"status": "interrupted"})
                         send_system_status("completed")
                         return
                    except Exception as e:
                        run_error = e
                        tb = traceback.format_exc()
                        send_json("error", {"message": str(e), "traceback": tb})
                    
                    send_system_status("completed")
                    
                    # usage_report.md generation moved to runner.py to ensure it is archived
                    
                    # Read and send final summary if it exists
                    # Only send if checkpoint exists (active run), otherwise completed_run_info will handle it
                    try:
                        from src.tools.base import WORKSPACE_DIR
                        from src.checkpoint import checkpoint_file_exists
                        from src.results import final_results_exists_and_not_empty
                        
                        # Only send final_summary if checkpoint exists (active run completion)
                        # If no checkpoint but final_results exists, completed_run_info will send it instead
                        has_checkpoint = checkpoint_file_exists()
                        if has_checkpoint:
                            summary_path = WORKSPACE_DIR / "final_results" / "summary.md"
                            if summary_path.exists():
                                summary_content = summary_path.read_text(encoding='utf-8')
                                if summary_content.strip():
                                    send_json("final_summary", {"content": summary_content})
                        # If no checkpoint but final_results exists, let completed_run_info handle it
                        # (which is sent when CLI calls check_checkpoint)
                    except Exception:
                        pass
                    
                    # Send appropriate done status based on whether run succeeded or errored
                    # "completed" = successful run, "error" = exception occurred
                    # Both should trigger EXIT_ON_COMPLETION, but "interrupted" should not
                    if run_error:
                        send_json("done", {"status": "error"})
                    else:
                        send_json("done", {"status": "completed"})
                    
                    if _HAS_DEBUG_LOGGER:
                        log_custom("BRIDGE", "Prompt command completed")

                # Start execution in a separate thread so main loop remains responsive to interrupts
                exec_thread = threading.Thread(target=run_prompt_in_thread)
                exec_thread.daemon = True
                exec_thread.start()
                
            elif command == "check_checkpoint":
                from src.checkpoint import checkpoint_file_exists, get_thread_config, create_checkpoint_infrastructure
                from src.results import final_results_exists_and_not_empty, archive_exists_without_checkpoint
                from src.tools.base import WORKSPACE_DIR
                from src.graph import build_graph
                from bridge_history import extract_checkpoint_history
                from src.usage_tracker import generate_interrupted_report_if_needed
                
                exists = checkpoint_file_exists()
                
                # Generate usage report for any interrupted run BEFORE loading checkpoint history
                # This ensures interrupted runs get their reports even if killed with SIGKILL
                if exists:
                    try:
                        generated = generate_interrupted_report_if_needed()
                        if generated and _HAS_DEBUG_LOGGER:
                            log_custom("BRIDGE", "Generated usage report for interrupted run")
                    except Exception as e:
                        if _HAS_DEBUG_LOGGER:
                            log_custom("BRIDGE", f"Failed to generate interrupted report: {e}")
                previous_input = ""
                history = None
                
                if exists:
                    previous_input = _read_previous_input_from_conversation()
                    
                    # Extract history from checkpoint state
                    try:
                        graph_builder = build_graph(llm)
                        graph = create_checkpoint_infrastructure(graph_builder)
                        config = get_thread_config()
                        state = graph.get_state(config)
                        
                        if state and state.values:
                            # Use is_replanning from state (most reliable)
                            is_replan = state.values.get('is_replanning', False)
                            history = extract_checkpoint_history(state.values, state.values.get('messages', []), is_replan=is_replan)
                    except Exception:
                        traceback.print_exc()
                
                send_json("checkpoint_info", {
                    "exists": exists,
                    "previous_input": previous_input,
                    "history": history
                })
                
                # Check for completed run state (no checkpoint but archive with runs exists)
                # Note: Use archive_exists_without_checkpoint() instead of final_results_exists_and_not_empty()
                # because after a run completes, final_results is moved to archive/run_N/
                if not exists and (archive_exists_without_checkpoint() or final_results_exists_and_not_empty()):
                    summary_content = ""
                    summary_path = WORKSPACE_DIR / "final_results" / "summary.md"
                    
                    # If local summary doesn't exist, check the latest archive
                    if not summary_path.exists():
                        try:
                            archive_dir = WORKSPACE_DIR / "archive"
                            if archive_dir.exists():
                                max_run_num = 0
                                latest_run_dir = None
                                
                                for item in archive_dir.iterdir():
                                    if item.is_dir() and item.name.startswith("run_"):
                                        try:
                                            run_num = int(item.name.split("_", 1)[1])
                                            if run_num > max_run_num:
                                                max_run_num = run_num
                                                latest_run_dir = item
                                        except (ValueError, IndexError):
                                            continue
                                
                                if latest_run_dir:
                                    archive_summary = latest_run_dir / "final_results" / "summary.md"
                                    if archive_summary.exists():
                                        summary_path = archive_summary
                        except Exception:
                            pass

                    if summary_path.exists():
                        try:
                            summary_content = summary_path.read_text(encoding='utf-8')
                        except Exception:
                            pass
                    
                    prev_input = _read_previous_input_from_conversation()
                    
                    send_json("completed_run_info", {
                        "exists": True,
                        "summary": summary_content,
                        "previous_input": prev_input
                    })
                
            elif command == "fresh_start":
                # Clean workspace for fresh start (deletes archives too)
                from src.results import cleanup_workspace_for_fresh_start
                from src.checkpoint import delete_checkpoint
                
                try:
                    cleanup_workspace_for_fresh_start()
                    delete_checkpoint()
                    send_json("fresh_start_complete", {"success": True})
                except Exception as e:
                    send_json("fresh_start_complete", {"success": False, "error": str(e)})
                
            elif command == "clear_checkpoint":
                # Clear checkpoint and workspace but keep archives
                from src.results import cleanup_workspace_keep_archive, archive_exists_without_checkpoint
                from src.checkpoint import delete_checkpoint
                from src.tools.base import WORKSPACE_DIR
                
                try:
                    cleanup_workspace_keep_archive()
                    delete_checkpoint()
                    
                    # Check if archives exist - if so, show completed_run_info prompt
                    if archive_exists_without_checkpoint():
                        # Get summary from latest archive
                        summary_content = ""
                        try:
                            archive_dir = WORKSPACE_DIR / "archive"
                            if archive_dir.exists():
                                max_run_num = 0
                                latest_run_dir = None
                                
                                for item in archive_dir.iterdir():
                                    if item.is_dir() and item.name.startswith("run_"):
                                        try:
                                            run_num = int(item.name.split("_", 1)[1])
                                            if run_num > max_run_num:
                                                max_run_num = run_num
                                                latest_run_dir = item
                                        except (ValueError, IndexError):
                                            continue
                                
                                if latest_run_dir:
                                    archive_summary = latest_run_dir / "final_results" / "summary.md"
                                    if archive_summary.exists():
                                        summary_content = archive_summary.read_text(encoding='utf-8')
                        except Exception:
                            pass
                        
                        send_json("completed_run_info", {
                            "exists": True,
                            "summary": summary_content,
                            "previous_input": ""
                        })
                    else:
                        # No archives - just confirm checkpoint cleared
                        send_json("clear_checkpoint_complete", {"success": True})
                except Exception as e:
                    send_json("clear_checkpoint_complete", {"success": False, "error": str(e)})
                
            elif command == "archive_and_continue":
                # Archive current workspace (move to archive/run_N) and prepare for improvement
                from src.results import setup_final_results_folder
                
                try:
                    setup_final_results_folder()
                    send_json("archive_complete", {"success": True})
                except Exception as e:
                    send_json("archive_complete", {"success": False, "error": str(e)})
                
            elif command == "interrupt":
                interrupt_event.set()
                
                # FIRST: Kill any running subprocess immediately
                # This is critical because the CLI may send SIGKILL right after this,
                # and we need to ensure child processes (mpirun, LAMMPS, etc.) are terminated
                # before the bridge process dies.
                try:
                    from src.tools.execution import interrupt_running_execution, has_running_process
                    if has_running_process():
                        interrupt_running_execution()
                except Exception as e:
                    if _HAS_DEBUG_LOGGER:
                        log_custom("BRIDGE", f"Failed to kill subprocess on interrupt: {e}")
                
                # Report generation and stats saving
                # We do this here to ensure immediate feedback even if worker thread is slow to stop
                try:
                    from src.usage_tracker import save_stats_to_checkpoint, generate_report, set_run_status, end_run
                    from src.tools.base import LOGS_DIR
                    
                    # Set status to interrupted
                    set_run_status("interrupted")
                    
                    # Save token stats to checkpoint
                    save_stats_to_checkpoint()
                    
                    # Generate and save usage report (for graceful interruption)
                    try:
                        report_content = generate_report()
                        report_path = LOGS_DIR / "usage_report.md"
                        report_path.write_text(report_content, encoding='utf-8')
                    except Exception:
                        pass
                    
                    # End run timing
                    end_run()
                except Exception as e:
                    if _HAS_DEBUG_LOGGER:
                        log_custom("BRIDGE", f"Failed to save stats on interrupt: {e}")
                
                send_json("interrupt_acknowledged", {"success": True})
                
            elif command == "exit":
                break
                
        except json.JSONDecodeError:
            continue
        except KeyboardInterrupt:
            # Stats already saved by signal handler, just send done and exit
            send_json("done", {"status": "interrupted"})
            break
        except Exception as e:
            tb = traceback.format_exc()
            send_json("error", {"message": str(e), "traceback": tb})

if __name__ == "__main__":
    main()
