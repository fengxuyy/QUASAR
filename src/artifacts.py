"""Names and helpers for QUASAR-owned workspace artifacts."""

from __future__ import annotations

import re
import secrets
from datetime import datetime
from pathlib import Path

ARCHIVE_DIR_NAME = "quasar_archive"
LOGS_DIR_NAME = "quasar_logs"
CHECKPOINT_DB_NAME = "checkpoints.sqlite"
CHECKPOINT_SETTINGS_NAME = "checkpoint_settings.json"
PENDING_EXECUTION_NAME = "pending_execution.json"
CHECKPOINT_DB_SUFFIXES = ("", "-shm", "-wal")
LEGACY_RUNTIME_ARTIFACT_NAMES = (
    *(f"{CHECKPOINT_DB_NAME}{suffix}" for suffix in CHECKPOINT_DB_SUFFIXES),
    CHECKPOINT_SETTINGS_NAME,
    PENDING_EXECUTION_NAME,
)

RUN_ID_PATTERN = re.compile(
    r"^quasar_run_(?P<date>\d{8})_(?P<time>\d{6})_(?P<token>[0-9a-f]{6})(?:_(?P<counter>\d+))?$"
)


def get_archive_dir(workspace_dir: Path) -> Path:
    return workspace_dir / ARCHIVE_DIR_NAME


def get_logs_dir(workspace_dir: Path) -> Path:
    return workspace_dir / LOGS_DIR_NAME


def get_checkpoint_db_path(workspace_dir: Path) -> Path:
    return get_logs_dir(workspace_dir) / CHECKPOINT_DB_NAME


def get_checkpoint_sidecar_paths(workspace_dir: Path) -> list[Path]:
    logs_dir = get_logs_dir(workspace_dir)
    return [logs_dir / f"{CHECKPOINT_DB_NAME}{suffix}" for suffix in CHECKPOINT_DB_SUFFIXES]


def get_checkpoint_settings_path(workspace_dir: Path) -> Path:
    return get_logs_dir(workspace_dir) / CHECKPOINT_SETTINGS_NAME


def get_pending_execution_path(workspace_dir: Path) -> Path:
    return get_logs_dir(workspace_dir) / PENDING_EXECUTION_NAME


def migrate_legacy_runtime_artifacts(workspace_dir: Path) -> None:
    """Move pre-quasar_logs runtime artifacts into quasar_logs when possible."""

    logs_dir = get_logs_dir(workspace_dir)
    logs_dir.mkdir(parents=True, exist_ok=True)

    for artifact_name in LEGACY_RUNTIME_ARTIFACT_NAMES:
        legacy_path = workspace_dir / artifact_name
        target_path = logs_dir / artifact_name
        if not legacy_path.exists():
            continue
        try:
            if target_path.exists():
                legacy_path.unlink()
            else:
                legacy_path.replace(target_path)
        except (OSError, PermissionError):
            pass


def is_archive_run_name(name: str) -> bool:
    return bool(RUN_ID_PATTERN.match(name))


def iter_archive_run_dirs(workspace_dir: Path) -> list[Path]:
    archive_dir = get_archive_dir(workspace_dir)
    if not archive_dir.exists() or not archive_dir.is_dir():
        return []
    try:
        runs = [
            item
            for item in archive_dir.iterdir()
            if item.is_dir() and is_archive_run_name(item.name)
        ]
    except (OSError, PermissionError):
        return []
    return sorted(runs, key=archive_run_sort_key)


def has_archive_runs(workspace_dir: Path) -> bool:
    return bool(iter_archive_run_dirs(workspace_dir))


def make_archive_run_id(now: datetime | None = None, token: str | None = None) -> str:
    timestamp = (now or datetime.now()).strftime("%Y%m%d_%H%M%S")
    unique_token = token or secrets.token_hex(3)
    return f"quasar_run_{timestamp}_{unique_token}"


def create_archive_run_path(workspace_dir: Path) -> Path:
    """Create and return a collision-resistant archive run directory."""

    archive_dir = get_archive_dir(workspace_dir)
    archive_dir.mkdir(parents=True, exist_ok=True)

    base_run_id = make_archive_run_id()
    for attempt in range(100):
        run_id = base_run_id if attempt == 0 else f"{base_run_id}_{attempt + 1}"
        archive_path = archive_dir / run_id
        try:
            archive_path.mkdir(parents=True, exist_ok=False)
            return archive_path
        except FileExistsError:
            continue

    raise FileExistsError(f"Could not create a unique archive run directory under {archive_dir}")


def archive_run_sort_key(path: Path) -> tuple[int, str, int, str]:
    """Stable ordering for archive run ids."""

    name = path.name
    if match := RUN_ID_PATTERN.match(name):
        counter = int(match.group("counter") or 0)
        return (1, f"{match.group('date')}{match.group('time')}", counter, match.group("token"))
    return (0, "", 0, name)


def latest_archive_run_dir(workspace_dir: Path) -> Path | None:
    runs = iter_archive_run_dirs(workspace_dir)
    return runs[-1] if runs else None


def find_run_log_file(run_path: Path, filename: str) -> Path | None:
    """Find a log file in a run's QUASAR log folder."""

    candidate = run_path / LOGS_DIR_NAME / filename
    return candidate if candidate.exists() else None


def display_archive_run_id(run_id: str) -> str:
    if match := RUN_ID_PATTERN.match(run_id):
        date = match.group("date")
        time = match.group("time")
        return (
            f"Run {date[:4]}-{date[4:6]}-{date[6:8]} "
            f"{time[:2]}:{time[2:4]}:{time[4:6]}"
        )
    return run_id
