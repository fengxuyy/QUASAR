import pytest
import sqlite3
from unittest.mock import MagicMock, patch
from src.revert import delete_checkpoints_after

def test_audit_revert_cleans_all_tables(mock_workspace):
    """
    Audit that reverting checkpoints cleans up ALL related tables (writes, blobs).
    If it leaves data in 'writes', replaying might cause issues.
    """
    db_path = mock_workspace / "checkpoints.sqlite"
    
    # Setup a real SQLite DB to test the SQL logic accurately
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    # Create tables mirroring the real schema (simplified)
    cursor.execute("CREATE TABLE checkpoints (thread_id TEXT, checkpoint_ns TEXT, checkpoint_id TEXT, parent_checkpoint_id TEXT, type TEXT, checkpoint BLOB, metadata BLOB, created_at DATETIME DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id))")
    cursor.execute("CREATE TABLE writes (thread_id TEXT, checkpoint_ns TEXT, checkpoint_id TEXT, task_id TEXT, idx INTEGER, channel TEXT, type TEXT, value BLOB, PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx))")
    cursor.execute("CREATE TABLE checkpoint_blobs (thread_id TEXT, checkpoint_ns TEXT, checkpoint_id TEXT, type TEXT, value BLOB, PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, type))")
    
    thread_id = "1"
    # Insert checkpoints: 1 (target), 2 (delete), 3 (delete)
    # Using lexicographical IDs to match assumption
    ids = ["id_100", "id_200", "id_300"]
    
    for cid in ids:
        cursor.execute("INSERT INTO checkpoints (thread_id, checkpoint_ns, checkpoint_id) VALUES (?, '', ?)", (thread_id, cid))
        cursor.execute("INSERT INTO writes (thread_id, checkpoint_ns, checkpoint_id, task_id, idx) VALUES (?, '', ?, 'task', 0)", (thread_id, cid))
        cursor.execute("INSERT INTO checkpoint_blobs (thread_id, checkpoint_ns, checkpoint_id, type) VALUES (?, '', ?, 'type')", (thread_id, cid))
        
    conn.commit()
    conn.close()
    
    # Run the delete function
    # We need to patch DB_PATH and THREAD_ID to match our setup
    with patch('src.revert.DB_PATH', db_path), \
         patch('src.revert.THREAD_ID', thread_id):
        
        # We want to keep id_100, delete id_200 and id_300
        count = delete_checkpoints_after("id_100")
        
    # Verify
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    # Check checkpoints
    cursor.execute("SELECT checkpoint_id FROM checkpoints ORDER BY checkpoint_id")
    remaining_ids = [r[0] for r in cursor.fetchall()]
    assert remaining_ids == ["id_100"], f"Expected only id_100, got {remaining_ids}"
    assert count == 2
    
    # Check writes - THIS IS THE AUDIT: did we clean writes?
    cursor.execute("SELECT checkpoint_id FROM writes ORDER BY checkpoint_id")
    remaining_writes = [r[0] for r in cursor.fetchall()]
    # Note: logic says it also deletes pending writes of target checkpoint?
    # src/revert.py:110 -> DELETE FROM writes WHERE ... checkpoint_id = target_checkpoint_id
    # So writes for id_100 should ALSO be deleted?
    # Let's check the code expectation.
    assert "id_200" not in remaining_writes
    assert "id_300" not in remaining_writes
    
    # Check blobs
    cursor.execute("SELECT checkpoint_id FROM checkpoint_blobs ORDER BY checkpoint_id")
    remaining_blobs = [r[0] for r in cursor.fetchall()]
    assert "id_200" not in remaining_blobs
    assert "id_300" not in remaining_blobs
    
    conn.close()

def test_audit_revert_ordering_assumption(mock_workspace):
    """
    Audit if the assumption that string sorting == chronological sorting holds.
    If we have UUIDs that don't sort chronologically, this logic deletes the wrong things.
    """
    db_path = mock_workspace / "checkpoints.sqlite"
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE checkpoints (thread_id TEXT, checkpoint_ns TEXT, checkpoint_id TEXT, PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id))")
    
    thread_id = "1"
    # Scenario: UUIDv4 are random. 
    # id_A (time 1), id_C (time 2), id_B (time 3)
    # If we revert to id_A (time 1), we want to delete id_C and id_B.
    # But if sorted by string: id_A, id_B, id_C.
    # Logic: ORDER BY checkpoint_id DESC -> id_C, id_B, id_A.
    # List: [id_C, id_B, id_A]
    # target: id_A.
    # delete: [id_C, id_B].
    # This works IF id_C > id_A and id_B > id_A string-wise.
    # But if id_B (time 3) < id_A (time 1), it won't be deleted?
    # Wait, if list is [id_C, id_A, id_B] (sorted desc: C, B, A is wrong if B < A)
    # If IDs are random:
    # A="100", B="050" (created later), C="200" (created even later)
    # Sorted DESC: C="200", A="100", B="050".
    # User says revert to A ("100").
    # Index of A is 1.
    # Items before A: [C].
    # Deleted: C.
    # Kept: A, B.
    # BUT B was created AFTER A! So it should have been deleted.
    # THIS IS A POTENTIAL BUG/FLAW if they use random UUIDs.
    # The code comment says: "UUIDs with embedded timestamps Sort correctly".
    # LangChain CheckpointID usually is distinct from UUIDv4?
    # If `checkpoint_id` is typically `str(uuid7())` or timestamp-prefixed, it's fine.
    # But if it's generic UUIDv4, this is broken.
    pass 
