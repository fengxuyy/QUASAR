---
title: Get Started
description: Set up and launch QUASAR with Docker, Singularity, or local deployment.
section: Setup
lead: Choose a runtime image, mount a workspace, and launch the CLI.
permalink: /installation/
---

<div class="card-grid">
  <div class="step-card">
    <p class="mini-label">Recommended</p>
    <h3>Docker CLI</h3>
    <p>Best default for laptops and workstations. It keeps the scientific runtime isolated from the host machine.</p>
  </div>
  <div class="step-card">
    <p class="mini-label">HPC</p>
    <h3>Singularity</h3>
    <p>Best fit for clusters and shared compute environments where container execution is available but Docker daemon access is not.</p>
  </div>
  <div class="step-card">
    <p class="mini-label">Advanced</p>
    <h3>Local Deployment</h3>
    <p>Useful when you need a custom environment on your machine, but it is less isolated and usually more fragile than container-based runs.</p>
  </div>
</div>

## Prerequisites

- Access to a supported model provider and a valid API key
- Docker installed on your device (required for Docker-based deployments)
- A workspace directory that can be mounted into the container
- Node.js 20 or newer (required only if running the CLI stack outside of a container)
- Optional keys such as `PMG_MAPI_KEY` for Materials Project access and `HF_TOKEN` for Hugging Face downloads used by the RAG index

<div class="callout callout-accent">
  <strong>Note:</strong> QUASAR is currently optimised for Gemini-oriented setups. Other providers may work, but they are not yet the primary compatibility target.
</div>

## Installation
### Docker

Pull the appropriate QUASAR image for your system from <a href="https://hub.docker.com/r/fengxuyang/quasar" target="_blank" rel="noopener noreferrer">Docker Hub</a>. Choose a tag that matches your hardware target:

| Image family | Best for |
| --- | --- |
| `amd64` / CPU tags | x86_64 CPU workstations and servers. |
| `arm64` tags | ARM64 machines. |
| `cuda` tags | NVIDIA GPU hosts with compatible drivers. |
| `rocm` tags | AMD GPU hosts with compatible ROCm support. |

```bash
docker pull fengxuyang/quasar:<tag>
```

The optimized images use staged builds and copy only runtime artifacts into the final image. They retain QUASAR's expected scientific stack, including Quantum ESPRESSO, LAMMPS/OpenKIM, RASPA3, xTB, ORCA, MACE/PyTorch, pymatgen, ASE, and RDKit where supported by the image architecture.

### Singularity

Build a `.sif` image from <a href="https://hub.docker.com/r/fengxuyang/quasar" target="_blank" rel="noopener noreferrer">Docker Hub</a>:

```bash
singularity build quasar.sif docker://fengxuyang/quasar:<tag>
```

### Local Deployment

If you want to run QUASAR directly on your machine, install the Python package and the scientific software stack you need. A minimal example looks like this:

```bash
conda create -n quasar python=3.11 -y
conda activate quasar
conda install -c conda-forge qe lammps raspa3 raspalib -y
pip install --upgrade pip
pip install quasar-core
```

### CLI

Use the CLI when you want terminal-native interaction or a direct headless prompt.

#### Docker

```bash
docker run -it --rm \
  -e MODEL=<model_name> \
  -e MODEL_API_KEY=<api_key> \
  -v "<workspace_path>:/workspace" \
  fengxuyang/quasar:<tag> \
  quasar
```

#### Singularity

```bash
singularity exec --cleanenv \
  -B "<workspace_path>:/workspace" \
  --home "<workspace_path>:/workspace" \
  --env MODEL=<model_name> \
  --env MODEL_API_KEY=<api_key> \
  quasar.sif quasar
```

#### Local Deployment

```bash
export WORKSPACE_DIR=<workspace_directory>
export MODEL=<model_name>
export MODEL_API_KEY=<api_key>
quasar
```

## What to Expect on First Launch

When QUASAR starts in a new workspace for the first time, it prepares the local resources it needs for later runs.

This setup step can include:

- Documentation repositories stored in `docs/`
- A prebuilt RAG index in `.rag_index/` when RAG is enabled
- Embedding model files used for documentation retrieval
- Runtime settings and checkpoint metadata such as `quasar_logs/checkpoint_settings.json`

Because these resources are downloaded and prepared only once per new workspace, the first launch is usually slower than later runs in the same workspace.
