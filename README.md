<p align="center">
    <img src="logos/logo_text_fancy.png" alt="MOF-ChemUnity Logo" width="400"/>
</p>

<h1 align="center">Quantum Universal Autonomous System for Atomistic Research</h1>

A research-ready autonomous computational chemistry agentic system. QUASAR covers the full atomistic simulation pipeline with integrated tools including Density Functional Theory (DFT), Machine Learning Potentials (MLP), Molecular Dynamics (MD), and Grand Canonical Monte Carlo (GCMC), allowing scientists to rapidly iterate on hypotheses, explore large design spaces, and accelerate the discovery of novel materials and phenomena.

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

**Singularity (HPC):** Convert the Docker image to a `.sif` file. Either build directly from Docker Hub:
```bash
singularity build quasar_<tag>.sif docker://fengxuyang/quasar:<tag>
```

### 4. Choose Your Interface
- **CLI** — Terminal-based interactive interface with essential functionalities; see [CLI](#cli) below.

- **Batch** — Headless automated execution for background or HPC tasks; see [Batch Jobs](#batch-jobs) below.

- **Web** — A premium web-based experience offering advanced usage, fine-grained control, and rich visualisation; currently in private beta, contact us at [j.evans@adelaide.edu.au](mailto:j.evans@adelaide.edu.au) for early access.

</details>

<br>

<details>
<summary id="local-deployment"><strong>Local Deployment</strong></summary>

Run QUASAR on your machine (without Docker/Singularity). Simulation engines (Quantum ESPRESSO, LAMMPS, RASPA3) needs to be pre-installed. Here's an example using conda.

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

### 4. Set required environment variables
```bash
export MODEL_API_KEY=<api_key>
export MODEL=<model_name>
export WORKSPACE_DIR=<workspace_directory>
```

### 5. Run QUASAR
```bash
quasar
```
More details please refer to CLI and Batch 
</details>

<br>


<details>
<summary id="cli"><strong>CLI</strong></summary>

Run QUASAR interactively from the terminal or inspect run history.

#### Docker
```bash
docker run -it --rm \
  -e MODEL_API_KEY=<api_key> \
  -e MODEL=<model_name> \
  -v "<workspace_path>:/workspace" \
  fengxuyang/quasar:<tag> \
  quasar
```

#### Singularity (HPC)
```bash
singularity exec --cleanenv \
  -B "<workspace_path>:/workspace" \
  --home "<workspace_path>:/workspace" \
  --env MODEL_API_KEY=<api_key> \
  --env MODEL=<model_name> \
  <tag>.sif quasar
```

#### Local Deployment
```bash
export MODEL_API_KEY=<api_key>
export MODEL=<model_name>
export WORKSPACE_DIR=<workspace_directory>
quasar
```

#### `quasar history`
After a run (or when resuming from a checkpoint), the CLI can show **per-task run history** from the current workspace checkpoint. This is useful to review what the operator and evaluator did for each task without re-running.

- **Command:** `quasar history`
- **Requires:** A workspace with an existing checkpoint (from a current or past run).
- **Behaviour:** Starts an interactive view that lists all tasks (e.g. `task_1`, `task_2`, …). Use ↑/↓ to select a task and Enter to open it. For the selected task you see the full step-by-step history: task description, operator tool calls (e.g. code snippets, file reads, searches), code outputs, and the evaluator’s summary for that task. Use ESC to go back to the task list; Ctrl+C or Ctrl+D to exit.

If no checkpoint exists, `quasar history` reports that you need to run `quasar` first or resume an interrupted session.

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

Configure the system via environment variables (Web and CLI):

| Variable | Description | Default |
| :--- | :--- | :--- |
| `MODEL_API_KEY` | **Required.** Your API key (Gemini, Claude, OpenAI, etc.). | - |
| `MODEL` | **Required.** Model name. | - |
| `ACCURACY` | `eco` (fast/balanced) or `pro` (maximum rigor). | `eco` |
| `GRANULARITY` | Workflow task breakdown level (`low`, `medium`, `high`). | `medium` |
| `ENABLE_RAG` | Enable/disable documentation search. | `true` |
| `IF_RESTART` | Resume from the last checkpoint. | `false` |
| `PMG_MAPI_KEY` | Materials Project API key for `pymatgen`. | - |
| `CHECK_INTERVAL`| Minutes between LLM check-ins for long Python runs. | `15` |


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
│   ├── overview.md     # High-level run summary
│   ├── input_messages.md # Input prompts sent to the agent
│   └── conversation/   # Conversation history
├── checkpoints.sqlite  # Checkpoint database for resumption
├── checkpoint_settings.json  # Run settings and token stats
├── archive/            # Historical runs (preserved across runs)
│   ├── run_1/          # First completed run
│   │   ├── final_results/
│   │   ├── logs/
│   │   └── ...         # All workspace files from that run
│   └── run_N/          # Subsequent runs
└── docs/               # Downloaded documentation (preserved)
```

When a run completes:
1. All workspace files are copied to `archive/run_N/`
2. Checkpoint files are removed from the workspace
3. The `archive/` and `docs/` directories are preserved for future runs

</details>

<br>

<details>
<summary><strong>Restart</strong></summary>

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

**Local Deployment:**
```bash
export MODEL_API_KEY=<api_key>
export MODEL=<model_name>
export WORKSPACE_DIR=<workspace_directory>
export IF_RESTART=true
quasar 
```

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

For inquiries, advanced features, or beta access, please reach out to: [j.evans@adelaide.edu.au](mailto:j.evans@adelaide.edu.au)


</details>
