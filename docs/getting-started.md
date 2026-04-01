---
title: Getting Started
description: Install and launch QUASAR-CHEM with Docker or Singularity.
section: Setup
lead: Start a new QUASAR-CHEM session with Docker or Singularity, mount a workspace, and run it through the CLI.
permalink: /getting-started/
---

## Prerequisites

- A model provider and a valid `MODEL_API_KEY`
- A model name exposed as `MODEL`
- Docker Desktop / Docker Engine, or Singularity on HPC systems
- A writable workspace directory you can mount into the container

> QUASAR-CHEM is currently optimized for Gemini-oriented setups. Other providers may work, but they are not yet the primary compatibility target.

## Launch Modes

Use the interactive CLI when you want a full terminal session with streamed agent updates. Use a direct prompt when you want a batch-style run from scripts, schedulers, or one-off commands.

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

`HF_TOKEN` is optional unless your environment requires authenticated access for the prebuilt RAG index or related Hugging Face resources.

## First-Run Expectations

On startup, QUASAR-CHEM may download:

- documentation repositories into `workspace/docs/`
- a prebuilt RAG index into `workspace/.rag_index/` when RAG is enabled
- embedding model assets used for documentation retrieval

That means the first launch can be slower than later launches, especially on a fresh workspace.

## Resume an Interrupted Run

Use `IF_RESTART=true` or the CLI `--resume` flag when a checkpoint already exists.

Docker example:

```bash
docker run --rm \
  -e IF_RESTART=true \
  -v "<workspace_path>:/workspace" \
  fengxuyang/quasar:<tag> \
  quasar
```

Singularity example:

```bash
singularity exec --cleanenv \
  --env IF_RESTART=true \
  -B "<workspace_path>:/workspace" \
  --home "<workspace_path>:/workspace" \
  <tag>.sif quasar
```

If you want the workspace model, archive, and checkpoint behavior before running anything large, read [Workspace & History]({{ '/workspace-history/' | relative_url }}).

If you want a concrete first exercise, follow the [Quick Tutorial]({{ '/quick-tutorial/' | relative_url }}) next.
