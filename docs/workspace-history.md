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
├── logs/
│   ├── usage_report.md
│   ├── execution_overview.md
│   ├── input_messages.md
│   └── conversation/
├── archive/
│   ├── run_1/
│   └── run_N/
├── docs/
├── .rag_index/
├── checkpoints.sqlite
├── checkpoint_settings.json
└── ...
```

## What Each Area Is For

| Path | Purpose |
| --- | --- |
| `final_results/` | Final user-facing outputs for the active run. |
| `logs/` | Run summaries, usage reports, input history, and conversation traces. |
| `archive/run_N/` | Historical snapshots of completed runs. |
| `docs/` | Downloaded documentation repositories used for local retrieval and manual inspection. |
| `.rag_index/` | Cached retrieval index and embedding resources. |
| `checkpoints.sqlite` | Active checkpoint database that powers resume and history features. |
| `checkpoint_settings.json` | Stored run settings and usage metadata used during resume and reporting. |

## What Gets Preserved

- `docs/` is preserved across normal cleanup and fresh starts
- `.rag_index/` and other dotfiles are preserved by the CLI cleanup commands
- `archive/` is preserved when you clear a checkpoint, but removed during a full fresh reset
- active checkpoint files stay in place until a run completes or you clear them

## Completion Behavior

When a run completes successfully, QUASAR archives the active workspace into `archive/run_N/` and removes checkpoint artifacts from the live workspace. That gives you a clean active area while keeping the finished run intact for inspection.

Archived runs can include:

- final results
- logs
- checkpoint-related sidecars
- generated files and intermediate outputs

## Interrupted Runs

An interrupted run behaves differently from a completed one:

- checkpoint files remain in the workspace
- the CLI exposes resume behavior
- settings are restored from checkpoint metadata
- the current run can continue without losing prior progress

## Cleanup Modes

The CLI cleanup commands operate on the live workspace only. They do not modify older archived runs unless you choose `--fresh`.

| Action | Keeps `docs/` | Keeps `archive/` | Keeps dotfiles | Keeps active checkpoint |
| --- | --- | --- | --- | --- |
| Resume | Yes | Yes | Yes | Yes |
| Clear checkpoint / `--clear` | Yes | Yes | Yes | No |
| Fresh start / `--fresh` | Yes | No | Yes | No |
| Completed run archive | Yes | Yes | Yes | No |

## History Surfaces

There are two main ways to inspect past work:

- the archived files under `workspace/archive/run_N/`, which preserve summaries, logs, traces, and generated outputs
- the **CLI `--history` command**, which lets you inspect checkpoint task history step by step

## A Practical Review Flow

For most runs, the fastest inspection sequence is:

1. Open `final_results/summary.md` for the user-facing conclusion.
2. Open `logs/execution_overview.md` when you want the high-level execution path.
3. Use `quasar --history` if you need per-task detail from the current checkpoint.
4. Open `archive/run_N/` when you want the full snapshot of a completed earlier run.

## Read-Only vs Editable Contexts

The live workspace is where active runs read and write files. Archived runs are intentionally treated as historical snapshots, which helps prevent accidental edits to past results while still making them easy to inspect.

<div class="callout callout-accent">
  <strong>Tip:</strong> if you are iterating on a workflow, clear the active checkpoint when you want a new live run but keep the archive. Reach for a full fresh start only when you intentionally want to delete previous run history.
</div>
