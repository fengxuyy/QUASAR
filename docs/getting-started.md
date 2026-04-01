---
title: Getting Started
description: Install and launch QUASAR with Docker, Singularity, or local deployment.
section: Setup
lead: Choose a deployment path, prepare a workspace, and launch QUASAR through the interactive CLI or a headless prompt.
permalink: /getting-started/
---

## Choose a Deployment Path

<div class="card-grid">
  <div class="step-card">
    <p class="mini-label">Recommended</p>
    <h3>Docker</h3>
    <p>Best default for laptops and workstations. It gives you the cleanest setup story and keeps the runtime isolated from your host machine.</p>
  </div>
  <div class="step-card">
    <p class="mini-label">HPC</p>
    <h3>Singularity</h3>
    <p>Best fit for clusters and shared compute environments where container execution is available but Docker is not.</p>
  </div>
  <div class="step-card">
    <p class="mini-label">Advanced</p>
    <h3>Local Deployment</h3>
    <p>Useful when you need a custom environment on your machine, but it is less isolated and usually more fragile than container-based runs.</p>
  </div>
</div>

## Prerequisites

- A model provider and a valid `MODEL_API_KEY`
- A model name exposed as `MODEL`
- A writable workspace directory for outputs, checkpoints, logs, and archives
- One runtime path: Docker, Singularity, or a local Python installation
- Node.js 18+ if you are using the local interactive CLI instead of a prebuilt container

> QUASAR is currently optimized for Gemini-oriented setups. Other providers may work, but they are not yet the primary compatibility target.

<div class="callout callout-accent">
  <strong>Interactive tip:</strong> if you launch the CLI without <code>MODEL</code> or <code>MODEL_API_KEY</code>, QUASAR can prompt for them through the built-in <code>\settings</code> panel before the first task starts.
</div>

## Prepare the Runtime

### Docker

Pull the image you want to run:

```bash
docker pull fengxuyang/quasar:<tag>
```

### Singularity

Build a `.sif` image from Docker Hub:

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

Set a workspace directory before local runs:

```bash
export WORKSPACE_DIR=<workspace_directory>
```

## Launch Modes

Use the interactive CLI when you want streamed agent updates, status panels, and checkpoint prompts. Use a direct prompt when you want batch-style execution from scripts, schedulers, or one-off commands.

## Docker

### Launch the CLI

Interactive:

```bash
docker run -it --rm \
  -e MODEL_API_KEY=<api_key> \
  -e MODEL=<model_name> \
  -v "<workspace_path>:/workspace" \
  fengxuyang/quasar:<tag> \
  quasar
```

Headless:

```bash
docker run --rm \
  -e MODEL_API_KEY=<api_key> \
  -e MODEL=<model_name> \
  -v "<workspace_path>:/workspace" \
  fengxuyang/quasar:<tag> \
  quasar "Calculate the band gap of silicon"
```

### Use the Built-In Settings Panel

If you want to open the container first and provide model settings interactively, you can omit the model environment variables on the initial CLI launch and fill them in from `\settings`:

```bash
docker run -it --rm \
  -v "<workspace_path>:/workspace" \
  fengxuyang/quasar:<tag> \
  quasar
```

## Singularity

### Launch the CLI

Interactive:

```bash
singularity exec --cleanenv \
  -B "<workspace_path>:/workspace" \
  --home "<workspace_path>:/workspace" \
  --env MODEL_API_KEY=<api_key> \
  --env MODEL=<model_name> \
  <tag>.sif quasar
```

Headless:

```bash
singularity exec --cleanenv \
  -B "<workspace_path>:/workspace" \
  --home "<workspace_path>:/workspace" \
  --env MODEL_API_KEY=<api_key> \
  --env MODEL=<model_name> \
  <tag>.sif quasar "Your research prompt here"
```

## Local Deployment

### Launch the CLI

Interactive:

```bash
export WORKSPACE_DIR=<workspace_directory>
quasar
```

Headless:

```bash
export MODEL_API_KEY=<api_key>
export MODEL=<model_name>
export WORKSPACE_DIR=<workspace_directory>
quasar "Your research prompt here"
```

`HF_TOKEN` is optional unless your environment requires authenticated access for the prebuilt RAG index or related Hugging Face resources.

## First-Run Expectations

On startup, QUASAR may download:

- documentation repositories into `workspace/docs/`
- a prebuilt RAG index into `workspace/.rag_index/` when RAG is enabled
- embedding model assets used for documentation retrieval

That means the first launch can be slower than later launches, especially on a fresh workspace.

## First-Run Checklist

Before you launch anything large, make sure you can answer these four questions:

1. Where is the mounted workspace, and do you have write access to it?
2. Which model will QUASAR use, and is `MODEL_API_KEY` available?
3. Are you using the interactive CLI or a direct headless prompt?
4. Do you want RAG enabled so QUASAR can retrieve local scientific documentation?

## Resume an Interrupted Run

Use the CLI `--resume` flag when a checkpoint already exists. The legacy `IF_RESTART=true` environment variable is still supported, but `quasar --resume` is the clearer path.

Docker example:

```bash
docker run --rm \
  -e MODEL_API_KEY=<api_key> \
  -e MODEL=<model_name> \
  -v "<workspace_path>:/workspace" \
  fengxuyang/quasar:<tag> \
  quasar --resume
```

Singularity example:

```bash
singularity exec --cleanenv \
  --env MODEL_API_KEY=<api_key> \
  --env MODEL=<model_name> \
  -B "<workspace_path>:/workspace" \
  --home "<workspace_path>:/workspace" \
  <tag>.sif quasar --resume
```

Local example:

```bash
export MODEL_API_KEY=<api_key>
export MODEL=<model_name>
export WORKSPACE_DIR=<workspace_directory>
quasar --resume
```

If you want a deeper explanation of what lives in the workspace and what gets preserved between runs, continue with [Workspace & History]({{ '/workspace-history/' | relative_url }}).

If you want a concrete first exercise, follow the [Quick Tutorial]({{ '/quick-tutorial/' | relative_url }}) next.
