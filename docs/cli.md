---
title: CLI
description: Run QUASAR from the terminal.
section: Interface
lead: The CLI supports interactive work, headless prompts, checkpoint management, and run history browsing.
permalink: /cli/
---

## Core Usage

Install the Python package and launcher from PyPI:

```bash
pip install quasar-core
```

`quasar-core` ships the Python backend and the packaged `quasar` launcher. Node.js 18+ is still required at runtime for the current terminal UI.

```bash
quasar [prompt]
quasar --resume
quasar --clear
quasar --fresh
quasar --history
quasar --config [show|validate]
quasar --info
```

## Command Reference

| Command | What it does |
| --- | --- |
| `quasar` | Starts the interactive CLI run flow. |
| `quasar "..."` | Runs a direct prompt in headless mode. |
| `quasar --resume` | Resumes from an active checkpoint and forces restart semantics. |
| `quasar --clear` | Clears the active checkpoint and current workspace state, but keeps archived runs. |
| `quasar --fresh` | Clears current workspace state and archived runs, while preserving downloaded docs. |
| `quasar --history` | Opens an interactive per-task checkpoint history browser. |
| `quasar --config` | Shows current configuration values. |
| `quasar --config validate` | Verifies required configuration such as `MODEL_API_KEY`. |
| `quasar --info` | Prints system and environment context such as workspace path and platform. |

## Interactive vs Headless

Use interactive mode when you want a full terminal UI with agent updates, planning panels, and checkpoint prompts. Use headless mode when you want to pass a single prompt directly from scripts, CI jobs, or schedulers.

Examples:

```bash
quasar
quasar "Optimize the geometry of MOF-5 and summarize convergence behavior"
```

## Resume Rules

The CLI enforces a few guardrails:

- if `--resume` is set and no checkpoint exists, it exits with an error
- if a checkpoint exists and you try to start a new headless prompt without resume, it refuses to overwrite that state
- if you pass a prompt together with `--resume`, the prompt is ignored and the checkpoint is resumed

These checks prevent accidental loss of interrupted work.

## `quasar --history`

The history view is a checkpoint-aware browser for task-by-task inspection. It lets you:

- select `task_1`, `task_2`, and so on
- inspect operator tool calls and outputs
- review evaluator summaries
- move back to the task list with `Esc`
- exit with `Ctrl+C` or `Ctrl+D`

This is especially helpful when you need to understand exactly where a long research run failed or why an evaluation loop requested changes.

## `--clear` vs `--fresh`

These two commands are easy to confuse:

- `--clear` preserves `archive/` and `docs/`
- `--fresh` preserves only `docs/`

If you want to clean up an interrupted run but keep previous results, use `--clear`. If you want to wipe prior run history as well, use `--fresh`.

## Legacy `--web` Flag

Older docs and scripts may still reference `quasar --web`. That flag now exits with an error because browser UI support has been removed from the current CLI.
