
import sys
import os
import json
import io
import threading
import traceback
import signal
from typing import Optional, Literal

# Global interrupt event for coordinated interruption
interrupt_event = threading.Event()

# Plan review confirmation (runner thread blocks until main thread receives plan_confirm)
_plan_confirm_lock = threading.Lock()
_plan_confirm_event = threading.Event()
PlanConfirmationAction = Literal["confirm", "decline", "revise"]
_plan_confirm_result: Optional[dict[str, str]] = None

AUTO_IMPROVE_STATE_KEY = "_auto_improve_state"
DEFAULT_AUTO_IMPROVE_STATE = {
    "remaining_cycles": 0,
    "current_run_is_automatic": False,
}
_auto_improve_state_lock = threading.Lock()
_auto_improve_state = DEFAULT_AUTO_IMPROVE_STATE.copy()


def _normalize_plan_confirmation_result(
    result: Optional[object] = None,
    *,
    feedback: str = "",
) -> dict[str, str]:
    """Normalize legacy and structured confirmation payloads."""
    action: PlanConfirmationAction = "confirm"
    normalized_feedback = ""

    if isinstance(result, bool):
        action = "confirm" if result else "decline"
    elif isinstance(result, str):
        candidate = result.strip().lower()
        if candidate in {"confirm", "decline", "revise"}:
            action = candidate  # type: ignore[assignment]
        normalized_feedback = feedback
    elif isinstance(result, dict):
        candidate = str(result.get("action", "")).strip().lower()
        if candidate in {"confirm", "decline", "revise"}:
            action = candidate  # type: ignore[assignment]
        raw_feedback = result.get("feedback", "")
        normalized_feedback = raw_feedback if isinstance(raw_feedback, str) else str(raw_feedback or "")
    elif result is None:
        action = "confirm"

    if action != "revise":
        normalized_feedback = ""

    return {
        "action": action,
        "feedback": normalized_feedback.strip(),
    }


def begin_plan_confirmation_wait() -> dict[str, str]:
    """Block the graph runner until the CLI sends plan_confirm (or headless auto-confirms)."""
    # Auto-confirm when AUTO_CONFIRM_PLAN env var is enabled (bypasses user review)
    if os.getenv("AUTO_CONFIRM_PLAN", "").lower() in ("true", "1", "yes", "on"):
        return _normalize_plan_confirmation_result(True)
    if _get_auto_improve_state().get("current_run_is_automatic"):
        return _normalize_plan_confirmation_result(True)
    global _plan_confirm_result
    with _plan_confirm_lock:
        _plan_confirm_event.clear()
        _plan_confirm_result = None
    send_json("plan_awaiting_confirm", {})
    _plan_confirm_event.wait()
    with _plan_confirm_lock:
        if _plan_confirm_result is None:
            return _normalize_plan_confirmation_result(True)
        return dict(_plan_confirm_result)


def set_plan_confirmation(
    proceed: bool | str | dict[str, object],
    *,
    feedback: str = "",
) -> None:
    """Resume the graph after plan_review_confirm_node."""
    global _plan_confirm_result
    with _plan_confirm_lock:
        _plan_confirm_result = _normalize_plan_confirmation_result(proceed, feedback=feedback)
    _plan_confirm_event.set()


_plan_declined_flag = False
_plan_declined_user_input = ""


def mark_plan_declined(user_input: str) -> None:
    """Record that the user declined the reviewed plan (runner deletes checkpoint after graph ends)."""
    global _plan_declined_flag, _plan_declined_user_input
    _plan_declined_flag = True
    _plan_declined_user_input = user_input or ""


def consume_plan_declined() -> Optional[str]:
    """If plan was declined, return the original user request and clear; else None."""
    global _plan_declined_flag, _plan_declined_user_input
    if not _plan_declined_flag:
        return None
    _plan_declined_flag = False
    text = _plan_declined_user_input
    _plan_declined_user_input = ""
    return text


def _parse_auto_improve_cycles(value) -> int:
    """Parse AUTO_IMPROVE_CYCLES as a non-negative integer."""
    try:
        return max(int(str(value).strip()), 0)
    except (TypeError, ValueError):
        return 0


def _get_checkpoint_settings_path():
    from src.tools.base import WORKSPACE_DIR
    return WORKSPACE_DIR / "checkpoint_settings.json"


def _load_checkpoint_settings() -> dict:
    settings_path = _get_checkpoint_settings_path()
    if not settings_path.exists():
        return {}
    try:
        return json.loads(settings_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_checkpoint_settings(settings: dict) -> None:
    settings_path = _get_checkpoint_settings_path()
    try:
        settings_path.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    except Exception:
        pass


def _normalize_auto_improve_state(state: Optional[dict]) -> dict:
    raw = state or {}
    return {
        "remaining_cycles": _parse_auto_improve_cycles(raw.get("remaining_cycles", 0)),
        "current_run_is_automatic": bool(raw.get("current_run_is_automatic", False)),
    }


def _get_auto_improve_state() -> dict:
    with _auto_improve_state_lock:
        return dict(_auto_improve_state)


def _set_auto_improve_state(
    state: Optional[dict],
    *,
    persist: bool = True,
    configured_cycles: Optional[int] = None,
) -> dict:
    normalized = _normalize_auto_improve_state(state)
    with _auto_improve_state_lock:
        _auto_improve_state.update(normalized)
    if persist:
        settings = _load_checkpoint_settings()
        if configured_cycles is not None:
            settings["AUTO_IMPROVE_CYCLES"] = str(_parse_auto_improve_cycles(configured_cycles))
        settings[AUTO_IMPROVE_STATE_KEY] = normalized
        _write_checkpoint_settings(settings)
    return normalized


def _clear_auto_improve_state(*, persist: bool = True) -> None:
    with _auto_improve_state_lock:
        _auto_improve_state.update(DEFAULT_AUTO_IMPROVE_STATE)
    if persist:
        settings = _load_checkpoint_settings()
        settings.pop(AUTO_IMPROVE_STATE_KEY, None)
        _write_checkpoint_settings(settings)


def _load_auto_improve_state_from_checkpoint() -> dict:
    settings = _load_checkpoint_settings()
    state = settings.get(AUTO_IMPROVE_STATE_KEY)
    if state is None:
        normalized = DEFAULT_AUTO_IMPROVE_STATE.copy()
        with _auto_improve_state_lock:
            _auto_improve_state.update(normalized)
        return normalized
    return _set_auto_improve_state(state, persist=False)


def _seed_auto_improve_state_for_new_run() -> dict:
    configured_cycles = _parse_auto_improve_cycles(os.getenv("AUTO_IMPROVE_CYCLES", "0"))
    return _set_auto_improve_state(
        {
            "remaining_cycles": configured_cycles,
            "current_run_is_automatic": False,
        },
        configured_cycles=configured_cycles,
    )


def _prepare_auto_improve_state_for_prompt(*, restart: bool) -> dict:
    from src.checkpoint import checkpoint_file_exists, delete_checkpoint

    if restart and checkpoint_file_exists():
        delete_checkpoint()
    if restart or not checkpoint_file_exists():
        return _seed_auto_improve_state_for_new_run()
    return _load_auto_improve_state_from_checkpoint()


def _prepare_next_auto_improve_cycle(run_result) -> Optional[str]:
    state = _get_auto_improve_state()
    if not getattr(run_result, "auto_improve_eligible", False):
        return None
    remaining_cycles = state.get("remaining_cycles", 0)
    if remaining_cycles <= 0:
        return None
    _set_auto_improve_state(
        {
            "remaining_cycles": remaining_cycles - 1,
            "current_run_is_automatic": True,
        }
    )
    return runner.AUTO_IMPROVE_MESSAGE


def _finalize_auto_improve_state_after_run(run_result) -> None:
    from src.checkpoint import checkpoint_file_exists

    if checkpoint_file_exists():
        return
    if getattr(run_result, "status", "") != "success":
        _clear_auto_improve_state()
        return
    _clear_auto_improve_state()


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

def send_agent_event(
    agent: str,
    event: str,
    status: str = "",
    is_error: bool = False,
    output: str = "",
    user_feedback: str = "",
    tool_name: str = "",
):
    """Send agent lifecycle event (start, update, complete)."""
    payload = {
        "agent": agent,
        "event": event,
        "status": status,
        "is_error": is_error
    }
    if output:
        payload["output"] = output
    if user_feedback:
        payload["user_feedback"] = user_feedback
    if tool_name:
        payload["toolName"] = tool_name
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


def send_context_usage_snapshot(
    *,
    input_tokens: Optional[int] = None,
    agent_name: Optional[str] = None,
    model_name: Optional[str] = None,
    reset: bool = False,
) -> None:
    """Send the current restricted context-window usage snapshot."""
    try:
        from src.agents.utils.bridge import (
            build_replayed_context_usage_payload,
            remember_context_usage_payload,
            reset_context_usage_seed,
        )

        if reset:
            reset_context_usage_seed()

        payload = build_replayed_context_usage_payload(
            input_tokens=input_tokens,
            agent_name=agent_name,
            model_name=model_name,
        )
        remember_context_usage_payload(payload)
        send_json("context_usage", payload)
    except Exception:
        pass

# --- Environment Setup ---
from dotenv import load_dotenv
load_dotenv()
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["TRANSFORMERS_VERBOSITY"] = "error"
os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = "1"
os.environ["TQDM_DISABLE"] = "1"
os.environ["TERM"] = "xterm-256color"

# --- Import System ---
from src import runner
from src.llm_config import initialize_llm, initialize_llm_for_agent
from src.usage_tracker import generate_report, reset as reset_usage_tracker
from src.tools.base import LOGS_DIR

# Mutable LLM handles (rebuilt after CLI `update_env` for model-related keys).
_bridge_llm_state = {"llm": None, "agent_llms": None}
_graph_cache_stale = False

# Env keys that require new LangChain clients and a fresh compiled graph.
_LLM_ENV_KEYS = frozenset({
    "MODEL",
    "MODEL_API_KEY",
    "OPENAI_API_BASE",
    "API_BASE_URL",
    "STRATEGIST_MODEL",
    "STRATEGIST_MODEL_API_KEY",
    "STRATEGIST_API_BASE_URL",
    "OPERATOR_MODEL",
    "OPERATOR_MODEL_API_KEY",
    "OPERATOR_API_BASE_URL",
    "EVALUATOR_MODEL",
    "EVALUATOR_MODEL_API_KEY",
    "EVALUATOR_API_BASE_URL",
})


def _refresh_llm_clients_from_env(*, mark_graph_stale: bool = False) -> dict:
    """Rebuild primary and per-agent LLMs from ``os.environ``."""
    global _graph_cache_stale
    llm, model_name = initialize_llm()
    strategist_llm, strategist_model = initialize_llm_for_agent("strategist", llm, model_name)
    operator_llm, operator_model = initialize_llm_for_agent("operator", llm, model_name)
    evaluator_llm, evaluator_model = initialize_llm_for_agent("evaluator", llm, model_name)
    _bridge_llm_state["llm"] = llm
    _bridge_llm_state["agent_llms"] = {
        "strategist": strategist_llm,
        "operator": operator_llm,
        "evaluator": evaluator_llm,
    }
    model_info = {"model": model_name}
    if strategist_model != model_name:
        model_info["strategist_model"] = strategist_model
    if operator_model != model_name:
        model_info["operator_model"] = operator_model
    if evaluator_model != model_name:
        model_info["evaluator_model"] = evaluator_model
    if mark_graph_stale:
        _graph_cache_stale = True
    return model_info


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


def _emit_final_summary_if_needed() -> None:
    """Send the final summary for active checkpoint runs."""
    try:
        from src.tools.base import WORKSPACE_DIR
        from src.checkpoint import checkpoint_file_exists

        has_checkpoint = checkpoint_file_exists()
        if has_checkpoint:
            summary_path = WORKSPACE_DIR / "final_results" / "summary.md"
            if summary_path.exists():
                summary_content = summary_path.read_text(encoding="utf-8")
                if summary_content.strip():
                    send_json("final_summary", {"content": summary_content})
    except Exception:
        pass


def _clear_auto_improve_state_if_terminal() -> None:
    """Drop runtime auto-improve state when the run cannot resume."""
    try:
        from src.checkpoint import checkpoint_file_exists

        if not checkpoint_file_exists():
            _clear_auto_improve_state()
    except Exception:
        _clear_auto_improve_state()


def _done_status_for_result(run_result, run_error: Optional[Exception]) -> str:
    if run_error:
        return "error"
    if getattr(run_result, "status", "") == "fail":
        return "gave_up"
    return "completed"


def _execute_prompt_sequence(prompt: str, restart: bool) -> None:
    """Execute one user-initiated prompt plus any automatic follow-up cycles."""
    global _graph_cache_stale

    send_system_status("running")
    run_error = None
    final_result = None
    current_prompt = prompt
    current_restart = restart

    try:
        _prepare_auto_improve_state_for_prompt(restart=restart)

        while True:
            if _graph_cache_stale:
                runner.invalidate_graph_cache()
                _graph_cache_stale = False

            final_result = runner.process_prompt(
                current_prompt,
                _bridge_llm_state["llm"],
                if_restart=current_restart,
                agent_llms=_bridge_llm_state["agent_llms"],
            )

            next_prompt = _prepare_next_auto_improve_cycle(final_result)
            if next_prompt is None:
                _finalize_auto_improve_state_after_run(final_result)
                break

            current_prompt = next_prompt
            current_restart = False

    except KeyboardInterrupt:
        send_json("done", {"status": "interrupted"})
        send_system_status("completed")
        return
    except RuntimeError as e:
        if "cannot schedule new futures" in str(e):
            send_json("done", {"status": "interrupted"})
            send_system_status("completed")
            return
        raise
    except Exception as e:
        run_error = e
        _clear_auto_improve_state_if_terminal()
        tb = traceback.format_exc()
        send_json("error", {"message": str(e), "traceback": tb})

    send_system_status("completed")
    _emit_final_summary_if_needed()
    send_json("done", {"status": _done_status_for_result(final_result, run_error)})

    if _HAS_DEBUG_LOGGER:
        log_custom("BRIDGE", "Prompt command completed")


def main():
    send_json("ready", {})
    
    try:
        model_info = _refresh_llm_clients_from_env()
        send_json("init", model_info)
    except Exception as e:
        # Don't crash on startup if just missing environment variables.
        # The CLI handles displaying Settings if MODEL/MODEL_API_KEY are missing on prompt.
        send_json("init", {"model": None, "warning": str(e)})

    send_context_usage_snapshot()
    
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
            
            # Pass status_tracker to initialization functions
            # Note: The function signature updates for initialize_embeddings and initialize_rag will be done in subsequent steps
            initialize_embeddings(workspace_dir=WORKSPACE_DIR, status_tracker=status_tracker)
            initialize_rag(workspace_dir=WORKSPACE_DIR, status_tracker=status_tracker)
            send_json("rag_status", {"status": "done", "message": "Initialized QUASAR RAG System"})
        except Exception as e:
            send_json("rag_status", {"status": "error", "message": str(e)})

    send_json("system_ready", {})

    exec_thread = None
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
                
                if _bridge_llm_state.get("llm") is None:
                    send_json("error", {"message": "Language model is not properly initialized. Please check your CLI Settings (e.g., verify your API_BASE_URL if using a custom model, or ensure your MODEL_API_KEY is valid).", "traceback": ""})
                    continue
                
                if _HAS_DEBUG_LOGGER:
                    log_custom("BRIDGE", "Prompt command received", {
                        "prompt_length": len(prompt) if prompt else 0,
                        "restart": restart
                    })

                send_context_usage_snapshot(reset=True)
                
                def run_prompt_in_thread():
                    _execute_prompt_sequence(prompt, restart)

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
                    # Skip if LLM is not yet configured (MODEL/MODEL_API_KEY unset)
                    if _bridge_llm_state["llm"] is not None:
                        try:
                            graph_builder = build_graph(_bridge_llm_state["llm"])
                            graph = create_checkpoint_infrastructure(graph_builder)
                            config = get_thread_config()
                            state = graph.get_state(config)
                            state_history = list(graph.get_state_history(config))
                            
                            if state and state.values:
                                # Use is_replanning from state (most reliable)
                                is_replan = state.values.get('is_replanning', False)
                                history = extract_checkpoint_history(
                                    state.values,
                                    state.values.get('messages', []),
                                    is_replan=is_replan,
                                    state_history=state_history,
                                )
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
                    _clear_auto_improve_state(persist=False)
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
                    _clear_auto_improve_state(persist=False)
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
                    _clear_auto_improve_state(persist=False)
                    setup_final_results_folder()
                    send_json("archive_complete", {"success": True})
                except Exception as e:
                    send_json("archive_complete", {"success": False, "error": str(e)})
                
            elif command == "plan_confirm":
                if "action" in data or "feedback" in data:
                    set_plan_confirmation(
                        {
                            "action": data.get("action", "confirm"),
                            "feedback": data.get("feedback", ""),
                        }
                    )
                else:
                    proceed = data.get("proceed", True)
                    set_plan_confirmation(bool(proceed))

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
                
            elif command == "update_env":
                # Update environment variables in the Python process
                updates = data.get("updates", {})
                for key, val in updates.items():
                    if val is None or val == '':
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = str(val)
                send_json("env_updated", {"success": True, "keys": list(updates.keys())})
                if updates and any(k in _LLM_ENV_KEYS for k in updates):
                    try:
                        model_info = _refresh_llm_clients_from_env(mark_graph_stale=True)
                        send_json("init", model_info)
                    except Exception as e:
                        send_json("init", {"model": None, "warning": f"Model client refresh failed: {e}"})
                send_context_usage_snapshot()
                
            elif command == "exit":
                break
                
        except json.JSONDecodeError:
            continue
        except KeyboardInterrupt:
            # Stats already saved by signal handler, just send done and exit
            send_json("done", {"status": "interrupted"})
            
            # Wait for execution thread to finish/cleanup if it's running
            # This prevents premature interpreter shutdown while thread is still active
            if exec_thread and exec_thread.is_alive():
                 exec_thread.join(timeout=3.0)
            
            break
        except Exception as e:
            tb = traceback.format_exc()
            send_json("error", {"message": str(e), "traceback": tb})

if __name__ == "__main__":
    main()
