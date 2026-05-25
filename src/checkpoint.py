"""Checkpoint infrastructure for state persistence."""

import sqlite3
from typing import Optional, TYPE_CHECKING

from langgraph.checkpoint.sqlite import SqliteSaver

from .tools.base import WORKSPACE_DIR
from .debug_logger import log_custom, log_exception
from .artifacts import (
    get_checkpoint_db_path,
    get_checkpoint_settings_path,
    get_checkpoint_sidecar_paths,
    get_pending_execution_path,
    migrate_legacy_runtime_artifacts,
)

if TYPE_CHECKING:  # Only import for type checkers to avoid runtime dependency issues
    from langgraph.graph import CompiledGraph

# Path configuration
DB_PATH = get_checkpoint_db_path(WORKSPACE_DIR)
THREAD_ID = "main_session"

# Global connection objects (module-level state)
_conn: Optional[sqlite3.Connection] = None
_checkpointer: Optional[SqliteSaver] = None


def create_checkpoint_infrastructure(graph_builder) -> "CompiledGraph":
    """Create checkpoint infrastructure and compile the graph."""
    global _conn, _checkpointer
    try:
        migrate_legacy_runtime_artifacts(WORKSPACE_DIR)
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        _checkpointer = SqliteSaver(_conn)
        graph = graph_builder.compile(checkpointer=_checkpointer)
        log_custom("CHECKPOINT", f"Enabled SQLite persistence at {DB_PATH}")
        return graph
    except Exception as e:
        log_exception("CHECKPOINT", e, {"context": "persistence setup"})
        # Fallback to in-memory compilation if DB fails, or just return compiled graph without checkpointer?
        # The original code compiled with checkpointer. If it fails, we might want to fail hard or fallback.
        # Original code printed warning and seemingly returned None for graph (implicitly) or crashed later.
        # Here we return compiled graph without checkpointer if DB fails, which allows run but no persistence.
        return graph_builder.compile()


def delete_checkpoint():
    """Delete checkpoint and associated files."""
    global _conn
    try:
        if _conn:
            try:
                _conn.close()
            except Exception:
                pass
            _conn = None
        
        migrate_legacy_runtime_artifacts(WORKSPACE_DIR)

        # Delete sqlite files
        for path in get_checkpoint_sidecar_paths(WORKSPACE_DIR):
            if path.exists():
                try:
                    path.unlink()
                    log_custom("CHECKPOINT", f"Deleted: {path}")
                except Exception as e:
                    log_custom("CHECKPOINT", f"Warning: Could not delete {path}", {"error": str(e)})

        # Delete any legacy root-level files left behind by older versions.
        for suffix in ["", "-shm", "-wal"]:
            legacy_path = WORKSPACE_DIR / f"checkpoints.sqlite{suffix}"
            if legacy_path.exists():
                try:
                    legacy_path.unlink()
                    log_custom("CHECKPOINT", f"Deleted: {legacy_path}")
                except Exception as e:
                    log_custom("CHECKPOINT", f"Warning: Could not delete {legacy_path}", {"error": str(e)})
        
        # Delete checkpoint_settings.json
        checkpoint_settings_path = get_checkpoint_settings_path(WORKSPACE_DIR)
        if checkpoint_settings_path.exists():
            try:
                checkpoint_settings_path.unlink()
                log_custom("CHECKPOINT", f"Deleted: {checkpoint_settings_path}")
            except Exception as e:
                log_custom("CHECKPOINT", f"Warning: Could not delete {checkpoint_settings_path}", {"error": str(e)})

        legacy_settings_path = WORKSPACE_DIR / "checkpoint_settings.json"
        if legacy_settings_path.exists():
            try:
                legacy_settings_path.unlink()
                log_custom("CHECKPOINT", f"Deleted: {legacy_settings_path}")
            except Exception as e:
                log_custom("CHECKPOINT", f"Warning: Could not delete {legacy_settings_path}", {"error": str(e)})

        pending_execution_path = get_pending_execution_path(WORKSPACE_DIR)
        if pending_execution_path.exists():
            try:
                pending_execution_path.unlink()
                log_custom("CHECKPOINT", f"Deleted: {pending_execution_path}")
            except Exception as e:
                log_custom("CHECKPOINT", f"Warning: Could not delete {pending_execution_path}", {"error": str(e)})

        legacy_pending_execution_path = WORKSPACE_DIR / "pending_execution.json"
        if legacy_pending_execution_path.exists():
            try:
                legacy_pending_execution_path.unlink()
                log_custom("CHECKPOINT", f"Deleted: {legacy_pending_execution_path}")
            except Exception as e:
                log_custom("CHECKPOINT", f"Warning: Could not delete {legacy_pending_execution_path}", {"error": str(e)})
                
    except Exception as e:
        log_exception("CHECKPOINT", e, {"context": "deleting checkpoint"})


def release_checkpoint_resources():
    """Close the SQLite connection and drop saver handles (e.g. before rebuilding the graph)."""
    global _conn, _checkpointer
    if _conn is not None:
        try:
            _conn.close()
        except Exception:
            pass
    _conn = None
    _checkpointer = None


def is_connection_valid():
    """Check if database connection is valid."""
    if _conn is None:
        return False
    try:
        _conn.execute("SELECT 1").fetchone()
        return True
    except (sqlite3.ProgrammingError, sqlite3.OperationalError, AttributeError):
        return False


def checkpoint_file_exists():
    """Check if checkpoint file exists."""
    migrate_legacy_runtime_artifacts(WORKSPACE_DIR)
    return DB_PATH.exists()


class _CheckpointInspectionLLM:
    """Minimal LLM shim for compiling the graph while reading checkpoint state."""

    def invoke(self, *args, **kwargs):
        return None

    def bind_tools(self, *args, **kwargs):
        return self


def checkpoint_is_strategist_stage():
    """Return True when the active checkpoint is still in strategist planning."""
    if not checkpoint_file_exists():
        return False

    try:
        from .graph import build_graph
        from .resume_steering import checkpoint_is_strategist_stage as is_strategist_stage

        graph_builder = build_graph(_CheckpointInspectionLLM())
        graph = create_checkpoint_infrastructure(graph_builder)
        state = graph.get_state(get_thread_config())
        next_nodes = list(getattr(state, "next", ()) or []) if state else []
        state_values = state.values if state else {}
        return is_strategist_stage(next_nodes, state_values)
    except Exception as e:
        log_custom("CHECKPOINT", "Could not inspect checkpoint stage", {"error": str(e)})
        return False
    finally:
        release_checkpoint_resources()


def has_checkpoint_history(graph: "CompiledGraph", config: dict):
    """Check if checkpoint has existing history."""
    if graph is None:
        return False
    try:
        # Check if state exists
        return bool(graph.get_state(config).values)
    except Exception:
        return False


def get_thread_config():
    """Get the standard configuration for the thread."""
    return {"configurable": {"thread_id": THREAD_ID}, "recursion_limit": 1000}
