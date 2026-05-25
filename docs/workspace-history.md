---
title: Workspace & History
description: How QUASAR stores outputs, checkpoints, archives, and documentation resources.
section: Results
lead: QUASAR treats the mounted workspace as the center of the run. Understanding that directory model makes restart, cleanup, and result review much easier.
permalink: /workspace-history/
---

## Workspace Layout

A typical workspace includes files like these:

```text
workspace/
├── final_results/
│   └── summary.md
├── quasar_logs/
│   ├── usage_report.md
│   ├── execution_overview.md
│   ├── input_messages.md
│   ├── conversation.md
│   ├── checkpoints.sqlite
│   ├── checkpoint_settings.json
│   └── pending_execution.json
├── quasar_archive/
│   ├── quasar_run_YYYYMMDD_HHMMSS_<id>/
│   └── quasar_run_.../
├── docs/
├── .rag_index/
└── ...
```

## What Each Area Is For

| Path | Purpose |
| --- | --- |
| `final_results/` | Final user-facing outputs for the active run. |
| `quasar_logs/` | Run summaries, usage reports, input history, conversation traces, checkpoint data, and pending execution state. |
| `quasar_archive/quasar_run_YYYYMMDD_HHMMSS_<id>/` | Historical snapshots of completed runs. |
| `docs/` | Downloaded documentation repositories used for local retrieval and manual inspection. |
| `.rag_index/` | Cached retrieval index and embedding resources. |
| `quasar_logs/checkpoints.sqlite` | Active checkpoint database that powers resume and history features. |
| `quasar_logs/checkpoint_settings.json` | Stored run settings and usage metadata used during resume and reporting. |
| `quasar_logs/pending_execution.json` | Recovery metadata for an interrupted Python execution. |

## What Gets Preserved

- `docs/` is preserved across normal cleanup and fresh starts
- `.rag_index/` and other dotfiles are preserved by the CLI cleanup commands
- `quasar_archive/` is preserved when you clear a checkpoint, but removed during a full fresh reset
- active checkpoint files stay in place until a run completes or you clear them

## Completion Behavior

When a run completes successfully, QUASAR archives the active workspace into `quasar_archive/quasar_run_YYYYMMDD_HHMMSS_<id>/` and removes checkpoint artifacts from the live workspace. That gives you a clean active area while keeping the finished run intact for inspection.

## Interrupted Runs

An interrupted run behaves differently from a completed one:

- checkpoint files remain in the workspace
- the CLI exposes resume behavior
- settings are restored from checkpoint metadata
- the current run can continue without losing prior progress

## Cleanup Modes

The CLI cleanup commands operate on the live workspace only. They do not modify older archived runs unless you choose `--fresh`.

| Action | Keeps `docs/` | Keeps `quasar_archive/` | Active checkpoint after action |
| --- | --- | --- | --- |
| Clear checkpoint / `--clear` | Yes | Yes | No |
| Fresh start / `--fresh` | Yes | No | No |
| Completed run archive | Yes | Yes | No in the live workspace; archived checkpoint data is preserved with the run. |
| Task revert / `\revert <task>` | Yes | Yes | Yes, rewound to the selected task |

## History Surfaces

There are three main ways to inspect past work:

- the archived files under `workspace/quasar_archive/quasar_run_YYYYMMDD_HHMMSS_<id>/`, which preserve summaries, logs, traces, and generated outputs
- the **CLI `--history` command**, which lets you inspect checkpoint task history step by step

## Reverting to a Task

When an active checkpoint exists, QUASAR can time-travel the run back to the start of a selected task. Use the interactive CLI command:

```bash
\revert 2
```

The revert operation prompts for confirmation, removes checkpoints after the selected task, deletes task folders from that task onward, clears stale pending execution state, and reloads the checkpoint view. It is intended for stopped or interrupted runs; the CLI refuses to revert while execution is running.
