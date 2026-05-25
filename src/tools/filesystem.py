import os
import base64
import difflib
import mimetypes
import re
from typing import Optional, List, Union

from langchain_core.tools import tool
from langchain_core.messages import HumanMessage

from .base import (
    WORKSPACE_DIR,
    _resolve_path,
    _validate_workspace_path,
    _is_multimodal_model,
    _find_line_based_matches,
    _find_token_based_matches,
    truncate_content,
    MAX_OUTPUT_CHARS,
    PROTECTED_SYSTEM_FILES,
)
from ..usage_tracker import extract_cache_read_tokens, record_api_call


# Maximum number of characters to return when reading an entire file at once.
# This helps avoid blowing the model's context window on very large files.
# _MAX_FULL_READ_CHARS replaced by global MAX_OUTPUT_CHARS from base.py

# Maximum number of directory entries to return from list_directory to avoid
# overwhelming the context window when a directory contains many files.
_MAX_DIR_ENTRIES = 100


def _safe_count_lines(path: os.PathLike) -> str:
    """Best-effort line count for a file, returning a short string."""
    try:
        # Use text mode with errors ignored to handle most text-like files.
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return str(sum(1 for _ in f))
    except Exception:
        # For binaries or unreadable files, avoid raising and mark as unknown.
        return "unknown"




@tool
def read_file(
    file_path: Union[str, List[str]],
    first_lines: Optional[int] = None,
    last_lines: Optional[int] = None,
    keyword: Optional[str] = None,
    context_lines: Optional[int] = None,
    if_pdf: bool = False
) -> str:
    """Read the contents of one or more files from the workspace directory with flexible options.
    
    **REQUIRED:** file_path must always be provided. All other parameters are optional.
    
    **Note:** Reading the full content of a file is NOT recommended. Use `first_lines`, `last_lines`, 
    or `keyword` to read only the relevant portions. This avoids wasting context window tokens and 
    keeps responses focused.
    
    Args:
        file_path: (REQUIRED) Path to the file relative to workspace root, or absolute path.
            Can be a single string for one file, or a list of strings to read multiple files at once.
        first_lines: (Optional) If provided, return only the first N lines of each file
        last_lines: (Optional) If provided, return only the last N lines of each file
        keyword: (Optional) If provided, search for this keyword in each file and return context around matching lines
        context_lines: (Optional) Number of lines before and after a keyword match to include (default: 5, only used with keyword)
        if_pdf: (Optional) If True, read the file(s) as PDF using pypdf.
        
    Returns:
        Contents of the file(s) (or selected portion based on parameters)
    
    Examples:
        read_file(file_path="script.py", first_lines=10)  # Returns first 10 lines
        read_file(file_path="script.py", last_lines=20)  # Returns last 20 lines
        read_file(file_path="script.py", keyword="def main", context_lines=10)  # Returns 10 lines before/after matches
        read_file(file_path="script.py")  # Returns entire file
        read_file(file_path="document.pdf", if_pdf=True)  # Returns text content of PDF
        read_file(file_path=["file1.py", "file2.py"])  # Read multiple files at once
        read_file(file_path=["a.py", "b.py"], first_lines=5)  # First 5 lines of each file
    """
    # Normalize to list for uniform handling
    paths = file_path if isinstance(file_path, list) else [file_path]
    results = []
    scoped_truncation_msg = (
        f"\n... [Output truncated to {MAX_OUTPUT_CHARS} chars. "
        "Reduce first_lines/last_lines, narrow the keyword, or lower context_lines.]\n"
    )

    for fp in paths:
        try:
            path = _resolve_path(fp)
            error = _validate_workspace_path(path)
            if error:
                results.append(error)
                continue

            if not path.exists():
                results.append(f"Error: File '{fp}' does not exist.")
                continue
            if not path.is_file():
                results.append(f"Error: '{fp}' is not a file.")
                continue

            # Protect internal/hidden files from being read directly
            if path.name in PROTECTED_SYSTEM_FILES:
                results.append(
                    f"Error: Reading '{path.name}' is not permitted because it is an "
                    "internal system file."
                )
                continue

            if if_pdf:
                try:
                    import pypdf
                except ImportError:
                    results.append("Error: pypdf is not installed. Please install it to read PDF files.")
                    continue
                
                try:
                    text_content = []
                    with open(path, "rb") as f:
                        reader = pypdf.PdfReader(f)
                        for page in reader.pages:
                            text_content.append(page.extract_text())
                    
                    # Combine all text and split into lines, keeping line endings to match readlines behavior
                    full_text = "\n".join(text_content)
                    lines = full_text.splitlines(keepends=True)
                    if not lines and full_text:  # Handle case where text exists but no newlines
                        lines = [full_text]
                except Exception as e:
                    results.append(f"**Reading File:** `{fp}`\n> Error reading PDF file: {str(e)}")
                    continue
            else:
                # Read all lines
                with open(path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
            
            total_lines = len(lines)
            
            # If keyword is provided, search for it
            if keyword:
                context = context_lines if context_lines is not None else 10
                matching_line_indices = []
                
                # Find all lines containing the keyword (case-insensitive search)
                for i, line in enumerate(lines):
                    if keyword.lower() in line.lower():
                        matching_line_indices.append(i)
                
                if not matching_line_indices:
                    results.append(f"Error: Keyword '{keyword}' not found in file '{fp}'.")
                    continue
                
                # Collect all context ranges (using set to avoid duplicates)
                result_indices = set()
                
                for match_idx in matching_line_indices:
                    # Calculate range: context_lines before to context_lines after
                    start_idx = max(0, match_idx - context)
                    end_idx = min(total_lines, match_idx + context + 1)
                    
                    # Add all indices in this range
                    for idx in range(start_idx, end_idx):
                        result_indices.add(idx)
                
                # Sort indices and collect lines in order
                sorted_indices = sorted(result_indices)
                result_lines = [lines[i] for i in sorted_indices]
                
                # Add header with match information
                match_info = (
                    f"Found keyword '{keyword}' at line(s) "
                    f"{', '.join(str(idx + 1) for idx in matching_line_indices)} "
                    f"(showing {context} lines of context):\n\n"
                )
                keyword_result = f"**Reading File:** `{fp}`\n> {match_info}\n```\n{''.join(result_lines)}\n```"
                results.append(truncate_content(keyword_result, MAX_OUTPUT_CHARS, scoped_truncation_msg))
                continue
            
            # If first_lines is provided
            if first_lines is not None:
                if first_lines <= 0:
                    results.append(f"Error: first_lines must be a positive integer.")
                    continue
                if first_lines >= total_lines:
                    first_result = f"**Reading File:** `{fp}`\n```\n{''.join(lines)}\n```"
                else:
                    first_result = f"**Reading File:** `{fp}`\n```\n{''.join(lines[:first_lines])}\n```"
                results.append(truncate_content(first_result, MAX_OUTPUT_CHARS, scoped_truncation_msg))
                continue
            
            # If last_lines is provided
            if last_lines is not None:
                if last_lines <= 0:
                    results.append(f"Error: last_lines must be a positive integer.")
                    continue
                if last_lines >= total_lines:
                    last_result = f"**Reading File:** `{fp}`\n```\n{''.join(lines)}\n```"
                else:
                    last_result = f"**Reading File:** `{fp}`\n```\n{''.join(lines[-last_lines:])}\n```"
                results.append(truncate_content(last_result, MAX_OUTPUT_CHARS, scoped_truncation_msg))
                continue
            
            # Default: return entire file, but guard against extremely large outputs
            full_content = "".join(lines)
            
            truncated = truncate_content(
                full_content, 
                MAX_OUTPUT_CHARS, 
                f"\n... [Content truncated to {MAX_OUTPUT_CHARS} chars. Use 'first_lines', 'last_lines', or 'keyword' to read specific parts.]\n"
            )
            
            results.append(f"**Reading File:** `{fp}`\n\n```\n{truncated}\n```")
            
        except Exception as e:
            results.append(f"**Reading File:** `{fp}`\n\n> Error reading file: {str(e)}")

    combined = "\n\n---\n\n".join(results)
    return truncate_content(
        combined,
        MAX_OUTPUT_CHARS,
        f"\n... [Combined output truncated to {MAX_OUTPUT_CHARS} chars. Read fewer files or narrow each selection.]\n"
    )


@tool
def edit_file(file_path: str, old_string: str, new_string: str, replace_all: bool = False) -> str:
    """Edit an existing file by replacing text. This is useful for modifying scripts incrementally.
    
    Args:
        file_path: Path to the file relative to workspace root, or absolute path
        old_string: The text to find and replace. Supports fuzzy matching for whitespace/indentation.
        new_string: The replacement text
        replace_all: If True, replace all occurrences; if False, replace only the first occurrence (default: False)
    
    Returns:
        Success message with details about what was changed, or error message
    """
    try:
        path = _resolve_path(file_path)
        error = _validate_workspace_path(path)
        if error:
            return f"**Edit File:** `{file_path}`\n\n> Error: {error.replace('access', 'edit')}"
        
        if not path.exists():
            return (
                f"**Edit File:** `{file_path}`\n> "
                f"Error: File `{file_path}` does not exist. "
                "Create it with Python/pathlib via execute_python first."
            )
        if not path.is_file():
            return f"**Edit File:** `{file_path}`\n> Error: `{file_path}` is not a file."
        
        # Protect internal/hidden files from being edited directly
        if path.name in PROTECTED_SYSTEM_FILES:
            return (
                f"**Edit File:** `{file_path}`\n\n> "
                f"Error: Editing '{path.name}' is not permitted because it is an "
                "internal system file."
            )

        # Read the current file content
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        
        # Strategy 1: Exact Match
        if old_string in content:
            count = content.count(old_string)
            new_content = content.replace(old_string, new_string) if replace_all else content.replace(old_string, new_string, 1)
            
            with open(path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            
            if replace_all and count > 1:
                return f"**Edit File:** `{file_path}`\n\n> Successfully replaced {count} occurrence(s) of the specified text."
            if not replace_all and count > 1:
                return f"**Edit File:** `{file_path}`\n\n> Successfully replaced the first occurrence ({count} total occurrence(s) found). Use replace_all=True to replace all occurrences."
            return f"**Edit File:** `{file_path}`\n\n> Successfully replaced the text."

        # Strategy 2: Line-based Fuzzy Match (Indentation Agnostic)
        matches_ranges = _find_line_based_matches(old_string, content)
        if matches_ranges:
            if not replace_all:
                matches_ranges = [matches_ranges[0]]
            
            content_lines = content.split("\n")
            for start_idx, end_idx in reversed(matches_ranges):
                del content_lines[start_idx:end_idx+1]
                content_lines.insert(start_idx, new_string)
            
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(content_lines))
            return f"**Edit File:** `{file_path}`\n\n> Successfully replaced {len(matches_ranges)} occurrence(s) (using line-based indentation matching)."

        # Strategy 3: Token-based Fuzzy Match (Regex)
        matches = _find_token_based_matches(old_string, content)
        
        if not matches:
            error_msg = f"Error: The specified text to replace was not found in '{file_path}'.\n\n"
            error_msg += "Strategies attempted:\n1. Exact match (failed)\n2. Line-based match (indentation agnostic) (failed)\n3. Token-based fuzzy match (whitespace agnostic) (failed)\n\n"
            
            try:
                matcher = difflib.SequenceMatcher(None, old_string, content)
                match = matcher.find_longest_match(0, len(old_string), 0, len(content))
                
                if match.size > 10:
                    start_idx, end_idx = match.b, match.b + match.size
                    lines_before = content[:start_idx].count('\n') + 1
                    line_start = content.rfind('\n', 0, start_idx) + 1
                    line_end = content.find('\n', end_idx)
                    if line_end == -1:
                        line_end = len(content)
                    
                    full_line_text = content[line_start:line_end]
                    error_msg += f"Closest partial match found at line {lines_before}:\n```\n{full_line_text[:300]}{'...' if len(full_line_text) > 300 else ''}\n```\nTIP: Use read_file to verify the content before editing.\n"
                else:
                    tokens = re.findall(r"\w+|[^\w\s]", old_string)
                    if len(tokens) > 3:
                        anchor_pattern = r"\s*".join(re.escape(t) for t in tokens[:5])
                        anchor_match = re.compile(anchor_pattern).search(content)
                        if anchor_match:
                            start_idx = anchor_match.start()
                            lines_before = content[:start_idx].count('\n') + 1
                            context_text = content[
                                start_idx : min(start_idx + 200, len(content))
                            ]
                            error_msg += f"Found start of text at line {lines_before}:\n```\n{context_text}...\n```\n"
                        else:
                            error_msg += "No close match found. Use read_file to see the exact file content.\n"
            except Exception:
                error_msg += "Could not determine closest match.\n"
            
            return f"**Edit File:** `{file_path}`\n\n> Error: {error_msg}"

        # Perform replacement
        if not replace_all:
            # Only replace first match
            matches = [matches[0]]
            
        # Apply replacements from end to start to preserve indices
        new_content = content
        for match in reversed(matches):
            start, end = match.span()
            new_content = new_content[:start] + new_string + new_content[end:]
            
        with open(path, "w", encoding="utf-8") as f:
            f.write(new_content)
            
        return f"**Edit File:** `{file_path}`\n\n> Successfully replaced {len(matches)} occurrence(s) (using fuzzy whitespace matching)."
        
    except Exception as e:
        return f"**Edit File:** `{file_path}`\n\n> Error editing file: {str(e)}"


@tool
def list_directory(directory_path: Union[str, List[str]] = ".", pattern: str = "*", exclude_docs: bool = False) -> str:
    """List files and directories in one or more directories.
    
    **Note:** It is highly recommended to use the `pattern` argument (e.g., `"*.py"`) to narrow down the listing scope for more efficient results, especially in large directories.
    
    Args:
        directory_path: Path to directory relative to workspace root (default: "."). Can be a single string for one directory, or a list of strings to list multiple directories at once.
        pattern: Glob pattern to filter files (default: "*")
        exclude_docs: If True, exclude the 'docs' folder from listing (default: False)
    
    Returns:
        List of files and directories.
        For very large directories, only the first `_MAX_DIR_ENTRIES` entries
        are shown along with a truncation notice.
    
    Examples:
        list_directory(directory_path=".")  # List current directory
        list_directory(directory_path=["src", "tests"])  # List multiple directories at once
        list_directory(directory_path=["dir1", "dir2"], pattern="*.py")  # List .py files in multiple dirs
    """
    # Normalize to list for uniform handling
    dirs = directory_path if isinstance(directory_path, list) else [directory_path]
    results = []

    for dp in dirs:
        try:
            path = _resolve_path(dp)
            error = _validate_workspace_path(path)
            if error:
                results.append(error.replace("files", "directories"))
                continue
            
            if not path.exists():
                results.append(f"Error: Directory '{dp}' does not exist.")
                continue
            if not path.is_dir():
                results.append(f"Error: '{dp}' is not a directory.")
                continue
            
            all_items = []
            
            for item in sorted(path.glob(pattern)):
                item_name = item.name
                if item_name in PROTECTED_SYSTEM_FILES or item_name.startswith("."):
                    continue
                # Exclude docs folder if requested
                if exclude_docs and item_name == "docs":
                    continue
                
                rel_path = item.relative_to(WORKSPACE_DIR)
                if item.is_dir():
                    all_items.append(f"[DIR]  {rel_path}/")
                else:
                    size_bytes = item.stat().st_size
                    line_count = _safe_count_lines(item)
                    line_part = (
                        f", {line_count} lines" if line_count != "unknown" else ", lines: N/A"
                    )
                    all_items.append(
                        f"[FILE] {rel_path} ({size_bytes} bytes{line_part})"
                    )
            
            if not all_items:
                results.append(f"**List Directory:** `{dp}`\n\n> No files found matching pattern '{pattern}'")
                continue

            total = len(all_items)
            if total > _MAX_DIR_ENTRIES:
                shown_items = all_items[:_MAX_DIR_ENTRIES]
                header = (
                    f"Warning: Directory '{dp}' has {total} matching entries. "
                    f"Showing only the first {_MAX_DIR_ENTRIES}.\n"
                )
                results.append(f"**List Directory:** `{dp}`\n\n> {header}\n```\n" + "\n".join(shown_items) + "\n```")
            else:
                results.append(f"**List Directory:** `{dp}`\n\n```\n" + "\n".join(all_items) + "\n```")
        except Exception as e:
            results.append(f"**List Directory:** `{dp}`\n\n> Error listing directory: {str(e)}")

    return "\n\n---\n\n".join(results)


@tool
def analyze_image(file_path: str, prompt: str) -> str:
    """Analyze an image using an LLM with a text prompt and return only the text answer.
    
    This tool reads an image file, sends it along with a text prompt to a multimodal LLM,
    and returns the LLM's text analysis of the image.
    
    Args:
        file_path: Path to the image file relative to workspace root, or absolute path
        prompt: Text prompt describing what to analyze in the image (e.g., "analyse this isotherm shape and see if the isotherm shows gate opening effect")
    
    Returns:
        Text answer from the LLM analyzing the image based on the prompt
    
    Examples:
        analyze_image(file_path="isotherm.png", prompt="analyse this isotherm shape and see if the isotherm shows gate opening effect")
        analyze_image(file_path="plot.png", prompt="describe the trends shown in this plot")
    """
    try:
        from ..llm_config import initialize_llm
        
        path = _resolve_path(file_path)
        error = _validate_workspace_path(path)
        if error:
            return error

        if not path.exists():
            return f"Error: File '{file_path}' does not exist."
        if not path.is_file():
            return f"Error: '{file_path}' is not a file."

        # Protect internal/hidden files from being read directly
        if path.name in PROTECTED_SYSTEM_FILES:
            return (
                f"Error: Analyzing '{path.name}' is not permitted because it is an "
                "internal system file."
            )

        # Check if current model is multimodal
        current_model = os.getenv("MODEL", "")
        if not _is_multimodal_model(current_model):
            return (
                f"Error: Cannot analyze image '{file_path}' because the current model "
                f"'{current_model}' is not configured as multimodal. "
                "Please use a multimodal model (e.g., gemini-3.5-flash, gpt-4o, claude-sonnet-4-5-20250929)."
            )

        # Check mime type
        mime_type, _ = mimetypes.guess_type(path)
        if not mime_type or not mime_type.startswith("image/"):
            return (
                f"Error: File '{file_path}' does not appear to be an image file. "
                f"Detected type: {mime_type}"
            )

        # Read and encode the image
        try:
            with open(path, "rb") as image_file:
                encoded_string = base64.b64encode(image_file.read()).decode("utf-8")
        except Exception as e:
            return f"Error reading image file '{file_path}': {str(e)}"

        # Initialize LLM
        try:
            llm, _ = initialize_llm()
        except Exception as e:
            return f"Error initializing LLM: {str(e)}"

        # Create message with image and prompt
        message_content = [
            {
                "type": "text",
                "text": prompt
            },
            {
                "type": "image_url",
                "image_url": {"url": f"data:{mime_type};base64,{encoded_string}"}
            }
        ]
        
        message = HumanMessage(content=message_content)

        # Call LLM to analyze the image
        try:
            response = llm.invoke([message])
            
            # Track token usage from response
            if response and hasattr(response, 'usage_metadata') and response.usage_metadata:
                usage = response.usage_metadata
                # Handle both dict and object access patterns
                if isinstance(usage, dict):
                    input_tokens = usage.get('input_tokens', 0)
                    output_tokens = usage.get('output_tokens', 0)
                else:
                    input_tokens = getattr(usage, 'input_tokens', 0)
                    output_tokens = getattr(usage, 'output_tokens', 0)
                record_api_call(
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cache_read_tokens=extract_cache_read_tokens(usage),
                )
            
            # Extract text content from response
            if hasattr(response, 'content'):
                content = response.content
                # Handle case where content is a list of content blocks (e.g., Gemini models)
                if isinstance(content, list):
                    # Extract just the text from each block
                    text_parts = []
                    for block in content:
                        if isinstance(block, dict) and 'text' in block:
                            text_parts.append(block['text'])
                        elif isinstance(block, str):
                            text_parts.append(block)
                    content = '\n'.join(text_parts) if text_parts else str(content)
                return f"**Analyze Image:** `{file_path}`\n> {content}"
            elif isinstance(response, str):
                return f"**Analyze Image:** `{file_path}`\n> {response}"
            else:
                return f"**Analyze Image:** `{file_path}`\n> Error: Unexpected response format from LLM: {type(response)}"
        except Exception as e:
            return f"**Analyze Image:** `{file_path}`\n> Error during LLM inference: {str(e)}"

    except Exception as e:
        return f"**Analyze Image:** `{file_path}`\n> Error analyzing image: {str(e)}"


@tool
def grep_search(
    pattern: str,
    directory_path: str,
    include_pattern: Optional[str] = None,
    exclude_pattern: Optional[str] = None,
    case_insensitive: bool = False,
    show_line_numbers: bool = True,
    max_results: int = 100
) -> str:
    """Fast search for a pattern in files using grep.
    
    This tool uses grep to quickly search for text patterns across files in the workspace.
    It's much faster than reading files individually when you need to find occurrences
    of a pattern across multiple files. 
    
    **Note:** It is highly recommended to narrow down the directory_path to a specific subdirectory to make the search more efficient and avoid searching the entire workspace.
    
    Args:
        pattern: The regex pattern to search for. Use basic regex syntax.
        directory_path: Directory to search in, relative to workspace root. It is highly recommended to narrow this down to a specific subdirectory rather than using the workspace root to improve search efficiency.
        include_pattern: Optional glob pattern to filter files to search (e.g., "*.py" for Python files only)
        exclude_pattern: Optional glob pattern to exclude files (e.g., "*.log" to skip log files)
        case_insensitive: If True, perform case-insensitive matching (default: False)
        show_line_numbers: If True, include line numbers in output (default: True)
        max_results: Maximum number of matching lines to return (default: 100). When
            provided and > 0, the grep process stops after this many matches to keep
            output bounded.
    
    Returns:
        Search results showing matching lines with file paths and line numbers,
        or a message if no matches found.
    
    Examples:
        grep_search(pattern="def main", include_pattern="*.py")  # Find 'def main' in Python files
        grep_search(pattern="ERROR", directory_path="quasar_logs")  # Search for ERROR in QUASAR logs
        grep_search(pattern="TODO", case_insensitive=True)  # Case-insensitive search for TODO
        grep_search(pattern="import numpy", include_pattern="*.py", exclude_pattern="test_*")  # Exclude test files
    """
    import subprocess
    
    try:
        path = _resolve_path(directory_path)
        error = _validate_workspace_path(path)
        if error:
            return error.replace("files", "directories")
        
        if not path.exists():
            return f"Error: Directory '{directory_path}' does not exist."
        if not path.is_dir():
            return f"Error: '{directory_path}' is not a directory."
        
        # Build grep command
        # Use -r for recursive, -n for line numbers, -H for filename
        cmd = ["grep", "-r", "-H"]
        
        if show_line_numbers:
            cmd.append("-n")
        
        if case_insensitive:
            cmd.append("-i")
        
        # Add include pattern if specified
        if include_pattern:
            cmd.extend(["--include", include_pattern])
        
        # Add exclude pattern if specified
        if exclude_pattern:
            cmd.extend(["--exclude", exclude_pattern])
        
        # Always exclude common non-text directories and files
        for exclude in ["*.pyc", "__pycache__", ".git", "*.sqlite*", "*.db"] + list(PROTECTED_SYSTEM_FILES):
            cmd.extend(["--exclude", exclude])
        for exclude_dir in ["__pycache__", ".git", "node_modules", ".venv", "venv", "quasar_logs", "quasar_archive"]:
            cmd.extend(["--exclude-dir", exclude_dir])
        
        # Skip binary files to avoid noise/garbage output
        cmd.append("--binary-files=without-match")
        
        # Bound the search at the grep level to avoid huge outputs/long runs
        if max_results and max_results > 0:
            cmd.extend(["-m", str(max_results)])
        
        # Add the pattern and directory
        cmd.append("--")  # ensure pattern is not treated as a flag
        cmd.append(pattern)
        cmd.append(str(path))
        
        # Run grep with timeout
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,  # 2 minute timeout
                cwd=str(WORKSPACE_DIR)
            )
        except subprocess.TimeoutExpired:
            return f"**Grep Search:** `{pattern}`\n\n> Error: Search timed out after 2 minutes. Try narrowing your search with include_pattern or a more specific directory."
        
        # grep returns exit code 1 if no matches found, 0 if matches found, 2+ for errors
        if result.returncode == 1:
            return f"**Grep Search:** `{pattern}`\n\n> No matches found for pattern '{pattern}' in '{directory_path}'."
        
        if result.returncode >= 2:
            error_msg = result.stderr.strip() if result.stderr else "Unknown error"
            return f"**Grep Search:** `{pattern}`\n\n> Error running grep: {error_msg}"
        
        # Process output
        output_lines = result.stdout.strip().split("\n") if result.stdout.strip() else []
        total_matches = len(output_lines)
        
        if total_matches == 0:
            return f"**Grep Search:** `{pattern}`\n\n> No matches found."
        
        # Limit results (safety in case -m was not applied)
        if max_results and max_results > 0 and total_matches > max_results:
            output_lines = output_lines[:max_results]
        
        # Make paths relative to workspace for cleaner output
        formatted_lines = []
        workspace_str = str(WORKSPACE_DIR)
        for line in output_lines:
            # Remove workspace prefix from paths
            if line.startswith(workspace_str):
                line = line[len(workspace_str):].lstrip("/")
            formatted_lines.append(line)
        
        result_text = "\n".join(formatted_lines)
        
        # Add truncation notice if applicable
        truncation_msg = ""
        truncated_by_limit = bool(max_results and max_results > 0 and total_matches >= max_results)
        if truncated_by_limit:
            truncation_msg = (
                f"\n\n> Search stopped after {max_results} matches to keep output bounded. "
                "Use a more specific pattern, include_pattern, or a larger max_results to see more."
            )
        
        match_label = f"at least {total_matches}" if truncated_by_limit else str(total_matches)
        
        return f"**Grep Search:** `{pattern}`\n\n**Found {match_label} matches:**\n\n```\n{result_text}\n```{truncation_msg}"
        
    except Exception as e:
        return f"**Grep Search:** `{pattern}`\n\n> Error during search: {str(e)}"


@tool
def get_hardware_info() -> str:
    """Get information about available CPU and GPU hardware resources.
    
    This tool returns information about the system's hardware including:
    - CPU model name (or Vendor ID if model name is unavailable)
    - Number of usable physical CPU cores
    - GPU information (CUDA/ROCm if available, or N/A)
    
    Use this tool when you need to determine available computational resources
    for parallelization decisions (MPI ranks, OpenMP threads, etc.).
    
    Returns:
        Hardware information string with CPU and GPU details.
    
    Examples:
        get_hardware_info()  # Returns: "- CPU: Intel Xeon...\n- Physical cores: 32\n- GPU: CUDA - NVIDIA A100..."
    """
    try:
        from ..agents.utils import get_hardware_info as _get_hardware_info
        hardware_info = _get_hardware_info()
        return f"**Hardware Info:**\n\n{hardware_info}"
    except Exception as e:
        return f"**Hardware Info:**\n\n> Error getting hardware info: {str(e)}"
