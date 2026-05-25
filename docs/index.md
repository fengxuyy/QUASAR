---
title: QUASAR Documentation
description: Documentation hub for installing, running, and understanding QUASAR.
show_title: false
---

<div class="hero">
  <div>
    <span class="pill">Quantum Universal Autonomous System for Atomistic Research</span>
    <h1>QUASAR</h1>
    <p>
      Documentation for the CLI, containers, settings, workspaces, and extension paths used by QUASAR's autonomous atomistic research workflows.
    </p>
    <div class="hero-actions">
      <a class="button-link" href="{{ '/installation/' | relative_url }}">Get Started</a>
      <a class="button-link button-link-subtle" href="{{ '/quick-tutorial/' | relative_url }}">Quick Tutorial</a>
    </div>
  </div>
</div>

## Why Use QUASAR

<div class="metric-grid">
  <div class="metric-card">
    <p class="mini-label">Interface</p>
    <h3>CLI</h3>
    <p>Run from the terminal, with shared settings, checkpoint resume, workspace browsing, and archive history.</p>
  </div>
  <div class="metric-card">
    <p class="mini-label">Scientific Stack</p>
    <h3>Atomistic Runtime</h3>
    <p>Container images include the core simulation and analysis stack for DFT, molecular dynamics, adsorption, xTB, ORCA, ML potentials, and cheminformatics.</p>
  </div>
  <div class="metric-card">
    <p class="mini-label">Models</p>
    <h3>Flexible Routing</h3>
    <p>Use one global model or configure Strategist, Operator, and Evaluator models independently, including OpenAI-compatible endpoints.</p>
  </div>
  <div class="metric-card">
    <p class="mini-label">Traceability</p>
    <h3>Archived Runs</h3>
    <p>Completed work is preserved under `quasar_archive/`, while active logs, summaries, and checkpoints remain inspectable during execution.</p>
  </div>
</div>

## Current Capabilities

QUASAR v0.4.0 includes the interactive CLI, OpenAI-compatible HTTP endpoints, per-agent model overrides, plan confirmation before execution, checkpoint resume and task revert, adaptive `ACCURACY` and `GRANULARITY` modes, context compression controls, local documentation retrieval, and optimized Docker runtimes for CPU and GPU images. See [Configuration]({{ '/configuration/' | relative_url }}) for environment variables and routing details.

## Start Here

<div class="feature-grid">
  <a class="feature-card" href="{{ '/quick-tutorial/' | relative_url }}">
    <p class="mini-label">Walkthrough</p>
    <h3>Quick Tutorial</h3>
    <p>Follow a concrete first run around a silicon band-gap workflow from launch through result inspection.</p>
  </a>
  <a class="feature-card" href="{{ '/installation/' | relative_url }}">
    <p class="mini-label">Setup</p>
    <h3>Get Started</h3>
    <p>Choose Docker, Singularity, or local deployment, mount a workspace, and launch QUASAR correctly the first time.</p>
  </a>
  <a class="feature-card" href="{{ '/cli/' | relative_url }}">
    <p class="mini-label">Interface</p>
    <h3>CLI</h3>
    <p>Learn the interactive CLI, headless runs, resume behavior, cleanup and revert commands, history browsing, and runtime checks.</p>
  </a>
  <a class="feature-card" href="{{ '/configuration/' | relative_url }}">
    <p class="mini-label">Tuning</p>
    <h3>Configuration</h3>
    <p>Set models, RAG, execution rigor, task granularity, agent-specific overrides, and long-run behavior.</p>
  </a>
  <a class="feature-card" href="{{ '/workspace-history/' | relative_url }}">
    <p class="mini-label">Results</p>
    <h3>Workspace & History</h3>
    <p>Understand where outputs live, what gets preserved, how archives are created, and how to inspect older work.</p>
  </a>
  <a class="feature-card" href="{{ '/extending-quasar/' | relative_url }}">
    <p class="mini-label">Advanced</p>
    <h3>Extending QUASAR</h3>
    <p>Learn when to install software in the prompt, when to bake it into the environment, and when system-prompt inclusion is enough versus when code changes are needed.</p>
  </a>
</div>
