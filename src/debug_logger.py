"""
Comprehensive debug logging for investigating strategist-to-operator transition issues.

Set environment variable DEBUG=1 to enable debug logging.
"""

import os
import sys
import json
import traceback
from datetime import datetime
from pathlib import Path

# Check if debug logging is enabled via environment variable
DEBUG_LOG_ENABLED = os.getenv("DEBUG", "0").lower() in ("1", "true", "yes")

# Import WORKSPACE_DIR from tools.base
try:
    from .tools.base import WORKSPACE_DIR, LOGS_DIR
except ImportError:
    _project_root = Path(__file__).parent.parent
    WORKSPACE_DIR = Path(os.getenv("WORKSPACE_DIR", str(_project_root / "workspace")))
    LOGS_DIR = WORKSPACE_DIR / "logs"

DEBUG_LOG_FILE = LOGS_DIR / "debug_cli.log"

# Only create log file if debug logging is enabled
if DEBUG_LOG_ENABLED:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    # Initialize/Overwrite the log file on module load
    try:
        with open(DEBUG_LOG_FILE, 'w', encoding='utf-8') as f:
            pass
    except Exception:
        pass


def _write_log(level: str, category: str, message: str, data: dict = None):
    """Write a debug log entry."""
    if not DEBUG_LOG_ENABLED:
        return
    
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
    entry = {
        "timestamp": timestamp,
        "level": level,
        "category": category,
        "message": message,
        "data": data or {}
    }
    
    try:
        DEBUG_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(DEBUG_LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry) + '\n')
    except Exception as e:
        sys.stderr.write(f"[DEBUG LOG ERROR] Failed to write to log file: {e}\n")
        sys.stderr.flush()


def _extract_state_info(state: dict) -> dict:
    """Extract common state information for logging."""
    if not state:
        return {"state_keys": [], "has_messages": False, "has_plan": False, "plan_length": 0}
    
    plan = state.get('plan', [])
    completed = state.get('completed_steps', [])
    return {
        "state_keys": list(state.keys()),
        "has_messages": bool(state.get('messages')),
        "has_plan": bool(plan),
        "plan_length": len(plan) if plan else 0,
        "completed_steps": len(completed) if completed else 0
    }


def log_strategist_start(state: dict):
    """Log when strategist node starts."""
    _write_log("INFO", "STRATEGIST", "Node started", _extract_state_info(state))


def log_strategist_plan_extracted(plan: list, content: str):
    """Log when plan is extracted from content."""
    _write_log("INFO", "STRATEGIST", "Plan extracted", {
        "plan_length": len(plan) if plan else 0,
        "plan_tasks": plan[:3] if plan else [],
        "content_length": len(content) if content else 0,
        "content_preview": content[:200] if content else ""
    })


def log_strategist_events_sent(events: list):
    """Log events sent by strategist."""
    _write_log("INFO", "STRATEGIST", "Events sent", {"events": events})


def log_strategist_return(state: dict):
    """Log what strategist returns."""
    info = _extract_state_info(state)
    info["return_keys"] = info.pop("state_keys")
    if state and state.get('plan'):
        info["plan_preview"] = state.get('plan', [])[:2]
    _write_log("INFO", "STRATEGIST", "Node returning", info)


def log_route_after_planning(state: dict, result: str):
    """Log routing decision after planning."""
    plan = state.get('plan', []) if state else []
    _write_log("INFO", "ROUTING", "route_after_planning called", {
        "state_keys": list(state.keys()) if state else [],
        "has_plan": bool(plan),
        "plan_length": len(plan),
        "plan_type": type(plan).__name__,
        "plan_is_empty": len(plan) == 0 if isinstance(plan, list) else True,
        "routing_result": result,
        "state_plan_value": str(plan)[:100] if plan else "None"
    })


def log_runner_event(node_name: str, node_state: dict):
    """Log events seen by runner."""
    info = _extract_state_info(node_state)
    info["node_name"] = node_name
    _write_log("INFO", "RUNNER", f"Processing node: {node_name}", info)


def log_operator_start(state: dict):
    """Log when operator node starts."""
    info = _extract_state_info(state)
    plan = state.get('plan', []) if state else []
    completed = state.get('completed_steps', []) if state else []
    info["current_task_index"] = len(completed) if completed else 0
    info["all_tasks_done"] = len(completed) >= len(plan) if plan else False
    _write_log("INFO", "OPERATOR", "Node started", info)


def log_bridge_send(type_: str, payload: dict):
    """Log messages sent via bridge."""
    _write_log("INFO", "BRIDGE", f"Sending {type_}", {
        "type": type_,
        "payload_keys": list(payload.keys()) if payload else [],
        "payload_preview": str(payload)[:200] if payload else ""
    })


def log_graph_stream_start(inputs: dict):
    """Log when graph streaming starts."""
    _write_log("INFO", "GRAPH", "Stream started", {
        "has_inputs": inputs is not None,
        "input_keys": list(inputs.keys()) if inputs else []
    })


def log_exception(category: str, exception: Exception, context: dict = None):
    """Log an exception."""
    _write_log("ERROR", category, f"Exception: {str(exception)}", {
        "exception_type": type(exception).__name__,
        "traceback": traceback.format_exc(),
        "context": context or {}
    })


def log_custom(category: str, message: str, data: dict = None):
    """Log a custom message."""
    _write_log("INFO", category, message, data or {})


def get_debug_log_path():
    """Get the path to the current debug log file."""
    return str(DEBUG_LOG_FILE)
