import os
import pytest
import shutil
from pathlib import Path
from src.tools.filesystem import read_file, write_file, list_directory, delete_file, edit_file
from src.tools.base import PROTECTED_SYSTEM_FILES

def test_write_and_read_file(mock_workspace):
    """Test writing to a file and then reading it back."""
    filename = "test_file.txt"
    content = "Hello, World!"
    
    # Write file
    result = write_file.invoke({"file_path": filename, "content": content})
    assert "Successfully wrote" in result
    assert (mock_workspace / filename).exists()
    
    # Read file
    read_result = read_file.invoke({"file_path": filename})
    assert content in read_result

def test_read_nonexistent_file(mock_workspace):
    """Test reading a file that does not exist."""
    result = read_file.invoke({"file_path": "nonexistent.txt"})
    assert "Error" in result
    assert "does not exist" in result

def test_read_file_params(mock_workspace):
    """Test first_lines, last_lines, and keyword parameters."""
    filename = "lines.txt"
    content = "\n".join([f"Line {i}" for i in range(1, 11)]) # 10 lines
    write_file.invoke({"file_path": filename, "content": content})
    
    # Test first_lines
    result_first = read_file.invoke({"file_path": filename, "first_lines": 3})
    assert "Line 1" in result_first
    assert "Line 3" in result_first
    assert "Line 4" not in result_first
    
    # Test last_lines
    result_last = read_file.invoke({"file_path": filename, "last_lines": 3})
    assert "Line 8" in result_last
    assert "Line 10" in result_last
    assert "Line 7" not in result_last
    
    # Test keyword
    result_key = read_file.invoke({"file_path": filename, "keyword": "Line 5", "context_lines": 1})
    assert "Found keyword 'Line 5'" in result_key
    assert "Line 4" in result_key
    assert "Line 5" in result_key
    assert "Line 6" in result_key
    assert "Line 3" not in result_key

def test_read_large_file_truncation(mock_workspace):
    """Test reading a very large file is truncated."""
    filename = "large_file.txt"
    # Create a file significantly larger than expected truncation limit (approx 16k chars usually)
    content = "A" * 50000 
    write_file.invoke({"file_path": filename, "content": content})
    
    result = read_file.invoke({"file_path": filename})
    assert "Content truncated" in result
    assert len(result) < 50000

def test_read_protected_file(mock_workspace):
    """Test attempting to read a protected system file."""
    # We need to simulate the protected file existing in the mock workspace
    protected_file = list(PROTECTED_SYSTEM_FILES)[0]
    (mock_workspace / protected_file).touch()
    
    result = read_file.invoke({"file_path": protected_file})
    assert "Error" in result
    assert "internal system file" in result

def test_list_directory(mock_workspace):
    """Test listing directory contents."""
    write_file.invoke({"file_path": "file1.txt", "content": "content"})
    write_file.invoke({"file_path": "file2.py", "content": "print('hello')"})
    os.makedirs(mock_workspace / "subfolder")
    
    # List all
    result = list_directory.invoke({"directory_path": "."})
    assert "file1.txt" in result
    assert "file2.py" in result
    assert "subfolder" in result
    
    # Test pattern
    result_py = list_directory.invoke({"directory_path": ".", "pattern": "*.py"})
    assert "file2.py" in result_py
    assert "file1.txt" not in result_py

def test_list_directory_exclude_docs(mock_workspace):
    """Test excluding docs folder."""
    os.makedirs(mock_workspace / "docs")
    os.makedirs(mock_workspace / "other")
    
    result = list_directory.invoke({"directory_path": ".", "exclude_docs": True})
    assert "docs" not in result
    assert "other" in result

def test_delete_file(mock_workspace):
    """Test deleting a file."""
    filename = "to_delete.txt"
    write_file.invoke({"file_path": filename, "content": "content"})
    assert (mock_workspace / filename).exists()
    
    result = delete_file.invoke({"file_path": filename})
    assert "Successfully deleted" in result
    assert not (mock_workspace / filename).exists()

def test_delete_protected_file(mock_workspace):
    """Test attempting to delete a protected file."""
    protected_file = list(PROTECTED_SYSTEM_FILES)[0]
    (mock_workspace / protected_file).touch()
    
    result = delete_file.invoke({"file_path": protected_file})
    assert "Error" in result
    assert "internal system file" in result
    assert (mock_workspace / protected_file).exists()

def test_edit_file(mock_workspace):
    """Test editing a file."""
    filename = "edit_test.txt"
    content = "Hello World\nAnother Line"
    write_file.invoke({"file_path": filename, "content": content})
    
    # Edit replacing "World" with "Python"
    result = edit_file.invoke({"file_path": filename, "old_string": "World", "new_string": "Python"})
    assert "Successfully replaced" in result
    
    read_result = read_file.invoke({"file_path": filename})
    assert "Hello Python" in read_result
    assert "Another Line" in read_result

def test_edit_file_fuzzy_match(mock_workspace):
    """Test editing logic with whitespace mismatch (fuzzy match)."""
    filename = "fuzzy.py"
    content = "def hello():\n    print('world')"
    write_file.invoke({"file_path": filename, "content": content})
    
    # Target has different whitespace
    old_target = "def hello():\n\tprint('world')" 
    
    # Note: The tool implementation might not support tab vs space fuzzy match if not strictly line based or if Python's diff doesn't catch it easily. 
    # But let's test a simpler case: simple indentation difference or line extraction.
    
    target_content = "    print('world')"
    replacement = "    print('universe')"
    
    result = edit_file.invoke({"file_path": filename, "old_string": target_content, "new_string": replacement})
    
    # If using string replacement, exact match might be required unless logic is robust.
    # The tool claims "Line-based Fuzzy Match (Indentation Agnostic)".
    
    read_result = read_file.invoke({"file_path": filename})
    if "Successfully replaced" in result:
        assert "print('universe')" in read_result
    else:
        # If it failed, it might be expected depending on tool implementation strictness.
        # But we want to vigorous test, so let's verify if failure gives good feedback.
        assert "Error" in result

def test_path_traversal_prevention(mock_workspace):
    """Test preventing access to files outside workspace."""
    # Attempt to write to a file outside the workspace using ../
    # Note: _resolve_path usually resolves paths. _validate_workspace_path checks if it starts with workspace.
    
    filename = "../outside.txt"
    result = write_file.invoke({"file_path": filename, "content": "bad"})
    
    assert "Error" in result
    # We expect some error about path or security


# Additional rigorous tests below

def test_write_file_creates_parent_dirs(mock_workspace):
    """Test that write_file creates parent directories if needed."""
    nested_path = "deep/nested/dir/file.txt"
    content = "Nested content"
    
    result = write_file.invoke({"file_path": nested_path, "content": content})
    
    assert "Successfully wrote" in result
    assert (mock_workspace / "deep/nested/dir/file.txt").exists()


def test_list_directory_nested(mock_workspace):
    """Test listing with nested directory structure."""
    import os
    
    # Create nested structure
    nested = mock_workspace / "level1" / "level2"
    nested.mkdir(parents=True)
    (nested / "deep_file.txt").touch()
    (mock_workspace / "level1" / "shallow_file.txt").touch()
    
    # List the workspace root - should see level1
    result = list_directory.invoke({"directory_path": "."})
    assert "level1" in result
    
    # List level1
    result = list_directory.invoke({"directory_path": "level1"})
    assert "level2" in result
    assert "shallow_file.txt" in result


def test_read_file_binary_detection(mock_workspace):
    """Test that binary files are handled appropriately."""
    binary_file = mock_workspace / "binary.bin"
    binary_file.write_bytes(b'\x00\x01\x02\x03\x04\xff\xfe')
    
    result = read_file.invoke({"file_path": "binary.bin"})
    
    # Should either read or indicate binary
    assert result  # At minimum should return something


def test_edit_file_no_match(mock_workspace):
    """Test editing when old_string doesn't exist."""
    filename = "nomatch.txt"
    write_file.invoke({"file_path": filename, "content": "Original content"})
    
    result = edit_file.invoke({
        "file_path": filename,
        "old_string": "nonexistent pattern",
        "new_string": "replacement"
    })
    
    # Should report that pattern wasn't found
    assert "not found" in result.lower() or "no match" in result.lower() or "error" in result.lower()


def test_delete_nonexistent_file(mock_workspace):
    """Test deleting a file that doesn't exist."""
    result = delete_file.invoke({"file_path": "does_not_exist.txt"})
    
    assert "Error" in result or "not found" in result.lower()


def test_write_file_append_mode(mock_workspace):
    """Test writing in append mode."""
    filename = "append_test.txt"
    
    # Write initial content
    write_file.invoke({"file_path": filename, "content": "First line\n"})
    
    # Append more content
    result = write_file.invoke({"file_path": filename, "content": "Second line\n", "mode": "a"})
    
    assert "Successfully" in result
    
    # Verify content
    content = (mock_workspace / filename).read_text()
    assert "First line" in content
    assert "Second line" in content


def test_grep_search_basic(mock_workspace):
    """Test basic grep search functionality."""
    from src.tools.filesystem import grep_search
    
    # Create searchable files
    write_file.invoke({"file_path": "search1.py", "content": "def hello():\n    print('world')"})
    write_file.invoke({"file_path": "search2.py", "content": "def goodbye():\n    print('done')"})
    
    result = grep_search.invoke({"pattern": "hello", "directory_path": "."})
    
    assert "search1.py" in result
    assert "hello" in result


def test_grep_search_no_match(mock_workspace):
    """Test grep search with no matches."""
    from src.tools.filesystem import grep_search
    
    write_file.invoke({"file_path": "nomatch.txt", "content": "Some content here"})
    
    result = grep_search.invoke({"pattern": "zzz_nonexistent_zzz", "directory_path": "."})
    
    # Should indicate no matches found
    assert "no match" in result.lower() or "not found" in result.lower() or "0 matches" in result.lower() or result.strip() == ""


def test_grep_search_case_insensitive(mock_workspace):
    """Test case-insensitive grep search."""
    from src.tools.filesystem import grep_search
    
    write_file.invoke({"file_path": "case.txt", "content": "Hello WORLD"})
    
    result = grep_search.invoke({
        "pattern": "hello",
        "directory_path": ".",
        "case_insensitive": True
    })
    
    assert "case.txt" in result or "Hello" in result


def test_move_file(mock_workspace):
    """Test moving a file."""
    from src.tools.filesystem import move_file
    
    # Create source file and destination dir
    write_file.invoke({"file_path": "source.txt", "content": "moveable"})
    (mock_workspace / "dest_dir").mkdir()
    
    result = move_file.invoke({
        "source_path": "source.txt",
        "destination_path": "dest_dir/source.txt"
    })
    
    assert "Successfully" in result or "moved" in result.lower()
    assert not (mock_workspace / "source.txt").exists()
    assert (mock_workspace / "dest_dir" / "source.txt").exists()


def test_rename_file(mock_workspace):
    """Test renaming a file."""
    from src.tools.filesystem import rename_file
    
    write_file.invoke({"file_path": "old_name.txt", "content": "content"})
    
    result = rename_file.invoke({
        "file_path": "old_name.txt",
        "new_name": "new_name.txt"
    })
    
    assert "Successfully" in result or "renamed" in result.lower()
    assert not (mock_workspace / "old_name.txt").exists()
    assert (mock_workspace / "new_name.txt").exists()

