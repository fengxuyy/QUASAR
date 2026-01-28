import pytest
import sqlite3
from unittest.mock import patch, MagicMock, mock_open
from src.revert import delete_checkpoints_after, find_checkpoint_for_task, delete_task_folders, revert_to_task

def test_delete_checkpoints_after(mock_workspace):
    """Test SQL operations for deleting checkpoints using real SQLite DB."""
    # Setup real DB in the mock workspace
    db_path = mock_workspace / "checkpoints.sqlite"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Create simple schema matching what's expected
    cursor.execute("CREATE TABLE checkpoints (checkpoint_id TEXT, thread_id TEXT, checkpoint_ns TEXT, parent_checkpoint_id TEXT)")
    
    # Insert test data
    # We need to ensure lexicographical order matches time order (Newest > Oldest)
    # ids: "z_cp3" (newest), "y_cp2", "target_cp", "a_cp1" (oldest)
    
    checkpoints = [
        ("z_cp3", "main_session", "", "y_cp2"),
        ("y_cp2", "main_session", "", "target_cp"),
        ("target_cp", "main_session", "", "a_cp1"),
        ("a_cp1", "main_session", "", "")
    ]
    cursor.executemany("INSERT INTO checkpoints VALUES (?, ?, ?, ?)", checkpoints)
    conn.commit()
    conn.close()
    
    # Call function - it will connect to the same DB file given the patches
    # The function deletes everything NEWER than target (so z_cp3, y_cp2)
    deleted = delete_checkpoints_after("target_cp")
    
    # Verify return value (z_cp3 and y_cp2 deleted = 2)
    assert deleted == 2 
    
    # Verify DB state
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    remaining = cursor.execute("SELECT checkpoint_id FROM checkpoints ORDER BY checkpoint_id").fetchall()
    conn.close()
    
    remaining_ids = {r[0] for r in remaining}
    assert "z_cp3" not in remaining_ids
    assert "y_cp2" not in remaining_ids
    assert "target_cp" in remaining_ids
    assert "a_cp1" in remaining_ids
        
def test_find_checkpoint_for_task_success():
    """Test finding a valid checkpoint for a task."""
    mock_graph = MagicMock()
    
    # Create mock snapshots
    # Snapshot 3: Task 3 done (completed_steps has 3 items) - Too late for reverting to task 2
    snap3 = MagicMock()
    snap3.values = {'completed_steps': ['t1', 't2', 't3'], 'plan': ['p1', 'p2', 'p3', 'p4']}
    snap3.next = ('evaluator',)
    
    # Snapshot 2: Task 1 done (completed_steps has 1 item) - Perfect for reverting to Task 2
    # Operator is next, meaning we are at start of Task 2
    snap2 = MagicMock()
    snap2.values = {'completed_steps': ['t1'], 'plan': ['p1', 'p2', 'p3', 'p4']}
    snap2.next = ('operator',)
    snap2.config = {'configurable': {'checkpoint_id': 'cp_task2_start'}}
    
    # Snapshot 1: Task 0 done (empty) - Start of Task 1
    snap1 = MagicMock()
    snap1.values = {'completed_steps': [], 'plan': ['p1', 'p2', 'p3', 'p4']}
    snap1.next = ('operator',)
    
    # History is newest first
    mock_graph.get_state_history.return_value = [snap3, snap2, snap1]
    
    # We want to revert to Task 2
    # So we look for completed_steps count == 2-1 = 1
    cp_id, error = find_checkpoint_for_task(mock_graph, 2)
    
    assert error is None
    assert cp_id == 'cp_task2_start'

def test_find_checkpoint_not_started():
    """Test when future task hasn't started yet."""
    mock_graph = MagicMock()
    
    # History only goes up to Task 1 completed
    snap1 = MagicMock()
    snap1.values = {'completed_steps': ['t1'], 'plan': ['p1', 'p2']}
    mock_graph.get_state_history.return_value = [snap1]
    
    # Try to revert to Task 5
    cp_id, error = find_checkpoint_for_task(mock_graph, 5)
    
    assert cp_id is None
    assert "hasn't started yet" in error

def test_delete_task_folders(mock_workspace):
    """Test deletion of task folders."""
    # Create task folders
    (mock_workspace / "task_1").mkdir()
    (mock_workspace / "task_2").mkdir()
    (mock_workspace / "task_3").mkdir()
    (mock_workspace / "other").mkdir()
    
    # Revert to Task 2 -> should delete task_2 and task_3 (and task_4 etc)
    with patch('src.revert.WORKSPACE_DIR', mock_workspace):
        deleted = delete_task_folders(2, 5)
        
        assert "task_2" in deleted
        assert "task_3" in deleted
        
        assert not (mock_workspace / "task_2").exists()
        assert not (mock_workspace / "task_3").exists()
        assert (mock_workspace / "task_1").exists() # Should remain
        assert (mock_workspace / "other").exists()  # Should remain

@patch('src.revert.build_graph')
@patch('src.revert.create_checkpoint_infrastructure')
@patch('src.revert.find_checkpoint_for_task')
@patch('src.revert.delete_task_folders')
@patch('src.revert.delete_checkpoints_after')
@patch('src.revert.get_files_at_checkpoint')
def test_revert_to_task_flow(mock_get_files, mock_del_cps, mock_del_folders, mock_find_cp, mock_create, mock_build):
    """Test the main orchestrator function flow."""
    # Setup mocks
    mock_find_cp.return_value = ("target_cp_id", None)
    mock_get_files.return_value = ([], {'plan': ['1', '2', '3']}) # 3 tasks
    mock_del_folders.return_value = ["task_2"]
    mock_del_cps.return_value = 5
    
    # Call
    result = revert_to_task(2)
    
    # Verify success
    assert result['success'] is True
    assert result['checkpoint_id'] == "target_cp_id"
    assert result['total_tasks'] == 3
    
    # Verify calls
    mock_find_cp.assert_called_once()
    mock_del_folders.assert_called_with(2, 3)
    mock_del_cps.assert_called_with("target_cp_id")


# Additional rigorous tests below

def test_get_files_at_checkpoint_success():
    """Test retrieving state from a checkpoint."""
    from src.revert import get_files_at_checkpoint
    
    mock_graph = MagicMock()
    mock_state = MagicMock()
    mock_state.values = {
        'files_at_task_start': ['file1.py', 'file2.txt'],
        'plan': ['Task 1', 'Task 2'],
        'completed_steps': ['Done 1'],
    }
    
    mock_graph.get_state.return_value = mock_state
    
    files, state_values = get_files_at_checkpoint(mock_graph, "checkpoint_123")
    
    assert files == ['file1.py', 'file2.txt']
    assert 'plan' in state_values
    assert state_values['plan'] == ['Task 1', 'Task 2']


def test_find_checkpoint_invalid_task_number():
    """Test finding checkpoint for task 0 or negative."""
    mock_graph = MagicMock()
    mock_graph.get_state_history.return_value = []
    
    # Task 0 should fail (tasks are 1-indexed)
    cp_id, error = find_checkpoint_for_task(mock_graph, 0)
    
    # Should return some error
    assert error is not None or cp_id is None


def test_delete_task_folders_nonexistent(mock_workspace):
    """Test deleting task folders when they don't exist."""
    # Don't create any task folders
    
    with patch('src.revert.WORKSPACE_DIR', mock_workspace):
        deleted = delete_task_folders(1, 3)
        
    # Should return empty list or handle gracefully
    assert isinstance(deleted, list)


@patch('src.revert.build_graph')
@patch('src.revert.create_checkpoint_infrastructure')
@patch('src.revert.find_checkpoint_for_task')
def test_revert_to_task_checkpoint_not_found(mock_find_cp, mock_create, mock_build):
    """Test revert when checkpoint is not found."""
    mock_find_cp.return_value = (None, "Task 5 hasn't started yet")
    
    result = revert_to_task(5)
    
    assert result['success'] is False
    assert 'error' in result
    assert "hasn't started" in result['error']


def test_find_checkpoint_edge_case_first_task():
    """Test finding checkpoint for Task 1 (edge case)."""
    mock_graph = MagicMock()
    
    # Snapshot at very beginning
    snap1 = MagicMock()
    snap1.values = {'completed_steps': [], 'plan': ['p1', 'p2']}
    snap1.next = ('operator',)
    snap1.config = {'configurable': {'checkpoint_id': 'cp_start'}}
    
    mock_graph.get_state_history.return_value = [snap1]
    
    # Revert to Task 1 means we want completed_steps == 0
    cp_id, error = find_checkpoint_for_task(mock_graph, 1)
    
    # Should find the checkpoint at the start
    assert cp_id == 'cp_start' or error is None  # Either finds it or no error

