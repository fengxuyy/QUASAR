"""Results management and archiving."""

import shutil

from .tools.base import WORKSPACE_DIR, LOGS_DIR
from .debug_logger import log_custom
from .artifacts import (
    ARCHIVE_DIR_NAME,
    create_archive_run_path,
    get_checkpoint_db_path,
    get_checkpoint_settings_path,
    get_checkpoint_sidecar_paths,
    has_archive_runs,
    migrate_legacy_runtime_artifacts,
)

IGNORED_ARCHIVE_NAMES = {ARCHIVE_DIR_NAME, "docs"}


def setup_final_results_folder():
    """Archive workspace files to a unique run folder and create final_results."""
    final_results_dir = WORKSPACE_DIR / "final_results"
    
    items_to_archive = [
        item for item in WORKSPACE_DIR.iterdir()
        if not item.name.startswith('.') and item.name not in IGNORED_ARCHIVE_NAMES
    ]
    
    if not items_to_archive:
        final_results_dir.mkdir(parents=True, exist_ok=True)
        return
    
    archive_path = create_archive_run_path(WORKSPACE_DIR)
    
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
    """Delete everything in workspace except docs, archives, and dotfiles.
    This clears current results and checkpoints but preserves archived runs.
    Also explicitly deletes checkpoint_settings.json.
    """
    # Explicitly delete checkpoint_settings.json if it exists
    migrate_legacy_runtime_artifacts(WORKSPACE_DIR)
    checkpoint_settings_path = get_checkpoint_settings_path(WORKSPACE_DIR)
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
        # Skip docs and archives - only delete current workspace files
        if item.name in ("docs", ARCHIVE_DIR_NAME):
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
    migrate_legacy_runtime_artifacts(WORKSPACE_DIR)
    checkpoint_settings_path = get_checkpoint_settings_path(WORKSPACE_DIR)
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
    """Archive workspace files including checkpoint to a unique folder on completion.
    
    This is called when a run completes successfully. It:
    1. Creates a unique archive run folder
    2. Copies all workspace items (including checkpoint files) to archive
    3. Deletes checkpoint files from workspace (but keeps them in archive)
    """
    migrate_legacy_runtime_artifacts(WORKSPACE_DIR)
    checkpoint_settings = get_checkpoint_settings_path(WORKSPACE_DIR)
    
    # Collect items to archive (everything except archive and most dotfiles)
    items_to_archive = [
        item for item in WORKSPACE_DIR.iterdir()
        if (not item.name.startswith('.') or item == checkpoint_settings) 
        and item.name not in IGNORED_ARCHIVE_NAMES
    ]
    
    if not items_to_archive:
        return
    
    archive_path = create_archive_run_path(WORKSPACE_DIR)
    
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
    for checkpoint_file in get_checkpoint_sidecar_paths(WORKSPACE_DIR):
        if checkpoint_file.exists():
            try:
                checkpoint_file.unlink()
            except (OSError, PermissionError) as e:
                log_custom("RESULTS", f"Warning: Could not remove {checkpoint_file.name}", {"error": str(e)})


def archive_exists_without_checkpoint():
    """Check if archive has runs and no active checkpoint exists.
    
    Returns True if:
    - archive folder exists with at least one run folder
    - no checkpoint file exists in workspace
    
    This indicates a previous run completed and was archived.
    """
    migrate_legacy_runtime_artifacts(WORKSPACE_DIR)
    checkpoint_file = get_checkpoint_db_path(WORKSPACE_DIR)
    
    # Check that checkpoint doesn't exist
    if checkpoint_file.exists():
        return False
    
    try:
        return has_archive_runs(WORKSPACE_DIR)
    except (OSError, PermissionError):
        return False
