import os
import re
from collections import defaultdict
from pathlib import Path
from typing import Optional, List

# Get workspace directory - can be set via WORKSPACE_DIR environment variable for Docker bind mounts
# Adjusted for src/tools/base.py location (one level deeper than src/tools.py)
_project_root = Path(__file__).parent.parent.parent
WORKSPACE_DIR = Path(os.getenv("WORKSPACE_DIR", str(_project_root / "workspace")))
WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)

# logs directory
LOGS_DIR = WORKSPACE_DIR / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# Set of supported multimodal models
MULTIMODAL_MODELS = {
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    "gemini-3-pro-preview",
    "gemini-3-flash-preview",
    "gpt-5.1",
    "gpt-5",
    "gpt-5-mini",
    "gpt-4o",
    "gpt-4o-mini",
    "claude-sonnet-4-5-20250929",
    "claude-haiku-4-5-20251001",
    "claude-opus-4-5-20251101",
    "claude-opus-4-1-20250805",
    "claude-sonnet-4-20250514",
    "claude-opus-4-20250514",
    "grok-4-0709",
    "grok-4-fast-non-reasoning",
    "grok-4-fast-reasoning",
    "grok-4-1-fast-reasoning",
    "grok-4-1-fast-non-reasoning",
}


def _is_multimodal_model(model_name: str) -> bool:
    """Return True if the given model name is in the known multimodal set."""
    return model_name in MULTIMODAL_MODELS


def _resolve_path(file_path: str) -> Path:
    """Resolve a file path (relative or absolute) to a Path object."""
    return Path(file_path) if os.path.isabs(file_path) else WORKSPACE_DIR / file_path


def _validate_workspace_path(path: Path) -> Optional[str]:
    """Validate that a path is within the workspace directory.
    
    Returns:
        Error message if invalid, None if valid
    """
    resolved = path.resolve()
    workspace_resolved = WORKSPACE_DIR.resolve()
    if not str(resolved).startswith(str(workspace_resolved)):
        return "Error: Cannot access files outside workspace directory."
    return None


def _find_line_based_matches(old_string: str, content: str) -> List[tuple[int, int]]:
    """Find line-based matches (indentation agnostic)."""
    old_lines_info = [(i, line.strip()) for i, line in enumerate(old_string.split('\n')) if line.strip()]
    if not old_lines_info:
        return []
    
    old_lines_content = [info[1] for info in old_lines_info]
    content_lines = content.split('\n')
    content_lines_info = [(i, line.strip()) for i, line in enumerate(content_lines) if line.strip()]
    
    matches_ranges = []
    if len(content_lines_info) >= len(old_lines_content):
        for i in range(len(content_lines_info) - len(old_lines_content) + 1):
            if all(content_lines_info[i+j][1] == old_line for j, old_line in enumerate(old_lines_content)):
                start_line_idx = content_lines_info[i][0]
                end_line_idx = content_lines_info[i + len(old_lines_content) - 1][0]
                matches_ranges.append((start_line_idx, end_line_idx))
    
    return matches_ranges


def _find_token_based_matches(old_string: str, content: str) -> List[re.Match]:
    """Find token-based matches (whitespace agnostic)."""
    tokens = re.findall(r'\w+|[^\w\s]', old_string)
    if not tokens:
        return []
    
    pattern = r"\s*".join(re.escape(t) for t in tokens)
    return list(re.compile(pattern).finditer(content))


# Global truncation limits
MAX_OUTPUT_CHARS = 15000

# Files that should be hidden from directory listings and protected from agent operations
PROTECTED_SYSTEM_FILES = {
    "checkpoints.sqlite",
    "checkpoints.sqlite-shm",
    "checkpoints.sqlite-wal",
    "checkpoint_settings.json",
    "conversation.md",
    "input_messages.md",
    "execution_overview.md",
    "debug_cli.log",
    "pending_execution.json",
    "logs",
}


def truncate_content(content: str, max_length: int = MAX_OUTPUT_CHARS, truncation_msg: str = "\n... [Output truncated]\n") -> str:
    """Truncate content to a maximum length.
    
    Args:
        content: The string to truncate
        max_length: Maximum allowed characters (default: MAX_OUTPUT_CHARS)
        truncation_msg: Message to append if truncated
        
    Returns:
        Truncated string
    """
    if not content or len(content) <= max_length:
        return content
    return content[:max_length] + truncation_msg


def _find_number_ranges(numbers: List[int]) -> List[tuple[int, int]]:
    """Find consecutive ranges in a sorted list of numbers."""
    if not numbers:
        return []
    
    numbers = sorted(numbers)
    ranges = []
    start = prev = numbers[0]
    
    for num in numbers[1:]:
        if num != prev + 1:
            ranges.append((start, prev))
            start = num
        prev = num
    ranges.append((start, prev))
    return ranges


def format_file_list(files: List[str], max_files_per_dir: int = 10) -> str:
    """Format a list of files smartly, collapsing large numbered sequences.
    
    Args:
        files: List of file paths (relative strings)
        max_files_per_dir: Threshold to trigger summarization for a directory
        
    Returns:
        Formatted string representation
    """
    if not files:
        return ""
    
    # Group by directory
    dir_files = defaultdict(list)
    for f in sorted(files):
        path = Path(f)
        parent = str(path.parent) if str(path.parent) != "." else ""
        dir_files[parent].append(path.name)
    
    output_lines = []
    
    for dirname in sorted(dir_files.keys()):
        filenames = sorted(dir_files[dirname])
        prefix = f"{dirname}/" if dirname else ""
        
        if len(filenames) <= max_files_per_dir:
            for fname in filenames:
                output_lines.append(f"- `{prefix}{fname}`")
            continue
        
        # Too many files - try to collapse patterns
        patterns = defaultdict(list)
        others = []
        
        for fname in filenames:
            match = re.match(r'^(.*?)(\d+)(\.[^.]+)$', fname)
            if match:
                prefix_part, num, suffix = match.groups()
                patterns[(prefix_part, suffix)].append(int(num))
            else:
                others.append(fname)
        
        # Process patterns
        for (f_prefix, f_suffix), numbers in patterns.items():
            if len(numbers) > 1:
                ranges = _find_number_ranges(numbers)
                range_strs = [f"{s}" if s == e else f"{s}-{e}" for s, e in ranges]
                range_txt = ",".join(range_strs)
                output_lines.append(f"- `{prefix}{f_prefix}[{range_txt}]{f_suffix}` ({len(numbers)} files)")
            else:
                others.append(f"{f_prefix}{numbers[0]}{f_suffix}")
        
        # Process remaining files
        others.sort()
        if len(others) > max_files_per_dir:
            for fname in others[:max_files_per_dir]:
                output_lines.append(f"- `{prefix}{fname}`")
            output_lines.append(f"  ... and {len(others) - max_files_per_dir} more files in {dirname or 'root'}/")
        else:
            for fname in others:
                output_lines.append(f"- `{prefix}{fname}`")
    
    return "\n".join(output_lines)


def get_all_files(directory: Optional[Path] = None) -> set[str]:
    """Get all file paths in a directory recursively, relative to workspace."""
    directory = directory or WORKSPACE_DIR
    files = set()
    
    try:
        for file in directory.rglob("*"):
            if not file.is_file():
                continue
            if any(part.startswith('.') or part == "__pycache__" for part in file.parts):
                continue
            # Skip internal/log files that should not appear in the new-file tracker
            if file.name in PROTECTED_SYSTEM_FILES:
                continue
            
            try:
                files.add(str(file.relative_to(WORKSPACE_DIR)))
            except ValueError:
                pass
    except Exception:
        pass
    
    return files




