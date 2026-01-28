"""
Revert utility for checkpoint time-travel.

This module provides functionality to revert the checkpoint to a specific task,
deleting files created after that task started.
"""

import os
import shutil
from pathlib import Path
from typing import Optional, Tuple, List

from .checkpoint import DB_PATH, THREAD_ID, create_checkpoint_infrastructure, get_thread_config
from .graph import build_graph
from .tools.base import WORKSPACE_DIR, LOGS_DIR
from .debug_logger import log_custom, log_exception


# System files that should never be deleted during revert
PROTECTED_FILES = {
    'checkpoints.sqlite',
    'checkpoints.sqlite-shm',
    'checkpoints.sqlite-wal',
    'checkpoint_settings.json',
    'pending_execution.json',
    '.rag_index',
    'docs',
    'archive',
    'logs',
}


def delete_checkpoints_after(target_checkpoint_id: str) -> int:
    """
    Delete all checkpoints from the SQLite database that were created after the target checkpoint.
    
    This is necessary to ensure the system resumes from the target checkpoint,
    since langgraph always loads the latest checkpoint.
    
    Args:
        target_checkpoint_id: The checkpoint_id to keep (and delete all after)
        
    Returns:
        Number of checkpoints deleted
    """
    import sqlite3
    
    try:
        conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        cursor = conn.cursor()
        
        # Get the target checkpoint's row ID to know which ones came after
        # The checkpoint_id is a UUID that contains a timestamp component
        # We can compare them lexicographically since UUIDs with embedded timestamps sort correctly
        
        # First, get all checkpoint_ids for our thread
        cursor.execute("""
            SELECT checkpoint_id FROM checkpoints 
            WHERE thread_id = ? AND checkpoint_ns = ''
            ORDER BY checkpoint_id DESC
        """, (THREAD_ID,))
        
        all_checkpoints = [row[0] for row in cursor.fetchall()]
        
        log_custom("REVERT", f"Found {len(all_checkpoints)} checkpoints for thread")
        
        # Find the index of our target checkpoint
        try:
            target_index = all_checkpoints.index(target_checkpoint_id)
        except ValueError:
            log_custom("REVERT", f"Target checkpoint {target_checkpoint_id} not found in list")
            conn.close()
            return 0
        
        # All checkpoints before target_index (since list is sorted DESC, these are newer)
        checkpoints_to_delete = all_checkpoints[:target_index]
        
        if not checkpoints_to_delete:
            log_custom("REVERT", "No checkpoints to delete (target is already the latest)")
            conn.close()
            return 0
        
        log_custom("REVERT", f"Deleting {len(checkpoints_to_delete)} checkpoints newer than target")
        
        # Delete from checkpoints table
        placeholders = ','.join(['?' for _ in checkpoints_to_delete])
        cursor.execute(f"""
            DELETE FROM checkpoints 
            WHERE thread_id = ? AND checkpoint_id IN ({placeholders})
        """, (THREAD_ID, *checkpoints_to_delete))
        
        deleted_from_checkpoints = cursor.rowcount
        
        # Delete writes for the checkpoints we're deleting
        try:
            cursor.execute(f"""
                DELETE FROM writes 
                WHERE thread_id = ? AND checkpoint_id IN ({placeholders})
            """, (THREAD_ID, *checkpoints_to_delete))
            deleted_from_writes = cursor.rowcount
            log_custom("REVERT", f"Deleted {deleted_from_writes} rows from writes (deleted checkpoints)")
        except sqlite3.OperationalError:
            # Table might not exist
            pass
        
        # ALSO delete pending writes for the TARGET checkpoint itself
        # This is critical because langgraph stores pending writes that get replayed when loading a checkpoint
        # If we don't delete these, the state will include extra actions that were scheduled but shouldn't be there
        try:
            cursor.execute("""
                DELETE FROM writes 
                WHERE thread_id = ? AND checkpoint_id = ?
            """, (THREAD_ID, target_checkpoint_id))
            deleted_target_writes = cursor.rowcount
            log_custom("REVERT", f"Deleted {deleted_target_writes} pending writes from target checkpoint")
        except sqlite3.OperationalError:
            pass
        
        # Also delete from checkpoint_blobs table if it exists
        try:
            cursor.execute(f"""
                DELETE FROM checkpoint_blobs 
                WHERE thread_id = ? AND checkpoint_id IN ({placeholders})
            """, (THREAD_ID, *checkpoints_to_delete))
            deleted_from_blobs = cursor.rowcount
            log_custom("REVERT", f"Deleted {deleted_from_blobs} rows from checkpoint_blobs")
        except sqlite3.OperationalError:
            # Table might not exist
            pass
        
        conn.commit()
        
        # Force a WAL checkpoint to ensure changes are persisted to the main database file
        # This is critical because SQLite WAL mode may keep changes in the -wal file,
        # and subsequent connections might not see the deletes without a checkpoint
        try:
            cursor.execute("PRAGMA wal_checkpoint(FULL)")
            log_custom("REVERT", "WAL checkpoint completed")
        except sqlite3.OperationalError as e:
            log_custom("REVERT", f"WAL checkpoint failed (non-fatal): {e}")
        
        # Verify the deletion worked by checking what's now the latest checkpoint
        cursor.execute("""
            SELECT checkpoint_id FROM checkpoints 
            WHERE thread_id = ? AND checkpoint_ns = ''
            ORDER BY checkpoint_id DESC LIMIT 1
        """, (THREAD_ID,))
        result = cursor.fetchone()
        if result:
            latest_after_delete = result[0]
            if latest_after_delete == target_checkpoint_id:
                log_custom("REVERT", f"Verified: target checkpoint is now the latest")
            else:
                log_custom("REVERT", f"WARNING: Latest checkpoint is {latest_after_delete}, expected {target_checkpoint_id}")
        else:
            log_custom("REVERT", "WARNING: No checkpoints remain after delete")
        
        conn.close()
        
        log_custom("REVERT", f"Successfully deleted {deleted_from_checkpoints} checkpoints")
        return deleted_from_checkpoints
        
    except Exception as e:
        log_exception("REVERT", e, {"context": "delete_checkpoints_after"})
        return 0


def get_files_at_checkpoint(graph, checkpoint_id: str) -> Tuple[List[str], dict]:
    """
    Get the list of files that existed at a specific checkpoint.
    
    Args:
        graph: The compiled langgraph
        checkpoint_id: The checkpoint_id to query
        
    Returns:
        Tuple of (files_at_task_start list, state_values dict)
    """
    config = get_thread_config()
    # Must include checkpoint_ns (empty string for main thread) when accessing specific checkpoint
    config['configurable']['checkpoint_id'] = checkpoint_id
    config['configurable']['checkpoint_ns'] = ''
    
    try:
        state = graph.get_state(config)
        if state and state.values:
            return state.values.get('files_at_task_start', []), state.values
    except Exception as e:
        log_exception("REVERT", e, {"context": "get_files_at_checkpoint"})
    
    return [], {}


def find_checkpoint_for_task(graph, target_task: int) -> Tuple[Optional[str], Optional[str]]:
    """
    Find the checkpoint_id corresponding to the START of a specific task.
    
    The checkpoint we want is the EARLIEST one where:
    - len(completed_steps) == target_task - 1 (previous tasks completed)
    - A plan exists (not before planning)
    - The operator is about to start or just started (next includes 'operator' or similar)
    
    This is the checkpoint where the operator is beginning work on this task.
    
    Args:
        graph: The compiled langgraph
        target_task: The task number to revert to (1-indexed)
        
    Returns:
        Tuple of (checkpoint_id string or None, error message or None)
    """
    config = get_thread_config()
    
    try:
        # Get all state history (most recent first)
        history = list(graph.get_state_history(config))
        
        log_custom("REVERT", f"Found {len(history)} checkpoints in history")
        
        if len(history) == 0:
            return None, "No checkpoints found in history"
        
        # Get max completed_steps to know what tasks have been reached
        max_completed = max(
            len(s.values.get('completed_steps', [])) 
            for s in history if s.values
        )
        
        # For task N, we need completed_steps == N-1
        # If max_completed < target_task - 1, this task hasn't started yet
        target_completed = target_task - 1
        
        if target_completed > max_completed:
            return None, f"Task {target_task} hasn't started yet. Currently at Task {max_completed + 1}"
        
        # Find the EARLIEST checkpoint for this task where:
        # 1. completed_steps == target_completed
        # 2. A plan exists (we're not before planning)
        # 3. The operator node is in the 'next' tuple (operator is about to work)
        #
        # History is sorted newest-first, so iterate in reverse to find the oldest matching checkpoint
        matching_checkpoint = None
        for snapshot in reversed(history):
            if not snapshot.values:
                continue
                
            completed_steps = snapshot.values.get('completed_steps', [])
            plan = snapshot.values.get('plan', [])
            next_nodes = snapshot.next or ()
            
            # Must have correct completed_steps count
            if len(completed_steps) != target_completed:
                continue
            
            # Must have a plan
            if not plan:
                continue
            
            # Prefer checkpoints where operator is about to start (in 'next')
            # This catches the checkpoint right before operator began working
            next_str = str(next_nodes).lower()
            if 'operator' in next_str:
                matching_checkpoint = snapshot
                break  # Found the earliest operator checkpoint for this task
        
        # If no operator checkpoint found, fall back to any checkpoint with plan
        if not matching_checkpoint:
            for snapshot in reversed(history):
                if not snapshot.values:
                    continue
                    
                completed_steps = snapshot.values.get('completed_steps', [])
                plan = snapshot.values.get('plan', [])
                
                if len(completed_steps) == target_completed and plan:
                    matching_checkpoint = snapshot
                    break
        
        if matching_checkpoint:
            checkpoint_id = matching_checkpoint.config.get('configurable', {}).get('checkpoint_id')
            plan = matching_checkpoint.values.get('plan', [])
            messages = len(matching_checkpoint.values.get('messages', []))
            next_nodes = matching_checkpoint.next
            log_custom("REVERT", f"Found EARLIEST checkpoint for task {target_task}", {
                "checkpoint_id": checkpoint_id,
                "completed_steps": target_completed,
                "plan_length": len(plan),
                "messages": messages,
                "next": str(next_nodes)
            })
            return checkpoint_id, None
        
        log_custom("REVERT", f"No checkpoint found for task {target_task}")
        return None, f"Could not find checkpoint for task {target_task}"
        
    except Exception as e:
        log_exception("REVERT", e, {"context": "find_checkpoint_for_task"})
        return None, str(e)



def delete_task_folders(target_task: int, total_tasks: int) -> List[str]:
    """
    Delete task folders for tasks >= target_task.
    
    This is a simpler and more reliable approach than tracking files_at_task_start,
    since task work is organized in task_N folders.
    
    Args:
        target_task: The task number to revert to (1-indexed). 
                     Folders task_N where N >= target_task will be deleted.
        total_tasks: Total number of tasks in the plan
        
    Returns:
        List of deleted folder names
    """
    import shutil
    deleted_folders = []
    
    # Delete task_N folders where N >= target_task
    # Instead of relying on a guess range, we should check what actually exists on disk
    # This catches "zombie folders" from previous longer runs
    
    # List all directories in workspace
    try:
        all_items = [d for d in WORKSPACE_DIR.iterdir() if d.is_dir()]
        task_folders = []
        for d in all_items:
            if d.name.startswith("task_") and d.name[5:].isdigit():
                task_num = int(d.name[5:])
                if task_num >= target_task:
                    task_folders.append((task_num, d.name))
        
        # Sort checks just in case order matters for logging
        task_folders.sort()
        
        for task_num, folder_name in task_folders:
            folder_path = WORKSPACE_DIR / folder_name
        
            if folder_path.exists() and folder_path.is_dir():
                try:
                    shutil.rmtree(folder_path)
                    deleted_folders.append(folder_name)
                    log_custom("REVERT", f"Deleted folder: {folder_name}")
                except Exception as e:
                    log_custom("REVERT", f"Failed to delete {folder_name}: {e}")
    except Exception:
        # Fallback if listing directory fails
        pass

    # Also clean up any run-related files at workspace root that might have been created
    # during task execution (but preserve docs, archive, logs, etc.)
    cleanup_patterns = [
        # Common output files that might be at workspace root
        'execution_log.md',
        'summary.md', 
    ]
    
    for pattern in cleanup_patterns:
        file_path = WORKSPACE_DIR / pattern
        if file_path.exists() and file_path.is_file():
            # Only delete if it was created after the run started
            # For safety, we skip this for now
            pass
    
    return deleted_folders


def delete_files_created_after_task(files_at_task_start: List[str]) -> List[str]:
    """
    DEPRECATED: This function is kept for compatibility but is not reliable.
    Use delete_task_folders instead.
    
    Delete files that were created after the task started.
    
    Args:
        files_at_task_start: List of file paths that existed when the task started
        
    Returns:
        List of deleted file paths
    """
    # This approach is unreliable because files_at_task_start is not being 
    # properly updated between tasks. Just return empty list.
    log_custom("REVERT", "delete_files_created_after_task is deprecated, use delete_task_folders")
    return []



def revert_to_task(target_task: int) -> dict:
    """
    Revert the checkpoint and workspace to the start of a specific task.
    
    This function:
    1. Finds the checkpoint at the start of the target task
    2. Deletes files created after that checkpoint
    3. Updates the graph state to that checkpoint
    
    Args:
        target_task: The task number to revert to (1-indexed)
        
    Returns:
        dict with success status and details
    """
    try:
        log_custom("REVERT", f"Starting revert to task {target_task}")
        
        # Create a minimal LLM for graph building
        class FakeLLM:
            def invoke(self, *args, **kwargs): return None
            def bind_tools(self, *args, **kwargs): return self
        
        llm = FakeLLM()
        graph_builder = build_graph(llm)
        graph = create_checkpoint_infrastructure(graph_builder)
        
        # Find the target checkpoint
        checkpoint_id, error_msg = find_checkpoint_for_task(graph, target_task)
        if not checkpoint_id:
            return {
                "success": False,
                "error": error_msg or f"Could not find checkpoint for task {target_task}"
            }
        
        # Get state at that checkpoint to know total tasks
        files_at_start, state_values = get_files_at_checkpoint(graph, checkpoint_id)
        total_tasks = len(state_values.get('plan', []))
        
        log_custom("REVERT", f"Reverting to task {target_task} of {total_tasks}")
        
        # Delete task folders for tasks >= target_task
        # This is more reliable than tracking files_at_task_start
        deleted_folders = delete_task_folders(target_task, total_tasks)
        
        log_custom("REVERT", f"Deleted {len(deleted_folders)} task folders: {deleted_folders}")
        
        # Delete all checkpoints after the target checkpoint from the SQLite database
        # This ensures the system resumes from the target checkpoint
        log_custom("REVERT", f"About to delete checkpoints after: {checkpoint_id}")
        deleted_checkpoints = delete_checkpoints_after(checkpoint_id)
        
        log_custom("REVERT", f"Deleted {deleted_checkpoints} checkpoints after target")
        
        return {
            "success": True,
            "target_task": target_task,
            "checkpoint_id": checkpoint_id,
            "deleted_folders": deleted_folders,
            "deleted_checkpoints": deleted_checkpoints,
            "total_tasks": total_tasks
        }
        
    except Exception as e:
        log_exception("REVERT", e, {"context": "revert_to_task", "target_task": target_task})
        return {
            "success": False,
            "error": str(e)
        }


def get_revert_info() -> dict:
    """
    Get information about available revert points.
    
    Returns:
        dict with task info and available revert points
    """
    try:
        # Create a minimal LLM for graph building
        class FakeLLM:
            def invoke(self, *args, **kwargs): return None
            def bind_tools(self, *args, **kwargs): return self
        
        llm = FakeLLM()
        graph_builder = build_graph(llm)
        graph = create_checkpoint_infrastructure(graph_builder)
        
        config = get_thread_config()
        state = graph.get_state(config)
        
        if not state or not state.values:
            return {"available": False, "reason": "No checkpoint state found"}
        
        plan = state.values.get('plan', [])
        completed_steps = state.values.get('completed_steps', [])
        
        # Get history to find available revert points
        history = list(graph.get_state_history(config))
        
        revert_points = []
        seen_tasks = set()
        
        for snapshot in history:
            if snapshot.values:
                num_completed = len(snapshot.values.get('completed_steps', []))
                task_num = num_completed + 1
                
                if task_num not in seen_tasks and task_num <= len(plan):
                    seen_tasks.add(task_num)
                    checkpoint_id = snapshot.config.get('configurable', {}).get('checkpoint_id')
                    revert_points.append({
                        "task": task_num,
                        "checkpoint_id": checkpoint_id,
                        "title": plan[task_num - 1] if task_num <= len(plan) else None
                    })
        
        return {
            "available": True,
            "current_task": len(completed_steps) + 1,
            "total_tasks": len(plan),
            "revert_points": sorted(revert_points, key=lambda x: x["task"])
        }
        
    except Exception as e:
        log_exception("REVERT", e, {"context": "get_revert_info"})
        return {"available": False, "error": str(e)}


if __name__ == "__main__":
    # CLI test
    import sys
    import json
    
    if len(sys.argv) > 1:
        task = int(sys.argv[1])
        result = revert_to_task(task)
        print(json.dumps(result, indent=2))
    else:
        info = get_revert_info()
        print(json.dumps(info, indent=2))
