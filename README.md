<p align="center">
    <img src="logos/logo_text_fancy.png" alt="MOF-ChemUnity Logo" width="400"/>
</p>

<h1 align="center">Quantum Universal Autonomous System for Atomistic Research</h1>

<p align="center">
  <a href="https://pypi.org/project/quasar-core/">
    <img src="https://img.shields.io/pypi/v/quasar-core?style=for-the-badge&logo=pypi&logoColor=white" alt="PyPI version" />
  </a>
  <img src="https://img.shields.io/pypi/pyversions/quasar-core?style=for-the-badge&logo=python&logoColor=white" alt="Python versions" />
  <img src="https://img.shields.io/pypi/l/quasar-core?style=for-the-badge" alt="PyPI license" />
</p>

A research-ready autonomous computational chemistry agentic system. QUASAR covers the full atomistic simulation pipeline with integrated tools including Density Functional Theory (DFT), Machine Learning Potentials (MLP), Molecular Dynamics (MD), and Grand Canonical Monte Carlo (GCMC), allowing scientists to rapidly iterate on hypotheses, explore large design spaces, and accelerate the discovery of novel materials and phenomena.

Documentation: [QUASAR-CHEM Docs](https://fengxuyy.github.io/QUASAR/)

<details>
<summary><strong>New Features</strong></summary>

- Dedicated GitHub Pages documentation for setup, CLI usage, configuration, architecture, and workspace history.
- Expanded CLI commands for resume, cleanup, history browsing, configuration validation, and system info.
- Interactive `\settings` panel for filling in required runtime settings from inside the terminal UI.
- Checkpoint-aware history inspection plus separate `--clear` and `--fresh` cleanup modes.
- Context compression controls via `CONTEXT_THRESHOLD` and automatic follow-up runs via `AUTO_IMPROVE_CYCLES`.
- Per-agent model overrides for strategist, operator, and evaluator workflows.
- Improved parallel execution of tool calls for enhanced performance.

</details>

<br>

<details>
<summary><strong>Quick Start</strong></summary>

### 1. Choose how to run QUASAR
- **Containers (recommended)** — Use the Docker or Singularity image for one-step setup.
- **Local Deployment** — Install QUASAR and simulation engines (QE, LAMMPS, RASPA3, etc.) on your machine via conda and pip; see [Local Deployment](#local-deployment). This option is less recommended because dependency conflicts are more likely, and agent-executed commands run directly on your host environment.

### 2. Install Docker or Singularity
- **Docker:** [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Mac/Windows) or [Docker Engine](https://docs.docker.com/engine/install/) (Linux).
- **HPC:** Singularity for cluster environments.

### 3. Pull the Image
Get the latest version from [Docker Hub](https://hub.docker.com/r/fengxuyang/quasar):

**Docker:**
```bash
docker pull fengxuyang/quasar:<tag>
```

**Singularity (HPC):** Convert the Docker image to a `.sif` file. Build directly from Docker Hub:
```bash
singularity build quasar.sif docker://fengxuyang/quasar:<tag>
```

### 4. Choose Your Interface
- **CLI** — Terminal-based interactive interface with live agent updates, checkpoint prompts, and the built-in `\settings` panel; see [CLI](#cli) below.

- **Batch** — Headless automated execution for background or HPC tasks; see [Batch Jobs](#batch-jobs) below.

</details>

<br>

<details>
<summary id="local-deployment"><strong>Local Deployment</strong></summary>

Run QUASAR on your machine (without Docker/Singularity). Simulation engines such as Quantum ESPRESSO, LAMMPS, and RASPA3 need to be pre-installed. Here's an example using conda.

### 1. Prerequisites
- [Miniconda](https://docs.conda.io/en/latest/miniconda.html) or [Anaconda](https://www.anaconda.com/)
- [Node.js](https://nodejs.org/) 18+ (required to run the QUASAR CLI)

### 2. Create conda environment with simulation tools
```bash
conda create -n quasar python=3.11 -y
conda activate quasar

# Simulation engines (conda-forge)
conda install -c conda-forge qe lammps raspa3 raspalib -y
```

### 3. Install QUASAR from PyPI
```bash
pip install --upgrade pip
pip install quasar-core
```

`quasar-core` ships the Python backend and the packaged `quasar` launcher. Interactive runs can fill in missing `MODEL` and `MODEL_API_KEY` values from the CLI via `\settings`; headless runs should still export them before launch.
</details>

<br>


<details>
<summary id="cli"><strong>CLI</strong></summary>

Run QUASAR interactively from the terminal, launch headless prompts, or inspect checkpoint state and task history.

#### Docker
```bash
docker run -it --rm \
  -v "<workspace_path>:/workspace" \
  fengxuyang/quasar:<tag> \
  quasar
```

#### Singularity (HPC)
```bash
singularity exec --cleanenv \
  -B "<workspace_path>:/workspace" \
  --home "<workspace_path>:/workspace" \
  <tag>.sif quasar
```

#### Local Deployment
```bash
export WORKSPACE_DIR=<workspace_directory>
quasar
```

Interactive sessions can open the built-in `\settings` panel before the first prompt if required settings such as `MODEL` or `MODEL_API_KEY` are missing. For scripted or headless runs, provide required environment variables up front.

#### Command Reference

| Command | What it does |
| :--- | :--- |
| `quasar` | Starts the interactive terminal UI. |
| `quasar "..."` | Runs a direct prompt in headless mode. |
| `quasar --resume` | Resumes the active checkpoint. |
| `quasar --clear` | Clears the active checkpoint and current workspace state, while preserving `archive/` and `docs/`. |
| `quasar --fresh` | Clears the current workspace state and archived runs, while preserving `docs/` and hidden caches such as `.rag_index/`. |
| `quasar --history` | Opens the interactive per-task checkpoint history browser. |
| `quasar --config` | Shows the current configuration values. |
| `quasar --config validate` | Verifies required configuration such as `MODEL_API_KEY`. |
| `quasar --info` | Prints system and workspace information. |

Add `--no-rag` to a run command when you want to disable documentation retrieval for that session.

#### `quasar --history`
After a run (or when resuming from a checkpoint), the CLI can show **per-task run history** from the current workspace checkpoint. This is useful to review what the operator and evaluator did for each task without re-running.

- **Command:** `quasar --history`
- **Requires:** A workspace with an existing checkpoint (from a current or past run).
- **Behaviour:** Starts an interactive view that lists all tasks (e.g. `task_1`, `task_2`, …). Use ↑/↓ to select a task and Enter to open it. For the selected task you see the full step-by-step history: task description, operator tool calls (e.g. code snippets, file reads, searches), code outputs, and the evaluator’s summary for that task. Use ESC to go back to the task list; Ctrl+C or Ctrl+D to exit.

If no checkpoint exists, `quasar --history` reports that you need to run `quasar` first or resume an interrupted session. The CLI also prevents a new direct prompt from overwriting an existing checkpoint unless you explicitly resume or clear it first.

The legacy browser-based `quasar --web` mode has been removed from the current CLI.

</details>

<br>

<details>
<summary id="batch-jobs"><strong>Batch Jobs</strong></summary>

Automate your research with one-off batch jobs for headless execution. Pass a prompt as an argument for automated jobs:

#### Docker
```bash
docker run --rm \
  -e MODEL_API_KEY=<api_key> \
  -e MODEL=<model_name> \
  -v "<workspace_path>:/workspace" \
  fengxuyang/quasar:<tag> \
  quasar "Calculate the band structure of silicon"
```

#### Singularity (HPC)
```bash
singularity exec --cleanenv \
  -B "<workspace_path>:/workspace" \
  --home "<workspace_path>:/workspace" \
  --env MODEL_API_KEY=<api_key> \
  --env MODEL=<model_name> \
  <tag>.sif quasar "Your research prompt here"
```

#### Local Deployment
```bash
export MODEL_API_KEY=<api_key>
export MODEL=<model_name>
export WORKSPACE_DIR=<workspace_directory>
quasar "Your research prompt here"
```
</details>

<br>

<details>
<summary><strong>Configuration</strong></summary>

Configure the system via environment variables and the interactive CLI settings panel:

| Variable | Description | Default |
| :--- | :--- | :--- |
| `MODEL` | **Required.** Model name. | - |
| `MODEL_API_KEY` | **Required.** Your API key (Gemini, Claude, OpenAI, etc.). | - |
| `OPENAI_API_BASE` | Optional base URL for OpenAI-compatible endpoints. | - |
| `ACCURACY` | Planning/execution rigor: `eco`, `standard`, `pro`. | `standard` |
| `GRANULARITY` | Workflow task breakdown level (`low`, `medium`, `high`). | `medium` |
| `CONTEXT_THRESHOLD` | Context-compression trigger level (`low`, `medium`, `high`). | `medium` |
| `ENABLE_RAG` | Enable/disable documentation search. | `true` |
| `CHECK_INTERVAL`| Minutes between LLM check-ins for long Python runs. | `15` |
| `AUTO_IMPROVE_CYCLES` | Automatic auto-improve follow-up runs after a successful user-started run. | `0` |
| `NUM_CORES` | Override detected physical core count. | `Auto` |
| `PMG_MAPI_KEY` | Materials Project API key for `pymatgen`. | - |
| `HF_TOKEN` | Optional Hugging Face token for authenticated RAG/index access. | - |
| `IF_RESTART` | Resume from the last checkpoint. | `false` |

Interactive CLI users can inspect or edit these values from `\settings`; headless users should export them before launch.

#### Per-Agent Model Overrides

| Agent | Model | API key | Base URL |
| :--- | :--- | :--- | :--- |
| Strategist | `STRATEGIST_MODEL` | `STRATEGIST_MODEL_API_KEY` | `STRATEGIST_API_BASE_URL` |
| Operator | `OPERATOR_MODEL` | `OPERATOR_MODEL_API_KEY` | `OPERATOR_API_BASE_URL` |
| Evaluator | `EVALUATOR_MODEL` | `EVALUATOR_MODEL_API_KEY` | `EVALUATOR_API_BASE_URL` |


</details>

<br>

<details>
<summary><strong>Workspace Structure</strong></summary>

All outputs are saved within the mounted workspace directory:

```
workspace/
├── final_results/      # Final outputs and analysis from the current run
│   └── summary.md      # Results summary
├── logs/               # Execution logs and usage reports
│   ├── usage_report.md # Token usage and cost breakdown
│   ├── execution_overview.md # High-level run summary
│   ├── input_messages.md # Input prompts sent to the agent
│   └── conversation/   # Conversation history
├── archive/            # Historical runs (preserved across normal cleanup)
│   ├── run_1/          # First completed run
│   └── run_N/          # Subsequent runs
├── docs/               # Downloaded documentation (preserved)
├── .rag_index/         # Cached RAG index and embeddings cache (preserved as a dot-directory)
├── checkpoints.sqlite  # Checkpoint database for resumption
├── checkpoint_settings.json  # Run settings and token stats
└── ...
```

When a run completes:
1. All workspace files are copied to `archive/run_N/`
2. Checkpoint files are removed from the workspace
3. The `archive/`, `docs/`, and hidden cache directories such as `.rag_index/` remain available for future runs

Cleanup modes:
1. `quasar --clear` removes the active checkpoint and current workspace state, but keeps `archive/`, `docs/`, and dot-directories.
2. `quasar --fresh` removes the active workspace state and archived runs, but still keeps `docs/` and dot-directories.

</details>

<br>

<details>
<summary><strong>Restart</strong></summary>

QUASAR automatically checkpoints progress during execution. To resume from the last checkpoint, use `quasar --resume` or the legacy `IF_RESTART=true` environment variable.

**Docker:**
```bash
docker run --rm \
  -v "<workspace_path>:/workspace" \
  fengxuyang/quasar:<tag> \
  quasar --resume
```

**Singularity:**
```bash
singularity exec --cleanenv \
  -B "<workspace_path>:/workspace" \
  --home "<workspace_path>:/workspace" \
  <tag>.sif quasar --resume
```

**Local Deployment:**
```bash
export MODEL_API_KEY=<api_key>
export MODEL=<model_name>
export WORKSPACE_DIR=<workspace_directory>
quasar --resume
```

Checkpoint metadata restores non-secret settings such as model, accuracy, granularity, and RAG options. API keys should still be supplied through environment variables or the interactive `\settings` panel before resuming work.

</details>

<br>

<details>
<summary><strong>Acknowledgements</strong></summary>

QUASAR is built upon a foundation of powerful open-source tools and research. We gratefully acknowledge the following projects: Quantum ESPRESSO, ASE, MACE, pymatgen, LAMMPS, and RASPA3.

</details>

<br>

<details>
<summary><strong>Citation</strong></summary>

If you find QUASAR useful for your research, please cite our benchmark paper:

> Yang, Fengxu, and Jack D. Evans. **"QUASAR: A Universal Autonomous System for Atomistic Simulation and a Benchmark of Its Capabilities."** *arXiv:2602.00185*, 30 Jan. 2026. [https://doi.org/10.48550/arXiv.2602.00185](https://doi.org/10.48550/arXiv.2602.00185)

```bibtex
@misc{yang2026quasar,
      title={QUASAR: A Universal Autonomous System for Atomistic Simulation and a Benchmark of Its Capabilities}, 
      author={Fengxu Yang and Jack D. Evans},
      year={2026},
      eprint={2602.00185},
      archivePrefix={arXiv},
      primaryClass={physics.chem-ph},
      url={https://arxiv.org/abs/2602.00185}, 
}
```

</details>

<br>

<details>
<summary><strong>Contact</strong></summary>

We are happy to collaborate. For inquiries, advanced features, beta access, or partnership ideas, please reach out to: [j.evans@adelaide.edu.au](mailto:j.evans@adelaide.edu.au)


</details>
