<p align="center">
  <img src="logos/logo_text_fancy.png" alt="QUASAR logo" width="420" />
</p>

<p align="center">
  <strong>Quantum Universal Autonomous System for Atomistic Research</strong>
</p>

<p align="center">
  Autonomous computational chemistry for end-to-end atomistic workflows.
</p>

<p align="center">
  <a href="https://pypi.org/project/quasar-core/">
    <img src="https://img.shields.io/pypi/v/quasar-core?style=for-the-badge&logo=pypi&logoColor=white" alt="PyPI version" />
  </a>
  <img src="https://img.shields.io/pypi/pyversions/quasar-core?style=for-the-badge&logo=python&logoColor=white" alt="Supported Python versions" />
  <a href="https://fengxuyy.github.io/QUASAR/">
    <img src="https://img.shields.io/badge/docs-online-0A7C86?style=for-the-badge" alt="Documentation" />
  </a>
  <a href="https://arxiv.org/abs/2602.00185">
    <img src="https://img.shields.io/badge/paper-arXiv-B31B1B?style=for-the-badge&logo=arxiv&logoColor=white" alt="Paper" />
  </a>
  <a href="https://hub.docker.com/r/fengxuyang/quasar">
    <img src="https://img.shields.io/badge/docker-images-2496ED?style=for-the-badge&logo=docker&logoColor=white" alt="Docker images" />
  </a>
</p>

QUASAR is a research-focused autonomous system for atomistic simulation and materials modeling. It combines LLM planning, scientific software execution, and reproducible workspace management in a single workflow so researchers can move from prompt to structured results with less manual orchestration.

The platform is designed for computational chemistry and materials science tasks spanning density functional theory (DFT), machine-learning potentials (MLPs), molecular dynamics (MD), and adsorption or Monte Carlo studies. QUASAR can plan multi-step work, execute tools, retrieve documentation, checkpoint progress, and archive outputs for later inspection.

Documentation: [QUASAR Docs](https://fengxuyy.github.io/QUASAR/)  
PyPI: [quasar-core](https://pypi.org/project/quasar-core/)  
Paper: [arXiv:2602.00185](https://arxiv.org/abs/2602.00185)

## Why QUASAR

- **End-to-end automation**: turn a scientific request into a planned workflow, executed tasks, validated intermediate results, and a final summary.
- **Research-oriented tooling**: support workflows that involve DFT, machine-learning potentials, molecular dynamics, and adsorption simulations.
- **Traceable runs**: keep checkpoints, logs, run summaries, archived workspaces, and per-task history for reproducibility and review.
- **Practical interfaces**: use the interactive CLI for guided work or run prompts headlessly for batch and HPC use cases.
- **Flexible deployment**: run QUASAR with Docker, Singularity, or a local Python installation.
- **Configurable execution**: tune rigor, task granularity, context compression, retrieval, and even per-agent model selection.
- **OpenAI-compatible APIs**: use `OPENAI_API_BASE` or `API_BASE_URL`, or per-agent base URLs, to point models at OpenAI-compatible gateways and third-party hosts.
- **Human-in-the-loop planning**: after the Strategist drafts a plan, the interactive CLI can confirm it, request a revision with feedback, or stop before execution.
- **Adaptive modes (experimental)**: `ACCURACY=adaptive` and `GRANULARITY=adaptive` let agents scale numerical rigor and task breakdown with workflow complexity.
- **ML-ready stack**: workflows can use scikit-learn and PyTorch for model training and analysis.

## Architecture at a Glance

| Component | Role |
| --- | --- |
| `Strategist` | Breaks the user request into a structured execution plan. |
| `Operator` | Executes tools, reads and writes files, and runs the scientific workflow. |
| `Evaluator` | Reviews task outcomes and decides whether work is ready to proceed. |
| Workspace layer | Stores checkpoints, logs, summaries, archives, and generated artifacts. |
| Retrieval layer | Optionally indexes documentation and serves grounded context during runs. |

## Documentation Map

- [Get Started](https://fengxuyy.github.io/QUASAR/installation/) for Docker, Singularity, and local installation.
- [Quick Tutorial](https://fengxuyy.github.io/QUASAR/quick-tutorial/) for a first end-to-end run.
- [CLI Reference](https://fengxuyy.github.io/QUASAR/cli/) for interactive, headless, resume, and cleanup commands.
- [Configuration](https://fengxuyy.github.io/QUASAR/configuration/) for environment variables and execution profiles.
- [Workspace & History](https://fengxuyy.github.io/QUASAR/workspace-history/) for logs, archives, and checkpoint behavior.
- [Extending QUASAR](https://fengxuyy.github.io/QUASAR/extending-quasar/) for adding dependencies or adapting the environment.
- [Contact](https://fengxuyy.github.io/QUASAR/contact/) for issues, collaboration, and support.

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

## Configuration Snapshot

| Variable | Purpose | Default |
| --- | --- | --- |
| `MODEL` | Required model name. | None |
| `MODEL_API_KEY` | Required provider API key. | None |
| `OPENAI_API_BASE` | Optional base URL for OpenAI-compatible endpoints (same as `API_BASE_URL`). | None |
| `API_BASE_URL` | Optional global base URL for OpenAI-compatible HTTP APIs. | None |
| `ACCURACY` | Planning and execution rigor: `eco`, `standard`, `pro`, `adaptive` (experimental). | `standard` |
| `GRANULARITY` | Task decomposition depth: `low`, `medium`, `high`, `adaptive` (experimental). | `medium` |
| `CONTEXT_THRESHOLD` | Context-compression trigger level. | `medium` |
| `ENABLE_RAG` | Enable documentation retrieval. | `true` |
| `CHECK_INTERVAL` | Minutes between long-run check-ins. Leave unset or use `0` to disable. | Disabled |
| `AUTO_IMPROVE_CYCLES` | Automatic follow-up refinement cycles after a successful run. | `0` |
| `NUM_CORES` | Override detected physical core count. | `Auto` |
| `PMG_MAPI_KEY` | Materials Project API key for `pymatgen`. | None |
| `HF_TOKEN` | Optional Hugging Face token for authenticated retrieval access. | None |
| `IF_RESTART` | Resume from the last checkpoint. | `false` |
| `AUTO_CONFIRM_PLAN` | Skip interactive plan confirmation when `true`/`1`/`yes`/`on` (e.g. headless automation). | unset |

Per-agent overrides are also available:

| Agent | Model | API key | Base URL |
| --- | --- | --- | --- |
| Strategist | `STRATEGIST_MODEL` | `STRATEGIST_MODEL_API_KEY` | `STRATEGIST_API_BASE_URL` |
| Operator | `OPERATOR_MODEL` | `OPERATOR_MODEL_API_KEY` | `OPERATOR_API_BASE_URL` |
| Evaluator | `EVALUATOR_MODEL` | `EVALUATOR_MODEL_API_KEY` | `EVALUATOR_API_BASE_URL` |

> QUASAR is optimized for Gemini-oriented setups first, but OpenAI-compatible base URLs are supported for the primary model and per-agent overrides. Anthropic, xAI, and other providers use their respective integrations when selected by model name.

## Workspace Outputs

QUASAR writes all outputs into the mounted workspace directory:

```text
workspace/
├── final_results/              # Final outputs and analysis from the current run
│   └── summary.md              # Main written summary
├── logs/                       # Execution logs and run reports
│   ├── usage_report.md
│   ├── execution_overview.md
│   ├── input_messages.md
│   └── conversation/
├── archive/                    # Historical runs preserved across normal cleanup
│   ├── run_1/
│   └── run_N/
├── docs/                       # Downloaded documentation
├── .rag_index/                 # Cached retrieval index and embeddings
├── checkpoints.sqlite          # Checkpoint database
├── checkpoint_settings.json    # Run settings and token statistics
└── ...
```

When a run completes, QUASAR archives the workspace state, removes active checkpoint files, and keeps reusable assets such as `archive/`, `docs/`, and hidden cache directories available for future runs.

## Resume and Cleanup

- Use `quasar --resume` to continue an interrupted run.
- Use `quasar --clear` to remove the active checkpoint and current workspace state while keeping archived runs and docs.
- Use `quasar --fresh` to remove current workspace state and archived runs while preserving docs and hidden cache directories.

Checkpoint metadata restores non-secret settings such as model choice, accuracy, granularity, and retrieval options. API keys should still be supplied through environment variables or the interactive `\settings` panel before resuming.

## Acknowledgements

QUASAR builds on a strong open-source scientific software ecosystem. In particular, the project draws on tools and libraries including Quantum ESPRESSO, ASE, MACE, pymatgen, LAMMPS, and RASPA3.

## Citation

If QUASAR is useful in your research, please cite:

> Yang, Fengxu, and Jack D. Evans. "QUASAR: A Universal Autonomous System for Atomistic Simulation and a Benchmark of Its Capabilities." *Journal of Chemical Information and Modeling*, [https://doi.org/10.1021/acs.jcim.6c00295](https://doi.org/10.1021/acs.jcim.6c00295)

```bibtex
@article{yang2026quasar,
  title={QUASAR: A Universal Autonomous System for Atomistic Simulation and a Benchmark of Its Capabilities},
  author={Yang, Fengxu and Evans, Jack D.},
  journal={Journal of Chemical Information and Modeling},
  year={2026},
  month=may,
  pages={acs.jcim.6c00295},
  doi={10.1021/acs.jcim.6c00295},
  url={https://doi.org/10.1021/acs.jcim.6c00295}
}
```

## Contact

- Technical issues and feature requests: [GitHub Issues](https://github.com/fengxuyy/QUASAR/issues)
- Collaboration, advanced features, beta access, or partnership inquiries: [j.evans@adelaide.edu.au](mailto:j.evans@adelaide.edu.au)
