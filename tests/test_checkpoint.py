import pytest
import sqlite3
from unittest.mock import patch, MagicMock
from src.checkpoint import create_checkpoint_infrastructure, delete_checkpoint, is_connection_valid, checkpoint_file_exists, DB_PATH

def test_create_checkpoint_infrastructure_success(mock_workspace):
    """Test successful creation of checkpoint infra with real DB."""
    # We won't patch sqlite3.connect, so it connects to real DB file
    # We might still patch SqliteSaver if we don't want to rely on langgraph internals,
    # but verifying side effect (file creation) is good.
    
    # Let's mock SqliteSaver just to avoid needing langgraph installed perfectly in test env if we are unsure,
    # BUT user asked for rigorous tests. Let's try to let it run if possible.
    # However, to be safe and focus on our code (checkpoint.py), let's keep SqliteSaver mock but verify the CONNECTION part is real.
    
    with patch('src.checkpoint.SqliteSaver') as mock_saver:
        mock_builder = MagicMock()
        
        # Call
        import src.checkpoint
        src.checkpoint.create_checkpoint_infrastructure(mock_builder)
        
        # Verify DB file exists
        assert (mock_workspace / "checkpoints.sqlite").exists()
        
        # Verify compilation with checkpointer
        mock_builder.compile.assert_called_once()
        # Verify we got a connection object
        assert src.checkpoint._conn is not None

def test_create_checkpoint_infrastructure_fallback():
    """Test fallback when DB fails."""
    # We simulate failure by patching connect to raise
    with patch('sqlite3.connect', side_effect=Exception("DB Error")):
        mock_builder = MagicMock()
        
        # Call
        import src.checkpoint
        src.checkpoint.create_checkpoint_infrastructure(mock_builder)
        
        # Verify compilation WITHOUT checkpointer (args empty/defaults)
        mock_builder.compile.assert_called_once_with()

def test_delete_checkpoint(mock_workspace):
    """Test deletion of checkpoint files with real files."""
    # Create dummy files
    (mock_workspace / "checkpoints.sqlite").touch()
    (mock_workspace / "checkpoints.sqlite-shm").touch()
    (mock_workspace / "checkpoint_settings.json").touch()
    
    # Establish a real connection to simulate active session
    import src.checkpoint
    src.checkpoint._conn = sqlite3.connect(mock_workspace / "checkpoints.sqlite")
    
    # Call
    src.checkpoint.delete_checkpoint()
    
    # Verify files are gone
    assert not (mock_workspace / "checkpoints.sqlite").exists()
    assert not (mock_workspace / "checkpoints.sqlite-shm").exists()
    assert not (mock_workspace / "checkpoint_settings.json").exists()
    
    # Verify connection global is cleared
    assert src.checkpoint._conn is None

def test_is_connection_valid(mock_workspace):
    """Test connection validity check with real connection."""
    import src.checkpoint
    
    # Case 1: No connection
    src.checkpoint._conn = None
    assert src.checkpoint.is_connection_valid() is False
        
    # Case 2: Valid
    src.checkpoint._conn = sqlite3.connect(mock_workspace / "checkpoints.sqlite")
    assert src.checkpoint.is_connection_valid() is True
    
    # Case 3: Error (Closed connection)
    src.checkpoint._conn.close()
    # Note: sqlite3 might not fail immediately on select 1 if object exists but closed? 
    # Usually it raises ProgrammingError.
    assert src.checkpoint.is_connection_valid() is False
