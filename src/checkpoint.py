"""Checkpoint infrastructure for state persistence."""

import sqlite3
from typing import Optional, TYPE_CHECKING

from langgraph.checkpoint.sqlite import SqliteSaver

from .tools.base import WORKSPACE_DIR, LOGS_DIR
from .debug_logger import log_custom, log_exception

if TYPE_CHECKING:  # Only import for type checkers to avoid runtime dependency issues
    from langgraph.graph import CompiledGraph

# Path configuration
DB_PATH = WORKSPACE_DIR / "checkpoints.sqlite"
THREAD_ID = "main_session"

# Global connection objects (module-level state)
_conn: Optional[sqlite3.Connection] = None
_checkpointer: Optional[SqliteSaver] = None


def create_checkpoint_infrastructure(graph_builder) -> "CompiledGraph":
    """Create checkpoint infrastructure and compile the graph."""
    global _conn, _checkpointer
    try:
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
    """Delete checkpoint and associated files (logs, sqlite sidecars, checkpoint_settings.json)."""
    global _conn
    try:
        if _conn:
            try:
                _conn.close()
            except Exception:
                pass
            _conn = None
        
        # Delete sqlite files
        for suffix in ["", "-shm", "-wal"]:
            path = WORKSPACE_DIR / f"checkpoints.sqlite{suffix}"
            if path.exists():
                try:
                    path.unlink()
                    log_custom("CHECKPOINT", f"Deleted: {path}")
                except Exception as e:
                    log_custom("CHECKPOINT", f"Warning: Could not delete {path}", {"error": str(e)})
        
        # Delete checkpoint_settings.json
        checkpoint_settings_path = WORKSPACE_DIR / "checkpoint_settings.json"
        if checkpoint_settings_path.exists():
            try:
                checkpoint_settings_path.unlink()
                log_custom("CHECKPOINT", f"Deleted: {checkpoint_settings_path}")
            except Exception as e:
                log_custom("CHECKPOINT", f"Warning: Could not delete {checkpoint_settings_path}", {"error": str(e)})
                
    except Exception as e:
        log_exception("CHECKPOINT", e, {"context": "deleting checkpoint"})


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
    return DB_PATH.exists()


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

