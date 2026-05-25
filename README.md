<p align="center">
    <img src="logos/logo_text_fancy.png" alt="MOF-ChemUnity Logo" width="400"/>
</p>

<h1 align="center">Universal Autonomous System for Atomistic Research</h1>

A research-ready autonomous computational chemistry agentic system. QUASAR covers the full atomistic simulation pipeline with integrated tools including Quantum ESPRESSO, ASE, MACE, pymatgen, LAMMPS, RASPA3, ORCA, xTB, and RDKit. Currently optimised for Gemini models; other providers may not be fully functional. Broader compatibility coming in future releases.

## Documentation

- **GitHub Pages:** `https://fengxuyy.github.io/QUASAR-CHEM/`
- **Docs source:** [`docs/`](docs/)
- **Recommended entrypoint:** [`docs/index.md`](docs/index.md)

<details>
<summary><strong>Quick Start</strong></summary>

### 1. Install Docker or Singularity
- **Docker:** [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Mac/Windows) or [Docker Engine](https://docs.docker.com/engine/install/) (Linux).
- **HPC:** [Singularity](https://sylabs.io/singularity/) for cluster environments.

### 2. Pull the Image
Get the latest version from [Docker Hub](https://hub.docker.com/r/fengxuyang/quasar):
```bash
docker pull fengxuyang/quasar:<tag>
```

### 3. Launch
- **CLI** — Terminal-based interactive or batch runs; see [CLI](#cli) below.

</details>

<br>



<details>
<summary><strong>CLI</strong></summary>

Run QUASAR from the terminal: interactive conversation, one-off batch jobs, or inspection of run history.

#### Docker — Interactive
```bash
docker run -it --rm \
  -e MODEL_API_KEY=<api_key> \
  -e MODEL=<model_name> \
  -v "<workspace_path>:/workspace" \
  fengxuyang/quasar:<tag> \
  quasar
```

#### Docker — Batch (headless)
Pass a prompt as an argument for automated jobs:
```bash
docker run --rm \
  -e MODEL_API_KEY=<api_key> \
  -e MODEL=<model_name> \
  -v "<workspace_path>:/workspace" \
  fengxuyang/quasar:<tag> \
  quasar "Calculate the band gap of silicon"
```

#### Singularity (HPC) — Interactive
```bash
singularity exec --cleanenv \
  -B "<workspace_path>:/workspace" \
  --home "<workspace_path>:/workspace" \
  --env MODEL_API_KEY=<api_key> \
  --env MODEL=<model_name> \
  <tag>.sif quasar
```

#### Singularity (HPC) — Batch (headless)
```bash
singularity exec --cleanenv \
  -B "<workspace_path>:/workspace" \
  --home "<workspace_path>:/workspace" \
  --env MODEL_API_KEY=<api_key> \
  --env MODEL=<model_name> \
  <tag>.sif quasar "Your research prompt here"
```

#### `quasar history`
After a run (or when resuming from a checkpoint), the CLI can show **per-task run history** from the current workspace checkpoint. This is useful to review what the operator and evaluator did for each task without re-running.

- **Command:** `quasar history`
- **Requires:** A workspace with an existing checkpoint (from a current or past run).
- **Behavior:** Starts an interactive view that lists all tasks (e.g. `task_1`, `task_2`, …). Use ↑/↓ to select a task and Enter to open it. For the selected task you see the full step-by-step history: task description, operator tool calls (e.g. code snippets, file reads, searches), code outputs, and the evaluator’s summary for that task. Use ESC to go back to the task list; Ctrl+C or Ctrl+D to exit.

If no checkpoint exists, `quasar history` reports that you need to run `quasar` first or resume an interrupted session.

#### Interactive backslash commands
While using the interactive CLI, type `\` at the start of the input box to open the command picker. QUASAR CLI commands use the backslash prefix only:

| Command | Description |
| :--- | :--- |
| `\settings` | Open the system settings panel. |
| `\refresh` | Clear and redraw the CLI, then reload checkpoint state. |
| `\execution-overview` | Display the current or latest archived `execution_overview.md`. |
| `\usage-report` | Display the current or latest archived `usage_report.md`. |
| `\revert <task>` | Confirm and revert the active checkpoint/workspace to the start of a task, for example `\revert 2`. |

</details>

<br>

<details>
<summary><strong>Configuration</strong></summary>

Configure the system via environment variables:

| Variable | Description | Default |
| :--- | :--- | :--- |
| `MODEL` | **Required.** Model name. | - |
| `MODEL_API_KEY` | **Required.** Your API key (Gemini, Claude, OpenAI, etc.). | - |
| `OPENAI_API_BASE` | Base URL for OpenAI-compatible global endpoints. | - |
| `API_BASE_URL` | Alias for `OPENAI_API_BASE`. | - |
| `ACCURACY` | `eco` (fast), `standard` (research-grade), `pro` (maximum rigor), or `adaptive` (dynamic scaling). | `standard` |
| `GRANULARITY` | Workflow task breakdown level (`low`, `medium`, `high`, `adaptive`). | `adaptive` |
| `AUTO_IMPROVE_CYCLES` | Number of automatic auto-improve follow-up runs after a successful user-started run. | `0` |
| `CONTEXT_THRESHOLD` | Context compression trigger level: `low` = 20%, `medium` = 40%, `hard` = 60% of model context. | `medium` |
| `ENABLE_RAG` | Enable/disable documentation search. | `true` |
| `IF_RESTART` | Resume from the last checkpoint. | `false` |
| `PMG_MAPI_KEY` | Materials Project API key for `pymatgen`. | - |
| `NUM_CORES` | Override number of physical CPU cores for execution. | `Auto` |
| `AUTO_CONFIRM_PLAN` | Skip interactive plan confirmation for headless or batch runs. | unset |

Long-running Python check-ins are scheduled by the operator agent per tool call via
`execute_python(check_in_after=...)` and rescheduled after each check-in via
`continue_execution(next_check_in_after=...)`.

</details>

<br>

<details>
<summary><strong>Workspace Structure</strong></summary>

All outputs are saved within the mounted workspace directory:

```
workspace/
├── final_results/      # Final outputs and analysis from the current run
│   └── summary.md      # Results summary
├── quasar_logs/        # Execution logs, checkpoints, and usage reports
│   ├── usage_report.md # Token usage and cost breakdown
│   ├── execution_overview.md # High-level run summary
│   ├── input_messages.md # Input prompts sent to the agent
│   ├── conversation.md # Conversation history
│   ├── checkpoints.sqlite # Checkpoint database for resumption
│   ├── checkpoint_settings.json # Run settings and token stats
│   └── pending_execution.json # Interrupted execution recovery state
├── quasar_archive/     # Historical runs (preserved across runs)
│   ├── quasar_run_YYYYMMDD_HHMMSS_<id>/ # Completed run
│   │   ├── final_results/
│   │   ├── quasar_logs/
│   │   └── ...         # All workspace files from that run
│   └── quasar_run_.../ # Subsequent runs
└── docs/               # Downloaded documentation (preserved)
```

When a run completes:
1. All workspace files are copied to `quasar_archive/quasar_run_YYYYMMDD_HHMMSS_<id>/`
2. Checkpoint files are removed from the workspace
3. The `quasar_archive/` and `docs/` directories are preserved for future runs

</details>

<br>

<details>
<summary><strong>Restart Mechanism</strong></summary>

QUASAR automatically checkpoints progress during execution. To resume from the last checkpoint:

**Docker:**
```bash
docker run --rm -e IF_RESTART=true \
  -v "<workspace_path>:/workspace" \
  fengxuyang/quasar:<tag> quasar
```

**Singularity:**
```bash
singularity exec --cleanenv \
  --env IF_RESTART=true \
  -B "<workspace_path>:/workspace" \
  --home "<workspace_path>:/workspace" \
  <tag>.sif quasar
```

**When changing hardware** (e.g., moving to a different node or GPU):
1. Ensure the same workspace path is mounted
2. Set `IF_RESTART=true` to resume from the checkpoint
3. The system will continue from exactly where it left off

> **Note:** Checkpoints are stored in `quasar_logs/checkpoints.sqlite` within the workspace. Completed runs are archived to `quasar_archive/quasar_run_YYYYMMDD_HHMMSS_<id>/` with their checkpoint data preserved.

</details>

<br>

<details>
<summary><strong>Advanced Setup: Per-Agent Model Configuration</strong></summary>

By default, all agents (Strategist, Operator, Evaluator) use the same model set via `MODEL`. You can optionally assign a **different model, API key, and endpoint** to each agent.

#### Environment Variables

| Variable | Description |
| :--- | :--- |
| `STRATEGIST_MODEL` | Override model for the planning agent |
| `STRATEGIST_MODEL_API_KEY` | API key for the strategist model |
| `STRATEGIST_API_BASE_URL` | Custom API endpoint for the strategist |
| `OPERATOR_MODEL` | Override model for the execution agent |
| `OPERATOR_MODEL_API_KEY` | API key for the operator model |
| `OPERATOR_API_BASE_URL` | Custom API endpoint for the operator |
| `EVALUATOR_MODEL` | Override model for the evaluation agent |
| `EVALUATOR_MODEL_API_KEY` | API key for the evaluator model |
| `EVALUATOR_API_BASE_URL` | Custom API endpoint for the evaluator |
| `NUM_CORES` | Override the number of physical CPU cores |

All are **optional** — when unset, each agent falls back to the primary `MODEL`, `MODEL_API_KEY`, and `OPENAI_API_BASE` / `API_BASE_URL`.

</details>
