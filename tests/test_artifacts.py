from src import results
from src.artifacts import (
    ARCHIVE_DIR_NAME,
    LOGS_DIR_NAME,
    display_archive_run_id,
    find_run_log_file,
    is_archive_run_name,
    iter_archive_run_dirs,
    latest_archive_run_dir,
)


def test_archive_completed_run_uses_unique_quasar_artifact_names(tmp_path, monkeypatch):
    monkeypatch.setattr(results, "WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr(results, "LOGS_DIR", tmp_path / LOGS_DIR_NAME)

    (tmp_path / "output.txt").write_text("ok", encoding="utf-8")
    logs_dir = tmp_path / LOGS_DIR_NAME
    logs_dir.mkdir()
    (logs_dir / "conversation.md").write_text("request", encoding="utf-8")
    (logs_dir / "checkpoints.sqlite").write_text("checkpoint", encoding="utf-8")
    (logs_dir / "checkpoint_settings.json").write_text("{}", encoding="utf-8")

    results.archive_completed_run()

    archive_root = tmp_path / ARCHIVE_DIR_NAME
    archived_runs = [item for item in archive_root.iterdir() if item.is_dir()]

    assert len(archived_runs) == 1
    archived_run = archived_runs[0]
    assert is_archive_run_name(archived_run.name)
    assert archived_run.name.startswith("quasar_run_")
    assert (archived_run / "output.txt").read_text(encoding="utf-8") == "ok"
    assert (archived_run / LOGS_DIR_NAME / "conversation.md").exists()
    assert (archived_run / LOGS_DIR_NAME / "checkpoints.sqlite").exists()
    assert (archived_run / LOGS_DIR_NAME / "checkpoint_settings.json").exists()
    assert not (tmp_path / "output.txt").exists()
    assert not (tmp_path / LOGS_DIR_NAME).exists()


def test_archive_helpers_sort_unique_run_names(tmp_path):
    older = tmp_path / ARCHIVE_DIR_NAME / "quasar_run_20260519_103011_a1b2c3"
    newer = tmp_path / ARCHIVE_DIR_NAME / "quasar_run_20260520_081500_d4e5f6"
    older.mkdir(parents=True)
    newer.mkdir(parents=True)

    runs = iter_archive_run_dirs(tmp_path)

    assert runs == [older, newer]
    assert latest_archive_run_dir(tmp_path) == newer
    assert display_archive_run_id(older.name) == "Run 2026-05-19 10:30:11"


def test_find_run_log_file_reads_quasar_logs_only(tmp_path):
    run_path = tmp_path / ARCHIVE_DIR_NAME / "quasar_run_20260519_103011_a1b2c3"
    quasar_logs = run_path / LOGS_DIR_NAME
    quasar_logs.mkdir(parents=True)
    (quasar_logs / "conversation.md").write_text("new", encoding="utf-8")

    assert find_run_log_file(run_path, "conversation.md") == quasar_logs / "conversation.md"
