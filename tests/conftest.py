import sys
import importlib.util
from unittest.mock import MagicMock

# Mock broken/heavy dependencies to avoid import errors during test collection
# This is necessary because the environment has version conflicts (numpy/transformers)
# and we want to unit test component logic that shouldn't depend on them.
def mock_modules():
    modules = [
        'transformers', 
        'transformers.utils', 
        'transformers.utils.versions',
        'langchain_huggingface',
        'langchain_openai',
        'langchain_openai.chat_models',
        'langchain_openai.chat_models.azure'
    ]
    for mod in modules:
        if mod not in sys.modules:
            sys.modules[mod] = MagicMock()

    if 'numpy' not in sys.modules and importlib.util.find_spec('numpy') is None:
        sys.modules['numpy'] = MagicMock()

mock_modules()

import pytest
import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch
import src.revert  # Explicitly import to ensure patch works

@pytest.fixture
def mock_workspace():
    """Create a temporary workspace directory for testing."""
    # Create a temporary directory
    temp_dir = tempfile.mkdtemp()
    workspace_path = Path(temp_dir).resolve()
    logs_path = workspace_path / "quasar_logs"
    logs_path.mkdir(parents=True, exist_ok=True)
    
    # Patch WORKSPACE_DIR in the tools modules
    # We need to patch it in both base and where it's imported
    # Patch WORKSPACE_DIR in the tools modules and checkpoint module
    # We need to patch it in both base and where it's imported
    # Also patch DB_PATH in src.checkpoint because it's computed at import time
    db_path = logs_path / "checkpoints.sqlite"
    
    # Check if src.revert exists and has DB_PATH, patch it if so. 
    # Since we can't conditionally patch in the decorator easily without logic, 
    # we'll assume it might be there or we add it to the list if we are sure.
    # To be safe and robust against import styles, we can patch wherever we suspect it's used.
    # But verifying source first.
    
    with patch('src.tools.base.WORKSPACE_DIR', workspace_path), \
         patch('src.tools.base.LOGS_DIR', logs_path), \
         patch('src.tools.filesystem.WORKSPACE_DIR', workspace_path), \
         patch('src.tools.execution.WORKSPACE_DIR', workspace_path), \
         patch('src.revert.WORKSPACE_DIR', workspace_path), \
         patch('src.revert.LOGS_DIR', logs_path), \
         patch('src.checkpoint.WORKSPACE_DIR', workspace_path), \
         patch('src.checkpoint.DB_PATH', db_path), \
         patch('src.revert.DB_PATH', db_path), \
         patch('src.pending_execution.WORKSPACE_DIR', workspace_path), \
         patch('src.pending_execution.PENDING_EXECUTION_FILE', logs_path / "pending_execution.json"):
        
        yield workspace_path
        
    # Cleanup after test
    shutil.rmtree(temp_dir)
