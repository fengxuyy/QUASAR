import pytest
from pathlib import Path
from unittest.mock import patch
from src.tools.base import _validate_workspace_path, truncate_content, MAX_OUTPUT_CHARS

def test_validate_workspace_path(mock_workspace):
    """Test path validation logic."""
    # Valid path
    valid_path = mock_workspace / "valid.txt"
    assert _validate_workspace_path(valid_path) is None
    
    # Path traversal attempt (resolves to outside)
    # Note: _validate_workspace_path checks if str(path).startswith(str(WORKSPACE_DIR))
    # We need to construct a path object that resolves to outside
    
    # Use explicit paths to avoid filesystem resolution ambiguity (symlinks, /var vs /private/var)
    from unittest.mock import patch
    
    # We patch the WORKSPACE_DIR used by the function (imported from src.tools.base)
    # Since we imported _validate_workspace_path from src.tools.base, it uses src.tools.base.WORKSPACE_DIR
    
    fake_workspace = Path("/users/test/workspace")
    fake_outside = Path("/users/test/other/file.txt")
    
    with patch('src.tools.base.WORKSPACE_DIR', fake_workspace):
        # We need to ensure resolve() doesn't change these theoretical paths to something else on real disk
        # or we just rely on string comparison logic if path doesn't exist.
        # But _validate_workspace_path calls .resolve().
        # So we should mock resolve too or use real path structure if possible.
        # Actually simplest is to ensure the paths don't exist so resolve strict=False (default) keeps them mostly as is,
        # OR just rely on the fact that /users/test/workspace doesn't exist so it resolves to itself.
        
        result = _validate_workspace_path(fake_outside)
        assert result is not None
        assert "outside" in result

def test_truncate_content():
    """Test content truncation."""
    # Small content
    assert truncate_content("hello") == "hello"
    
    # Large content
    limit = 10
    large = "a" * 20
    truncated = truncate_content(large, max_length=limit)
    assert len(truncated) <= limit + 100 # + overhead for message
    assert "truncated" in truncated
    
    # Exact limit (fuzzy)
    # truncate_content logic: if len > max_length: return content[:max_length] + msg
    
    res = truncate_content("1234567890", max_length=5)
    assert res.startswith("12345")
    assert "truncated" in res


# Additional rigorous tests below

def test_is_multimodal_model():
    """Test multimodal model detection."""
    from src.tools.base import _is_multimodal_model
    
    # Known multimodal models
    assert _is_multimodal_model("gemini-2.5-pro") is True
    assert _is_multimodal_model("gpt-4o") is True
    assert _is_multimodal_model("claude-sonnet-4-5-20250929") is True
    assert _is_multimodal_model("grok-4-0709") is True
    
    # Non-multimodal models
    assert _is_multimodal_model("gpt-3.5-turbo") is False
    assert _is_multimodal_model("llama-3-70b") is False
    assert _is_multimodal_model("") is False


def test_find_line_based_matches():
    """Test line-based matching logic (indentation agnostic)."""
    from src.tools.base import _find_line_based_matches
    
    content = """def hello():
    print('world')
    return True

def goodbye():
    print('end')"""
    
    # Find a simple pattern
    old_string = "print('world')\n    return True"
    matches = _find_line_based_matches(old_string, content)
    assert len(matches) >= 1
    
    # Non-matching pattern
    old_string = "print('missing')"
    matches = _find_line_based_matches(old_string, content)
    assert len(matches) == 0
    
    # Empty pattern
    matches = _find_line_based_matches("", content)
    assert len(matches) == 0


def test_find_token_based_matches():
    """Test token-based matching logic (whitespace agnostic)."""
    from src.tools.base import _find_token_based_matches
    
    content = "def hello ( x , y ) :\n    return x + y"
    
    # Find with different whitespace
    old_string = "hello(x, y)"
    matches = _find_token_based_matches(old_string, content)
    assert len(matches) >= 1
    
    # Empty pattern
    matches = _find_token_based_matches("", content)
    assert len(matches) == 0


def test_format_file_list_empty():
    """Test format_file_list with empty list."""
    from src.tools.base import format_file_list
    
    result = format_file_list([])
    assert result == ""


def test_format_file_list_simple():
    """Test format_file_list with simple file list."""
    from src.tools.base import format_file_list
    
    files = ["file1.txt", "file2.py", "dir/file3.md"]
    result = format_file_list(files)
    
    assert "file1.txt" in result
    assert "file2.py" in result
    assert "file3.md" in result


def test_format_file_list_collapse_ranges():
    """Test format_file_list collapsing numbered sequences."""
    from src.tools.base import format_file_list
    
    # Create many numbered files
    files = [f"output_{i}.dat" for i in range(1, 25)]
    result = format_file_list(files, max_files_per_dir=10)
    
    # Should collapse the range
    assert "files" in result.lower()  # Should mention number of files


def test_get_all_files(mock_workspace):
    """Test get_all_files recursive listing."""
    from src.tools.base import get_all_files
    import os
    
    # Create some files
    (mock_workspace / "test1.txt").touch()
    (mock_workspace / "test2.py").touch()
    
    # Create subdirectory with files
    subdir = mock_workspace / "subdir"
    subdir.mkdir()
    (subdir / "nested.txt").touch()
    
    # Create __pycache__ that should be ignored
    pycache = mock_workspace / "__pycache__"
    pycache.mkdir()
    (pycache / "cached.pyc").touch()
    
    with patch('src.tools.base.WORKSPACE_DIR', mock_workspace):
        files = get_all_files(mock_workspace)
    
    # Should find regular files
    assert "test1.txt" in files
    assert "test2.py" in files
    assert "subdir/nested.txt" in files
    
    # Should not include __pycache__ files
    assert not any("__pycache__" in f for f in files)


def test_find_number_ranges():
    """Test _find_number_ranges helper."""
    from src.tools.base import _find_number_ranges
    
    # Consecutive numbers
    result = _find_number_ranges([1, 2, 3, 4, 5])
    assert result == [(1, 5)]
    
    # Gaps
    result = _find_number_ranges([1, 2, 5, 6, 7, 10])
    assert result == [(1, 2), (5, 7), (10, 10)]
    
    # Single number
    result = _find_number_ranges([5])
    assert result == [(5, 5)]
    
    # Empty
    result = _find_number_ranges([])
    assert result == []

