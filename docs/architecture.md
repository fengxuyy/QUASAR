---
title: Architecture
description: High-level architecture and workflow model for QUASAR-CHEM.
section: System
lead: QUASAR-CHEM combines a three-agent workflow, a shared workspace, and local documentation retrieval to support long-running scientific tasks with recovery and review.
permalink: /architecture/
---

## Three-Agent Flow

<div class="card-grid">
  <div class="step-card">
    <p class="mini-label">Planning</p>
    <h3>Strategist</h3>
    <p>Builds the plan from the user request, workspace state, and archived context. It uses `ACCURACY` and `GRANULARITY` to shape how the work is decomposed.</p>
  </div>
  <div class="step-card">
    <p class="mini-label">Execution</p>
    <h3>Operator</h3>
    <p>Executes the current task with tools for files, Python execution, documentation retrieval, and web lookup when needed.</p>
  </div>
  <div class="step-card">
    <p class="mini-label">Validation</p>
    <h3>Evaluator</h3>
    <p>Checks whether the operator’s work actually satisfies the task. It can fail a task and request corrective action before the run advances.</p>
  </div>
</div>

## Shared State Model

The agents coordinate through a shared run state that tracks:

- the original user request
- the current plan
- completed steps
- step summaries
- per-task message history
- whether the system is in replanning mode

This shared state is what makes checkpoint resume possible.

## Documentation Retrieval

When RAG is enabled, QUASAR-CHEM prepares two complementary resources:

1. downloaded documentation repositories in `workspace/docs/`
2. a prebuilt retrieval index in `workspace/.rag_index/`

The current downloader targets documentation and examples for:

- ASE
- pymatgen
- MACE
- RASPA3
- Quantum ESPRESSO
- LAMMPS

The Operator can query that material directly, then follow up by reading source files or examples from the downloaded docs.

## CLI on Top of the Same Core

Both interactive and headless CLI flows ultimately drive the same underlying run engine.

That means the mental model of runs, checkpoints, archives, and settings stays the same whether you launch QUASAR from an interactive terminal session or a direct one-shot prompt.

## Restart and Archive Loop

The normal lifecycle looks like this:

1. A run starts with current settings and a workspace.
2. Progress is checkpointed during execution.
3. If interrupted, the run can resume from checkpoint state.
4. If completed, the workspace contents move into `archive/run_N/`.
5. The next run can use archived context to improve or continue the research thread.

## Why This Structure Matters

This architecture is aimed at long, stateful scientific work rather than single-shot chat responses. Planning, execution, validation, checkpointing, and archival context are all first-class parts of the product.
