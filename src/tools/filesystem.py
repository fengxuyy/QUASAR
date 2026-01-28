import os
import shutil
import base64
import difflib
import mimetypes
import re
from typing import Optional

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
from ..usage_tracker import record_api_call


# Maximum number of characters to return when reading an entire file at once.
# This helps avoid blowing the model's context window on very large files.
# _MAX_FULL_READ_CHARS replaced by global MAX_OUTPUT_CHARS from base.py

# Maximum number of directory entries to return from list_directory to avoid
# overwhelming the context window when a directory contains many files.
_MAX_DIR_ENTRIES = 300


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
    file_path: str,
    first_lines: Optional[int] = None,
    last_lines: Optional[int] = None,
    keyword: Optional[str] = None,
    context_lines: Optional[int] = None,
    if_pdf: bool = False
) -> str:
    """Read the contents of a file from the workspace directory with flexible options.
    
    **REQUIRED:** file_path must always be provided. All other parameters are optional.
    
    **Note:** For image analysis, use the `analyze_image` tool instead of reading images directly.
    
    Args:
        file_path: (REQUIRED) Path to the file relative to workspace root, or absolute path. This parameter is mandatory.
        first_lines: (Optional) If provided, return only the first N lines of the file
        last_lines: (Optional) If provided, return only the last N lines of the file
        keyword: (Optional) If provided, search for this keyword in the file and return context around matching lines
        context_lines: (Optional) Number of lines before and after a keyword match to include (default: 5, only used with keyword)
        if_pdf: (Optional) If True, read the file as a PDF using pypdf.
        
    Notes on large files:
        - When reading an entire file (no first_lines/last_lines/keyword provided),
          the returned content is limited to `MAX_OUTPUT_CHARS`
          characters to protect the context window.
        - If truncation occurs, a warning header is added. Use `first_lines`,
          `last_lines`, or `keyword` for more targeted reads on large files.
    
    Returns:
        Contents of the file (or selected portion based on parameters)
    
    Examples:
        read_file(file_path="script.py", first_lines=10)  # Returns first 10 lines
        read_file(file_path="script.py", last_lines=20)  # Returns last 20 lines
        read_file(file_path="script.py", keyword="def main", context_lines=10)  # Returns 10 lines before/after matches
        read_file(file_path="script.py")  # Returns entire file
        read_file(file_path="document.pdf", if_pdf=True)  # Returns text content of PDF
    """
    try:
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
                f"Error: Reading '{path.name}' is not permitted because it is an "
                "internal system file."
            )

        if if_pdf:
            try:
                import pypdf
            except ImportError:
                return "Error: pypdf is not installed. Please install it to read PDF files."
            
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
                return f"**Reading File:** `{file_path}`\n> Error reading PDF file: {str(e)}"
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
                return f"Error: Keyword '{keyword}' not found in file '{file_path}'."
            
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
            return f"**Reading File:** `{file_path}`\n> {match_info}\n```\n{''.join(result_lines)}\n```"
        
        # If first_lines is provided
        if first_lines is not None:
            if first_lines <= 0:
                return f"Error: first_lines must be a positive integer."
            if first_lines >= total_lines:
                # Return entire file if requested lines exceed file length
                return f"**Reading File:** `{file_path}`\n```\n{''.join(lines)}\n```"
            return f"**Reading File:** `{file_path}`\n```\n{''.join(lines[:first_lines])}\n```"
        
        # If last_lines is provided
        if last_lines is not None:
            if last_lines <= 0:
                return f"Error: last_lines must be a positive integer."
            if last_lines >= total_lines:
                # Return entire file if requested lines exceed file length
                return f"**Reading File:** `{file_path}`\n```\n{''.join(lines)}\n```"
            return f"**Reading File:** `{file_path}`\n```\n{''.join(lines[-last_lines:])}\n```"
        
        # Default: return entire file, but guard against extremely large outputs
        full_content = "".join(lines)
        
        truncated = truncate_content(
            full_content, 
            MAX_OUTPUT_CHARS, 
            f"\n... [Content truncated to {MAX_OUTPUT_CHARS} chars. Use 'first_lines', 'last_lines', or 'keyword' to read specific parts.]\n"
        )
        
        return f"**Reading File:** `{file_path}`\n\n```\n{truncated}\n```"
        
    except Exception as e:
        return f"**Reading File:** `{file_path}`\n\n> Error reading file: {str(e)}"


@tool
def write_file(file_path: str, content: str, mode: str = "w") -> str:
    """Write content to a file in the workspace directory.
    
    Args:
        file_path: Path to the file relative to workspace root, or absolute path
        content: Content to write to the file
        mode: Write mode - 'w' for overwrite, 'a' for append (default: 'w')
    
    Returns:
        Success message or error
    """
    try:
        path = _resolve_path(file_path)
        error = _validate_workspace_path(path)
        if error:
            return error.replace("access", "write")
        
        # Protect internal/hidden files from being written directly
        if path.name in PROTECTED_SYSTEM_FILES:
            return (
                f"**Write File:** `{file_path}`\n\n> "
                f"Error: Writing to '{path.name}' is not permitted because it is an "
                "internal system file."
            )

        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a" if mode == "a" else "w", encoding="utf-8") as f:
            f.write(content)
        return f"**Write File:** `{file_path}`\n\n> Successfully wrote to `{file_path}`"
    except Exception as e:
        return f"**Write File:** `{file_path}`\n\n> Error writing file: {str(e)}"


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
                "Use write_file to create a new file."
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
def delete_file(file_path: str) -> str:
    """Delete a file from the workspace directory.
    
    Args:
        file_path: Path to the file relative to workspace root, or absolute path
    
    Returns:
        Success message or error
    """
    try:
        path = _resolve_path(file_path)
        error = _validate_workspace_path(path)
        if error:
            return error.replace("access", "delete")

        # Protect internal/hidden files from deletion, even if directly targeted
        if path.name in PROTECTED_SYSTEM_FILES:
            return (
                f"**Delete File:** `{file_path}`\n\n> "
                f"Error: Deletion of '{path.name}' is not permitted because it is an "
                "internal system file."
            )

        path.unlink()
        return f"**Delete File:** `{file_path}`\n\n> Successfully deleted file."
    except Exception as e:
        return f"**Delete File:** `{file_path}`\n\n> Error deleting file: {str(e)}"


@tool
def list_directory(directory_path: str = ".", pattern: str = "*", exclude_docs: bool = False) -> str:
    """List files and directories in a given directory.
    
    Args:
        directory_path: Path to directory relative to workspace root (default: ".")
        pattern: Glob pattern to filter files (default: "*")
        exclude_docs: If True, exclude the 'docs' folder from listing (default: False)
    
    Returns:
        List of files and directories.
        For very large directories, only the first `_MAX_DIR_ENTRIES` entries
        are shown along with a truncation notice.
    """
    try:
        path = _resolve_path(directory_path)
        error = _validate_workspace_path(path)
        if error:
            return error.replace("files", "directories")
        
        if not path.exists():
            return f"Error: Directory '{directory_path}' does not exist."
        if not path.is_dir():
            return f"Error: '{directory_path}' is not a directory."
        
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
            return f"**List Directory:** `{directory_path}`\n\n> No files found matching pattern '{pattern}'"

        total = len(all_items)
        if total > _MAX_DIR_ENTRIES:
            shown_items = all_items[:_MAX_DIR_ENTRIES]
            header = (
                f"Warning: Directory '{directory_path}' has {total} matching entries. "
                f"Showing only the first {_MAX_DIR_ENTRIES}.\n"
            )
            return f"**List Directory:** `{directory_path}`\n\n> {header}\n```\n" + "\n".join(shown_items) + "\n```"
        
        return f"**List Directory:** `{directory_path}`\n\n```\n" + "\n".join(all_items) + "\n```"
    except Exception as e:
        return f"**List Directory:** `{directory_path}`\n\n> Error listing directory: {str(e)}"


@tool
def move_file(source_path: str, destination_path: str) -> str:
    """Move a file or directory from one location to another in the workspace.
    
    This will move the file/directory from source_path to destination_path. If destination_path
    is a directory, the source will be moved into that directory with its original name.
    If destination_path is a file path, the source will be moved and renamed to that path.
    
    Args:
        source_path: Path to the source file or directory relative to workspace root, or absolute path
        destination_path: Path to the destination file or directory relative to workspace root, or absolute path
    
    Returns:
        Success message or error
    
    Examples:
        move_file("file.txt", "subdir/file.txt")  # Move and rename
        move_file("file.txt", "subdir/")  # Move into directory (keeps original name)
        move_file("old_dir", "new_dir")  # Move directory
    """
    try:
        source = _resolve_path(source_path)
        dest = _resolve_path(destination_path)
        
        # Validate source path
        error = _validate_workspace_path(source)
        if error:
            return error.replace("access", "move")
        
        if not source.exists():
            return f"Error: Source '{source_path}' does not exist."
        
        # Validate destination path
        error = _validate_workspace_path(dest)
        if error:
            return error.replace("access", "move to")
        
        # Protect internal/hidden files from being moved
        if source.name in PROTECTED_SYSTEM_FILES:
            return (
                f"Error: Moving '{source.name}' is not permitted because it is an "
                "internal system file."
            )
        
        # If destination is an existing directory, move source into it
        if dest.exists() and dest.is_dir():
            final_dest = dest / source.name
        else:
            final_dest = dest
            # Create parent directory if it doesn't exist
            final_dest.parent.mkdir(parents=True, exist_ok=True)
        
        # Check if destination already exists
        if final_dest.exists():
            return f"Error: Destination '{destination_path}' already exists. Use rename_file to overwrite or delete it first."
        
        # Perform the move
        shutil.move(str(source), str(final_dest))
        
        return f"**Move File:** `{source_path}` → `{destination_path}`\n\n> Successfully moved file."
    except Exception as e:
        return f"**Move File:** `{source_path}` → `{destination_path}`\n\n> Error moving file: {str(e)}"


@tool
def rename_file(file_path: str, new_name: str) -> str:
    """Rename a file or directory in the workspace.
    
    This renames a file or directory to a new name in the same directory.
    For moving files to different directories, use move_file instead.
    
    Args:
        file_path: Path to the file or directory to rename relative to workspace root, or absolute path
        new_name: New name for the file or directory (just the name, not a full path)
    
    Returns:
        Success message or error
    
    Examples:
        rename_file("old_file.txt", "new_file.txt")  # Rename file
        rename_file("old_dir", "new_dir")  # Rename directory
    """
    try:
        path = _resolve_path(file_path)
        error = _validate_workspace_path(path)
        if error:
            return error.replace("access", "rename")
        
        if not path.exists():
            return f"Error: File or directory '{file_path}' does not exist."
        
        # Protect internal/hidden files from being renamed
        if path.name in PROTECTED_SYSTEM_FILES:
            return (
                f"Error: Renaming '{path.name}' is not permitted because it is an "
                "internal system file."
            )
        
        # Validate new_name doesn't contain path separators
        if "/" in new_name or "\\" in new_name:
            return (
                f"Error: New name '{new_name}' cannot contain path separators. "
                "Use move_file to move files to different directories."
            )
        
        # Check if new name already exists in the same directory
        new_path = path.parent / new_name
        if new_path.exists():
            return f"Error: A file or directory named '{new_name}' already exists in '{path.parent}'."
        
        # Perform the rename
        path.rename(new_path)
        
        return f"**Rename File:**\n> Successfully renamed `{file_path}` to `{new_name}`"
    except Exception as e:
        return f"**Rename File:**\n> Error renaming `{file_path}` to `{new_name}`: {str(e)}"


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
                "Please use a multimodal model (e.g., gemini-2.5-pro, gpt-4o, claude-sonnet-4-5-20250929)."
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
                    output_tokens=output_tokens
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
    directory_path: str = ".",
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
    
    Args:
        pattern: The regex pattern to search for. Use basic regex syntax.
        directory_path: Directory to search in, relative to workspace root (default: "." for workspace root)
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
        grep_search(pattern="ERROR", directory_path="logs")  # Search for ERROR in logs directory
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
        for exclude_dir in ["__pycache__", ".git", "node_modules", ".venv", "venv", "logs"]:
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
                timeout=30,  # 30 second timeout
                cwd=str(WORKSPACE_DIR)
            )
        except subprocess.TimeoutExpired:
            return f"**Grep Search:** `{pattern}`\n\n> Error: Search timed out after 30 seconds. Try narrowing your search with include_pattern or a more specific directory."
        
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
