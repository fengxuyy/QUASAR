<p align="center">
    <img src="logos/logo_text_fancy.png" alt="MOF-ChemUnity Logo" width="400"/>
</p>

<h1 align="center">Universal Autonomous System for Atomistic Research</h1>

A research-ready autonomous computational chemistry agentic system. QUASAR covers the full atomistic simulation pipeline with integrated tools including Quantum ESPRESSO, ASE, MACE, pymatgen, LAMMPS, RASPA3, ORCA, xTB, and RDKit. Currently optimised for Gemini models; other providers may not be fully functional. Broader compatibility coming in future releases.

## Documentation

- **GitHub Pages:** [https://fengxuyy.github.io/QUASAR](https://fengxuyy.github.io/QUASAR)
- **Docs source:** [`docs/`](docs/)
- **Recommended entrypoint:** [`docs/index.md`](docs/index.md)

Quick links:
- [Installation](https://fengxuyy.github.io/QUASAR-CHEM/installation/) for Docker, Singularity, and local setup.
- [Quick Tutorial](https://fengxuyy.github.io/QUASAR-CHEM/quick-tutorial/) for a step-by-step walkthrough.
- [CLI Reference](https://fengxuyy.github.io/QUASAR-CHEM/cli/) for interactive, headless, resume, and cleanup commands.
- [Configuration](https://fengxuyy.github.io/QUASAR-CHEM/configuration/) for environment variables and execution profiles.
- [Workspace & History](https://fengxuyy.github.io/QUASAR-CHEM/workspace-history/) for logs, archives, and checkpoint behavior.
- [Extending QUASAR](https://fengxuyy.github.io/QUASAR-CHEM/extending-quasar/) for adding dependencies or adapting the environment.
- [Contact](https://fengxuyy.github.io/QUASAR-CHEM/contact/) for issues, collaboration, and support.

## Quick Start

QUASAR supports three deployment paths:

- **Docker** is the recommended default for laptops and workstations.
- **Singularity** is the best fit for HPC and shared cluster environments.
- **Local deployment** is useful when you need a custom native environment, but it is typically less isolated.

### Docker

Pull the image:

```bash
docker pull fengxuyang/quasar:<tag>
```

Launch the interactive CLI:

```bash
docker run -it --rm \
  -v "<workspace_path>:/workspace" \
  fengxuyang/quasar:<tag> \
  quasar
```

Run a headless prompt:

```bash
docker run --rm \
  -e MODEL=<model_name> \
  -e MODEL_API_KEY=<api_key> \
  -v "<workspace_path>:/workspace" \
  fengxuyang/quasar:<tag> \
  quasar "Calculate the band gap of silicon"
```

### Singularity

Build the `.sif` image from Docker Hub:

```bash
singularity build quasar.sif docker://fengxuyang/quasar:<tag>
```

Run QUASAR:

```bash
singularity exec --cleanenv \
  -B "<workspace_path>:/workspace" \
  --home "<workspace_path>:/workspace" \
  quasar.sif quasar
```

Run a headless prompt:

```bash
singularity exec --cleanenv \
  -B "<workspace_path>:/workspace" \
  --home "<workspace_path>:/workspace" \
  --env MODEL=<model_name> \
  --env MODEL_API_KEY=<api_key> \
  quasar.sif quasar "Your research prompt here"
```

### Local Installation

Prerequisites:

- Python 3.10 or newer
- Node.js 20 or newer for the local interactive CLI
- Scientific software installed separately as needed for your workflows

Example setup:

```bash
conda create -n quasar python=3.11 -y
conda activate quasar
conda install -c conda-forge qe lammps raspa3 raspalib -y
pip install --upgrade pip
pip install quasar-core
```

Launch QUASAR:

```bash
export WORKSPACE_DIR=<workspace_directory>
quasar
```

Run a headless prompt:

```bash
export MODEL=<model_name>
export MODEL_API_KEY=<api_key>
export WORKSPACE_DIR=<workspace_directory>
quasar "Your research prompt here"
```

> Interactive sessions can fill missing `MODEL` and `MODEL_API_KEY` values through the built-in `\settings` panel. Headless runs should still provide required variables before launch.

> The first run in a new workspace can be slower because QUASAR may prepare documentation assets, retrieval indexes, and embedding resources.

## CLI Reference

| Command | What it does |
| --- | --- |
| `quasar` | Starts the interactive terminal UI. |
| `quasar "..."` | Runs a direct prompt in headless mode. |
| `quasar --resume` | Resumes the active checkpoint. |
| `quasar --clear` | Clears the active checkpoint and current workspace state while preserving archives and docs. |
| `quasar --fresh` | Clears current workspace state and archived runs while preserving docs and hidden cache directories. |
| `quasar --history` | Opens the interactive per-task checkpoint history browser. |
| `quasar --config` | Prints the current configuration values. |
| `quasar --config validate` | Verifies required configuration such as `MODEL_API_KEY`. |
| `quasar --info` | Prints system and workspace information. |
| `quasar --no-rag "..."` | Runs a prompt without documentation retrieval for that session. |

### Interactive Backslash Commands

While using the interactive CLI, type `\` at the start of the input box to open the command picker:

| Command | Description |
| --- | --- |
| `\settings` | Open the system settings panel. |
| `\refresh` | Clear and redraw the CLI, then reload checkpoint state. |
| `\execution-overview` | Display the current or latest archived `execution_overview.md`. |
| `\usage-report` | Display the current or latest archived `usage_report.md`. |
| `\revert <task>` | Confirm and revert the active checkpoint/workspace to the start of a task, e.g. `\revert 2`. |

## Configuration Snapshot

| Variable | Purpose | Default |
| --- | --- | --- |
| `MODEL` | Required model name. | None |
| `MODEL_API_KEY` | Required provider API key. | None |
| `OPENAI_API_BASE` | Optional base URL for OpenAI-compatible endpoints. | None |
| `ACCURACY` | Planning and execution rigor: `eco`, `standard`, `pro`, `adaptive`. | `standard` |
| `GRANULARITY` | Task decomposition depth: `low`, `medium`, `high`, `adaptive`. | `adaptive` |
| `CONTEXT_THRESHOLD` | Context-compression trigger level. | `medium` |
| `ENABLE_RAG` | Enable documentation retrieval. | `true` |
| `AUTO_IMPROVE_CYCLES` | Automatic follow-up refinement cycles after a successful run. | `0` |
| `AUTO_CONFIRM_PLAN` | Skip interactive plan confirmation for headless or batch runs. | unset |
| `NUM_CORES` | Override detected physical core count. | `Auto` |
| `PMG_MAPI_KEY` | Materials Project API key for `pymatgen`. | None |
| `HF_TOKEN` | Optional Hugging Face token for authenticated retrieval access. | None |
| `IF_RESTART` | Resume from the last checkpoint. | `false` |

Long-running Python executions use agent-scheduled check-ins via `execute_python(check_in_after=...)` and are rescheduled after each check-in via `continue_execution(next_check_in_after=...)`.

Per-agent overrides are also available:

| Agent | Model | API key | Base URL |
| --- | --- | --- | --- |
| Strategist | `STRATEGIST_MODEL` | `STRATEGIST_MODEL_API_KEY` | `STRATEGIST_API_BASE_URL` |
| Operator | `OPERATOR_MODEL` | `OPERATOR_MODEL_API_KEY` | `OPERATOR_API_BASE_URL` |
| Evaluator | `EVALUATOR_MODEL` | `EVALUATOR_MODEL_API_KEY` | `EVALUATOR_API_BASE_URL` |

> QUASAR is currently optimized for Gemini-oriented setups. Other providers may work, especially through supported integrations and compatible endpoints, but they are not yet the primary compatibility target.

## Workspace Outputs

QUASAR writes all outputs into the mounted workspace directory:

```text
workspace/
├── final_results/              # Final outputs and analysis from the current run
│   └── summary.md              # Main written summary
├── quasar_logs/                # Execution logs, checkpoints, and usage reports
│   ├── usage_report.md
│   ├── execution_overview.md
│   ├── input_messages.md
│   ├── conversation.md
│   ├── checkpoints.sqlite      # Checkpoint database
│   ├── checkpoint_settings.json # Run settings and token statistics
│   └── pending_execution.json  # Interrupted execution recovery state
├── quasar_archive/             # Historical runs preserved across normal cleanup
│   ├── quasar_run_YYYYMMDD_HHMMSS_<id>/
│   │   ├── final_results/
│   │   ├── quasar_logs/
│   │   └── ...
│   └── quasar_run_.../
├── docs/                       # Downloaded documentation
└── .rag_index/                 # Cached retrieval index and embeddings
```

When a run completes, QUASAR archives the workspace state to `quasar_archive/`, removes active checkpoint files, and keeps reusable assets such as `quasar_archive/`, `docs/`, and hidden cache directories available for future runs.

## Resume and Cleanup

- Use `quasar --resume` to continue an interrupted run. When resuming into an operator task, you can type steering instructions to guide the agent.
- Use `quasar --clear` to remove the active checkpoint and current workspace state while keeping archived runs and docs.
- Use `quasar --fresh` to remove current workspace state and archived runs while preserving docs and hidden cache directories.

Checkpoint metadata restores non-secret settings such as model choice, accuracy, granularity, and retrieval options. API keys should still be supplied through environment variables or the interactive `\settings` panel before resuming.

## Third-Party Software Licenses

QUASAR integrates with several third-party computational chemistry packages. Most are open-source, but **ORCA** is distributed under its own license terms:

> **ORCA** is free for academic use but is **not free for commercial use**. By using ORCA through QUASAR, you agree to the [ORCA license terms](https://www.faccts.de/orca/). Users are responsible for obtaining a valid ORCA license and ensuring compliance with its terms of use.

## Acknowledgements

QUASAR builds on a strong open-source scientific software ecosystem. In particular, the project draws on tools and libraries including Quantum ESPRESSO, ASE, MACE, pymatgen, LAMMPS, RASPA3, ORCA, xTB, and RDKit.

## Citation

If QUASAR is useful in your research, please cite:

> Yang, Fengxu, and Jack D. Evans. "QUASAR: A Universal Autonomous System for Atomistic Simulation and a Benchmark of Its Capabilities." arXiv:2602.00185, 2026. [https://doi.org/10.48550/arXiv.2602.00185](https://doi.org/10.48550/arXiv.2602.00185)

```bibtex
@misc{yang2026quasar,
  title={QUASAR: A Universal Autonomous System for Atomistic Simulation and a Benchmark of Its Capabilities},
  author={Fengxu Yang and Jack D. Evans},
  year={2026},
  eprint={2602.00185},
  archivePrefix={arXiv},
  primaryClass={physics.chem-ph},
  url={https://arxiv.org/abs/2602.00185}
}
```

## Contact

- Technical issues and feature requests: [GitHub Issues](https://github.com/fengxuyy/QUASAR/issues)
- Collaboration, advanced features, beta access, or partnership inquiries: [j.evans@adelaide.edu.au](mailto:j.evans@adelaide.edu.au)
