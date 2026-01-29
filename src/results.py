"""Results management and archiving."""

import shutil

from .tools.base import WORKSPACE_DIR, LOGS_DIR
from .debug_logger import log_custom

IGNORED_ARCHIVE_NAMES = {"archive", "docs"}


def setup_final_results_folder():
    """Archive workspace files to run_N folder and create new final_results folder."""
    final_results_dir = WORKSPACE_DIR / "final_results"
    archive_dir = WORKSPACE_DIR / "archive"
    
    items_to_archive = [
        item for item in WORKSPACE_DIR.iterdir()
        if not item.name.startswith('.') and item.name not in IGNORED_ARCHIVE_NAMES
    ]
    
    if not items_to_archive:
        final_results_dir.mkdir(parents=True, exist_ok=True)
        return
    
    archive_dir.mkdir(parents=True, exist_ok=True)
    
    # Find highest run number
    max_run_num = 0
    for item in archive_dir.iterdir():
        if item.is_dir() and item.name.startswith("run_"):
            try:
                max_run_num = max(max_run_num, int(item.name.split("_", 1)[1]))
            except (ValueError, IndexError):
                continue
    
    archive_path = archive_dir / f"run_{max_run_num + 1}"
    archive_path.mkdir(parents=True, exist_ok=True)
    
    # Archive items
    archived_items = []
    for item in items_to_archive:
        dest_path = archive_path / item.name
        try:
            if item.is_dir():
                shutil.copytree(str(item), str(dest_path), dirs_exist_ok=True)
            else:
                shutil.copy2(str(item), str(dest_path))
            archived_items.append(item.name)
        except (OSError, PermissionError) as e:
            log_custom("RESULTS", f"Warning: Could not archive {item.name}", {"error": str(e)})
    
    if archived_items:
        log_custom("RESULTS", f"Archived {len(archived_items)} item(s) to {archive_path}", {"items": archived_items})
    
    # Clean up workspace
    for item in items_to_archive:
        try:
            shutil.rmtree(str(item)) if item.is_dir() else item.unlink()
        except (OSError, PermissionError) as e:
            log_custom("RESULTS", f"Warning: Could not remove {item.name}", {"error": str(e)})
    
    final_results_dir.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)


def final_results_exists_and_not_empty():
    """Check if final_results folder exists and is not empty."""
    final_results_dir = WORKSPACE_DIR / "final_results"
    if not final_results_dir.exists() or not final_results_dir.is_dir():
        return False
    try:
        return any(not item.name.startswith('.') for item in final_results_dir.iterdir())
    except (OSError, PermissionError):
        return False


def cleanup_workspace_keep_archive():
    """Delete everything in workspace except docs, archive, and dotfiles.
    This clears current results and checkpoints but preserves archived runs.
    Also explicitly deletes checkpoint_settings.json.
    """
    # Explicitly delete checkpoint_settings.json if it exists
    checkpoint_settings_path = WORKSPACE_DIR / "checkpoint_settings.json"
    if checkpoint_settings_path.exists():
        try:
            checkpoint_settings_path.unlink()
            log_custom("RESULTS", f"Deleted: {checkpoint_settings_path}")
        except (OSError, PermissionError) as e:
            log_custom("RESULTS", f"Warning: Could not delete {checkpoint_settings_path}", {"error": str(e)})
    
    for item in WORKSPACE_DIR.iterdir():
        # Skip dot-files/folders
        if item.name.startswith("."):
            continue
        # Skip docs and archive - only delete current workspace files
        if item.name in ("docs", "archive"):
            continue
            
        try:
            if item.is_dir():
                shutil.rmtree(str(item))
            else:
                item.unlink()
        except (OSError, PermissionError) as e:
            log_custom("RESULTS", f"Warning: Could not remove {item.name}", {"error": str(e)})
            
    # Ensure logs directory exists after cleanup
    LOGS_DIR.mkdir(parents=True, exist_ok=True)


def cleanup_workspace_for_fresh_start():
    """Delete everything in workspace except docs and dotfiles.
    This includes clearing all results, archives, and checkpoint files.
    Also explicitly deletes checkpoint_settings.json.
    """
    # Explicitly delete checkpoint_settings.json if it exists
    checkpoint_settings_path = WORKSPACE_DIR / "checkpoint_settings.json"
    if checkpoint_settings_path.exists():
        try:
            checkpoint_settings_path.unlink()
            log_custom("RESULTS", f"Deleted: {checkpoint_settings_path}")
        except (OSError, PermissionError) as e:
            log_custom("RESULTS", f"Warning: Could not delete {checkpoint_settings_path}", {"error": str(e)})
    
    for item in WORKSPACE_DIR.iterdir():
        # Skip dot-files/folders
        if item.name.startswith("."):
            continue
        # Only skip docs for fresh start - delete everything else including archive
        if item.name == "docs":
            continue
            
        try:
            if item.is_dir():
                shutil.rmtree(str(item))
            else:
                item.unlink()
        except (OSError, PermissionError) as e:
            log_custom("RESULTS", f"Warning: Could not remove {item.name}", {"error": str(e)})
            
    # Ensure logs directory exists after cleanup
    LOGS_DIR.mkdir(parents=True, exist_ok=True)


def archive_completed_run():
    """Archive workspace files including checkpoint to run_N folder on completion.
    
    This is called when a run completes successfully. It:
    1. Creates archive/run_N folder
    2. Copies all workspace items (including checkpoint files) to archive
    3. Deletes checkpoint files from workspace (but keeps them in archive)
    """
    archive_dir = WORKSPACE_DIR / "archive"
    
    checkpoint_settings = WORKSPACE_DIR / "checkpoint_settings.json"
    
    # Collect items to archive (everything except archive and most dotfiles)
    items_to_archive = [
        item for item in WORKSPACE_DIR.iterdir()
        if (not item.name.startswith('.') or item == checkpoint_settings) 
        and item.name not in IGNORED_ARCHIVE_NAMES
    ]
    
    if not items_to_archive:
        return
    
    archive_dir.mkdir(parents=True, exist_ok=True)
    
    # Find highest run number
    max_run_num = 0
    for item in archive_dir.iterdir():
        if item.is_dir() and item.name.startswith("run_"):
            try:
                max_run_num = max(max_run_num, int(item.name.split("_", 1)[1]))
            except (ValueError, IndexError):
                continue
    
    archive_path = archive_dir / f"run_{max_run_num + 1}"
    archive_path.mkdir(parents=True, exist_ok=True)
    
    # Archive items
    archived_items = []
    for item in items_to_archive:
        dest_path = archive_path / item.name
        try:
            if item.is_dir():
                shutil.copytree(str(item), str(dest_path), dirs_exist_ok=True)
            else:
                shutil.copy2(str(item), str(dest_path))
            archived_items.append(item.name)
        except (OSError, PermissionError) as e:
            log_custom("RESULTS", f"Warning: Could not archive {item.name}", {"error": str(e)})
    
    if archived_items:
        log_custom("RESULTS", f"Archived {len(archived_items)} item(s) to {archive_path}", {"items": archived_items})
    
    # Clean up workspace: remove archived items (except archive itself)
    for item in items_to_archive:
        try:
            if item.is_dir():
                shutil.rmtree(str(item))
            else:
                item.unlink()
        except (OSError, PermissionError) as e:
            log_custom("RESULTS", f"Warning: Could not remove {item.name}", {"error": str(e)})

    # Also ensure checkpoint sqlite files are removed even if they weren't in items_to_archive
    for suffix in ["", "-shm", "-wal"]:
        checkpoint_file = WORKSPACE_DIR / f"checkpoints.sqlite{suffix}"
        if checkpoint_file.exists():
            try:
                checkpoint_file.unlink()
            except (OSError, PermissionError) as e:
                log_custom("RESULTS", f"Warning: Could not remove {checkpoint_file.name}", {"error": str(e)})


def archive_exists_without_checkpoint():
    """Check if archive has runs and no active checkpoint exists.
    
    Returns True if:
    - archive folder exists with at least one run_N folder
    - no checkpoint file exists in workspace
    
    This indicates a previous run completed and was archived.
    """
    archive_dir = WORKSPACE_DIR / "archive"
    checkpoint_file = WORKSPACE_DIR / "checkpoints.sqlite"
    
    # Check that checkpoint doesn't exist
    if checkpoint_file.exists():
        return False
    
    # Check that archive exists and has run folders
    if not archive_dir.exists() or not archive_dir.is_dir():
        return False
    
    try:
        return any(
            item.is_dir() and item.name.startswith("run_")
            for item in archive_dir.iterdir()
        )
    except (OSError, PermissionError):
        return False

