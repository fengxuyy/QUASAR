import pytest
import os
import tempfile
from pathlib import Path
from unittest.mock import patch
from src.tools.execution import execute_python

def test_temp_file_leak_on_error(mock_workspace):
    """
    Audit if temp files leak when execution crashes or errors.
    """
    # We need to spy on tempfile.mkstemp to know what file was created
    real_mkstemp = tempfile.mkstemp
    created_temp_files = []
    
    def spy_mkstemp(*args, **kwargs):
        fd, path = real_mkstemp(*args, **kwargs)
        created_temp_files.append(Path(path))
        return fd, path
        
    with patch('src.tools.execution.WORKSPACE_DIR', mock_workspace):
        with patch('tempfile.mkstemp', side_effect=spy_mkstemp):
            # Execute code that raises an exception (e.g. invalid syntax or runtime error)
            # Note: execute_python catches exceptions, but we want to ensure cleanup happens IN that catch block.
            
            # 1. Error case
            execute_python.invoke({"code": "raise ValueError('Crash!')"})
            
            # Check if temp file was cleaned up
            assert len(created_temp_files) > 0
            for temp_path in created_temp_files:
                assert not temp_path.exists(), f"Temp file leaked: {temp_path}"

def test_temp_file_leak_standard_execution(mock_workspace):
    """
    Audit if temp files leak during normal execution.
    """
    real_mkstemp = tempfile.mkstemp
    created_temp_files = []
    
    def spy_mkstemp(*args, **kwargs):
        fd, path = real_mkstemp(*args, **kwargs)
        created_temp_files.append(Path(path))
        return fd, path
        
    with patch('src.tools.execution.WORKSPACE_DIR', mock_workspace):
         with patch('tempfile.mkstemp', side_effect=spy_mkstemp):
            execute_python.invoke({"code": "print('ok')"})
            
            assert len(created_temp_files) > 0
            for temp_path in created_temp_files:
                assert not temp_path.exists(), f"Temp file leaked: {temp_path}"
