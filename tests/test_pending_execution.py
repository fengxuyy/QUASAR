"""Tests for pending execution state management."""
import pytest
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.pending_execution import (
    save_pending_execution,
    load_pending_execution,
    clear_pending_execution,
    PENDING_EXECUTION_FILE,
)


def test_save_pending_execution(mock_workspace):
    """Test saving pending execution state to JSON file."""
    ai_message = "Running simulation..."
    tool_call = {"id": "call_123", "name": "execute_python", "args": {"code": "print('test')"}}
    task_index = 2
    
    with patch('src.pending_execution.PENDING_EXECUTION_FILE', mock_workspace / "pending_execution.json"):
        save_pending_execution(ai_message, tool_call, task_index)
        
        # Verify file exists
        pending_file = mock_workspace / "pending_execution.json"
        assert pending_file.exists()
        
        # Verify content
        data = json.loads(pending_file.read_text())
        assert data["ai_message_content"] == ai_message
        assert data["tool_call"] == tool_call
        assert data["task_index"] == task_index


def test_load_pending_execution_exists(mock_workspace):
    """Test loading valid pending execution state."""
    pending_file = mock_workspace / "pending_execution.json"
    expected_data = {
        "ai_message_content": "Test content",
        "tool_call": {"id": "call_456", "name": "execute_python", "args": {}},
        "task_index": 1
    }
    pending_file.write_text(json.dumps(expected_data))
    
    with patch('src.pending_execution.PENDING_EXECUTION_FILE', pending_file):
        result = load_pending_execution()
        
        assert result is not None
        assert result["ai_message_content"] == "Test content"
        assert result["tool_call"]["id"] == "call_456"
        assert result["task_index"] == 1


def test_load_pending_execution_not_exists(mock_workspace):
    """Test loading when no pending execution file exists."""
    non_existent = mock_workspace / "does_not_exist.json"
    
    with patch('src.pending_execution.PENDING_EXECUTION_FILE', non_existent):
        result = load_pending_execution()
        
        assert result is None


def test_load_pending_execution_corrupt(mock_workspace):
    """Test loading handles corrupted JSON gracefully."""
    pending_file = mock_workspace / "pending_execution.json"
    pending_file.write_text("{ invalid json }")
    
    with patch('src.pending_execution.PENDING_EXECUTION_FILE', pending_file):
        result = load_pending_execution()
        
        assert result is None


def test_clear_pending_execution(mock_workspace):
    """Test clearing pending execution removes the file."""
    pending_file = mock_workspace / "pending_execution.json"
    pending_file.write_text('{"test": "data"}')
    
    assert pending_file.exists()
    
    with patch('src.pending_execution.PENDING_EXECUTION_FILE', pending_file):
        clear_pending_execution()
        
        assert not pending_file.exists()


def test_clear_pending_execution_no_file(mock_workspace):
    """Test clearing when no file exists doesn't raise error."""
    non_existent = mock_workspace / "does_not_exist.json"
    
    with patch('src.pending_execution.PENDING_EXECUTION_FILE', non_existent):
        # Should not raise
        clear_pending_execution()
