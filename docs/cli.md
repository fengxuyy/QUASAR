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