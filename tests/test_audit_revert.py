import pytest
import os
from unittest.mock import patch, MagicMock
from src.revert import delete_task_folders

def test_zombie_task_folders(mock_workspace):
    """
    detects 'zombie' folders that persist after a revert.
    
    Scenario:
    - Previous run went up to Task 20.
    - We revert to Task 2.
    - The current plan (in state) only has 5 tasks.
    - The delete_task_folders function takes (target=2, total=5).
    - Expected: ALL task folders >= 2 should be deleted, even task_20.
    - Current Logic (Auditing): Likely only deletes 2 to (5+10)=15. Task 20 remains.
    """
    # Setup: Create task folders 1 to 20
    for i in range(1, 21):
        (mock_workspace / f"task_{i}").mkdir()
        
    # Verify setup
    assert (mock_workspace / "task_20").exists()
    
    # Action: Revert to Task 2. 
    # Assume the new plan has 5 tasks.
    with patch('src.revert.WORKSPACE_DIR', mock_workspace):
        # We expect this to delete EVERYTHING from task_2 upwards.
        delete_task_folders(target_task=2, total_tasks=5)
        
    # Check for zombies
    # task_1 should stay
    assert (mock_workspace / "task_1").exists()
    
    # task_2 to task_5 should be gone (covered by standard logic)
    assert not (mock_workspace / "task_2").exists()
    assert not (mock_workspace / "task_5").exists()
    
    # ZOMBIE CHECK: task_20 should be gone too!
    # If the logic limits to total_tasks + buffer, this assertion will FAIL if the buffer isn't big enough.
    assert not (mock_workspace / "task_20").exists(), "Found zombie folder task_20!"
