---
title: CLI
description: Run QUASAR from the terminal.
section: Interface
lead: The CLI supports interactive work, headless prompts, checkpoint management, and run history browsing.
permalink: /cli/
---

## Install the Launcher

Install the Python package and launcher from PyPI:

```bash
pip install quasar-core
```

`quasar-core` ships the Python backend and the packaged `quasar` launcher. Node.js 18+ is still required at runtime for the current terminal UI.

## Core Usage

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
| `quasar --fresh` | Clears current workspace state and archived runs, while preserving downloaded docs and dotfiles. |
| `quasar --history` | Opens an interactive per-task checkpoint history browser. |
| `quasar --config` | Shows current configuration values. |
| `quasar --config validate` | Verifies required configuration such as `MODEL_API_KEY`. |
| `quasar --info` | Prints system and environment context such as workspace path and platform. |
| `quasar --no-rag "..."` | Runs without documentation retrieval for that specific prompt. |

## Interactive vs Headless

Use interactive mode when you want a full terminal UI with agent updates, planning panels, and checkpoint prompts. Use headless mode when you want to pass a single prompt directly from scripts, CI jobs, or schedulers.

Examples:

```bash
quasar
quasar "Optimize the geometry of MOF-5 and summarize convergence behavior"
```

<div class="card-grid">
  <div class="step-card">
    <p class="mini-label">Interactive</p>
    <h3>Use <code>\settings</code> for Missing Values</h3>
    <p>If <code>MODEL</code> or <code>MODEL_API_KEY</code> are missing, the interactive CLI can open the settings panel before the run starts.</p>
  </div>
  <div class="step-card">
    <p class="mini-label">Headless</p>
    <h3>Best for Automation</h3>
    <p>Pass a full prompt directly when you want one-shot execution from scripts, containers, or scheduler jobs.</p>
  </div>
  <div class="step-card">
    <p class="mini-label">Config</p>
    <h3>Inspect Runtime State</h3>
    <p>Use <code>quasar --config</code> and <code>quasar --info</code> when you want to sanity-check environment values before launching a large run.</p>
  </div>
</div>

## Common Launch Patterns

Interactive session:

```bash
quasar
```

Headless run:

```bash
quasar "Optimize the geometry of MOF-5 and summarize convergence behavior"
```

Resume an interrupted run:

```bash
quasar --resume
```

Disable RAG for one run:

```bash
quasar --no-rag "Summarize the existing files in this workspace and propose the next simulation step"
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

## `quasar --config` and `quasar --info`

These commands are lightweight sanity checks:

- `quasar --config` shows the currently resolved runtime configuration
- `quasar --config validate` checks whether required values such as `MODEL_API_KEY` are present
- `quasar --info` prints the workspace path, platform, architecture, CPU count, and Node version

## `--clear` vs `--fresh`

These two commands are easy to confuse:

- `--clear` preserves `archive/`, `docs/`, and dotfiles
- `--fresh` preserves `docs/` and dotfiles, but removes archived runs

If you want to clean up an interrupted run but keep previous results, use `--clear`. If you want to wipe prior run history as well, use `--fresh`.

## Legacy `--web` Flag

Older docs and scripts may still reference `quasar --web`. That flag now exits with an error because browser UI support has been removed from the current CLI.
