---
title: CLI
description: Run QUASAR from the terminal.
section: Interface
lead: The CLI supports interactive work, checkpoint management, and run history browsing.
permalink: /cli/
---

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

## Interactive run flow

After you submit a request and confirm settings, the **Strategist** produces an execution plan. Before the **Operator** starts, the CLI enters a **plan confirmation** step: you can approve the plan, **decline** it (the run stops in a controlled way), or **revise** it by sending feedback so the Strategist can adjust the plan. This human-in-the-loop gate applies to normal interactive runs.

Automatic follow-up runs driven by `AUTO_IMPROVE_CYCLES` confirm the plan without prompting. For unattended or scripted sessions where you still want the graph to proceed without blocking, set `AUTO_CONFIRM_PLAN` to `true` (see [Configuration]({{ '/configuration/' | relative_url }})).