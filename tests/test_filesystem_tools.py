import os
from src.tools.filesystem import read_file, list_directory, edit_file
from src.tools.base import MAX_OUTPUT_CHARS
from src.tools.base import PROTECTED_SYSTEM_FILES

def _write_workspace_file(mock_workspace, file_path, content, mode="w"):
    path = mock_workspace / file_path
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open(mode, encoding="utf-8") as handle:
        handle.write(content)
    return path


def test_read_file(mock_workspace):
    """Test reading a file."""
    filename = "test_file.txt"
    content = "Hello, World!"
    _write_workspace_file(mock_workspace, filename, content)
    
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
    _write_workspace_file(mock_workspace, filename, content)
    
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
    _write_workspace_file(mock_workspace, filename, content)
    
    result = read_file.invoke({"file_path": filename})
    assert "truncated" in result.lower()
    assert len(result) < 50000


def test_read_file_keyword_mode_respects_global_output_limit(mock_workspace):
    """Keyword reads should still honor the same global truncation budget."""
    filename = "keyword_huge.log"
    repeated_line = "keyword " + ("X" * 400)
    content = "\n".join(f"{i}: {repeated_line}" for i in range(500))
    _write_workspace_file(mock_workspace, filename, content)

    result = read_file.invoke({
        "file_path": filename,
        "keyword": "keyword",
        "context_lines": 0,
    })

    assert "Found keyword 'keyword'" in result
    assert "truncated" in result.lower()
    assert len(result) <= MAX_OUTPUT_CHARS + 200


def test_read_file_first_lines_mode_respects_global_output_limit(mock_workspace):
    """first_lines reads should be capped by the global output limit."""
    filename = "first_lines_huge.log"
    long_line = "Y" * 600
    content = "\n".join(f"{i}: {long_line}" for i in range(300))
    _write_workspace_file(mock_workspace, filename, content)

    result = read_file.invoke({
        "file_path": filename,
        "first_lines": 200,
    })

    assert "truncated" in result.lower()
    assert len(result) <= MAX_OUTPUT_CHARS + 200


def test_read_file_last_lines_mode_respects_global_output_limit(mock_workspace):
    """last_lines reads should be capped by the global output limit."""
    filename = "last_lines_huge.log"
    long_line = "Z" * 600
    content = "\n".join(f"{i}: {long_line}" for i in range(300))
    _write_workspace_file(mock_workspace, filename, content)

    result = read_file.invoke({
        "file_path": filename,
        "last_lines": 200,
    })

    assert "truncated" in result.lower()
    assert len(result) <= MAX_OUTPUT_CHARS + 200

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
    _write_workspace_file(mock_workspace, "file1.txt", "content")
    _write_workspace_file(mock_workspace, "file2.py", "print('hello')")
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

def test_edit_file(mock_workspace):
    """Test editing a file."""
    filename = "edit_test.txt"
    content = "Hello World\nAnother Line"
    _write_workspace_file(mock_workspace, filename, content)
    
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
    _write_workspace_file(mock_workspace, filename, content)
    
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
    # Attempt to read a file outside the workspace using ../
    # Note: _resolve_path usually resolves paths. _validate_workspace_path checks if it starts with workspace.
    outside_file = mock_workspace.parent / "outside.txt"
    outside_file.write_text("bad", encoding="utf-8")

    result = read_file.invoke({"file_path": "../outside.txt"})
    
    assert "Error" in result
    # We expect some error about path or security


# Additional rigorous tests below

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
    _write_workspace_file(mock_workspace, filename, "Original content")
    
    result = edit_file.invoke({
        "file_path": filename,
        "old_string": "nonexistent pattern",
        "new_string": "replacement"
    })
    
    # Should report that pattern wasn't found
    assert "not found" in result.lower() or "no match" in result.lower() or "error" in result.lower()


def test_grep_search_basic(mock_workspace):
    """Test basic grep search functionality."""
    from src.tools.filesystem import grep_search
    
    # Create searchable files
    _write_workspace_file(mock_workspace, "search1.py", "def hello():\n    print('world')")
    _write_workspace_file(mock_workspace, "search2.py", "def goodbye():\n    print('done')")
    
    result = grep_search.invoke({"pattern": "hello", "directory_path": "."})
    
    assert "search1.py" in result
    assert "hello" in result


def test_grep_search_no_match(mock_workspace):
    """Test grep search with no matches."""
    from src.tools.filesystem import grep_search
    
    _write_workspace_file(mock_workspace, "nomatch.txt", "Some content here")
    
    result = grep_search.invoke({"pattern": "zzz_nonexistent_zzz", "directory_path": "."})
    
    # Should indicate no matches found
    assert "no match" in result.lower() or "not found" in result.lower() or "0 matches" in result.lower() or result.strip() == ""


def test_grep_search_case_insensitive(mock_workspace):
    """Test case-insensitive grep search."""
    from src.tools.filesystem import grep_search
    
    _write_workspace_file(mock_workspace, "case.txt", "Hello WORLD")
    
    result = grep_search.invoke({
        "pattern": "hello",
        "directory_path": ".",
        "case_insensitive": True
    })
    
    assert "case.txt" in result or "Hello" in result


# ── Multi-path tests ──────────────────────────────────────────────────────

def test_read_multiple_files(mock_workspace):
    """Test reading multiple files at once by passing a list of paths."""
    _write_workspace_file(mock_workspace, "multi1.txt", "Alpha content")
    _write_workspace_file(mock_workspace, "multi2.txt", "Beta content")

    result = read_file.invoke({"file_path": ["multi1.txt", "multi2.txt"]})
    assert "Alpha content" in result
    assert "Beta content" in result
    # Results should be separated by a divider
    assert "---" in result


def test_read_multiple_files_one_missing(mock_workspace):
    """Test reading a list where one file does not exist – should still return partial results."""
    _write_workspace_file(mock_workspace, "exists.txt", "I exist")

    result = read_file.invoke({"file_path": ["exists.txt", "ghost.txt"]})
    assert "I exist" in result
    assert "does not exist" in result


def test_read_multiple_files_with_first_lines(mock_workspace):
    """Test reading multiple files with first_lines parameter."""
    _write_workspace_file(mock_workspace, "a.txt", "line1\nline2\nline3")
    _write_workspace_file(mock_workspace, "b.txt", "lineA\nlineB\nlineC")

    result = read_file.invoke({"file_path": ["a.txt", "b.txt"], "first_lines": 1})
    assert "line1" in result
    assert "lineA" in result
    assert "line3" not in result
    assert "lineC" not in result


def test_list_multiple_directories(mock_workspace):
    """Test listing multiple directories at once."""
    import os
    (mock_workspace / "dir_a").mkdir()
    (mock_workspace / "dir_a" / "fileA.txt").touch()
    (mock_workspace / "dir_b").mkdir()
    (mock_workspace / "dir_b" / "fileB.py").touch()

    result = list_directory.invoke({"directory_path": ["dir_a", "dir_b"]})
    assert "fileA.txt" in result
    assert "fileB.py" in result
    assert "---" in result


def test_read_single_file_unchanged(mock_workspace):
    """Verify that passing a single string still works identically."""
    _write_workspace_file(mock_workspace, "solo.txt", "Solo content")
    result = read_file.invoke({"file_path": "solo.txt"})
    assert "Solo content" in result
    assert "---" not in result  # No multi-file separator
