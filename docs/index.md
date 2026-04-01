---
title: QUASAR Documentation
description: Documentation hub for installing, running, and understanding QUASAR.
show_title: false
---

<div class="hero">
  <div>
    <span class="pill">Quantum Universal Autonomous System for Atomistic Research</span>
    <h1>Documentation for QUASAR</h1>
    <p>
      QUASAR is an autonomous system for end-to-end scientific discovery, integrating LLMs with simulation tools to automate workflows across quantum chemistry, materials science, and molecular simulation.
    </p>
    <div class="hero-actions">
      <a class="button-link" href="{{ '/getting-started/' | relative_url }}">Start With Setup</a>
      <a class="button-link button-link-subtle" href="{{ '/quick-tutorial/' | relative_url }}">Run the Tutorial</a>
    </div>
  </div>
</div>

## Why Teams Use QUASAR

<div class="metric-grid">
  <div class="metric-card">
    <p class="mini-label">Scope</p>
    <h3>Complete Chemistry Landscape</h3>
    <p>QUASAR is designed for the full range of atomistic research, from DFT and machine-learning potentials to molecular dynamics and adsorption simulations.</p>
  </div>
  <div class="metric-card">
    <p class="mini-label">Automation</p>
    <h3>Autonomous Complex Simulation</h3>
    <p>Go beyond simple chat. QUASAR plans multi-step scientific workflows, executes calculations, and validates intermediate results automatically.</p>
  </div>
  <div class="metric-card">
    <p class="mini-label">Adaptability</p>
    <h3>Modular Flexibility</h3>
    <p>Easily extend capabilities through your own models, custom tools, or prompt-time software installation to match your specific research needs.</p>
  </div>
  <div class="metric-card">
    <p class="mini-label">Integrity</p>
    <h3>Traceable & Reproducible</h3>
    <p>Comprehensive context management ensures every run stays traceable through checkpoints, archives, and detailed execution logs.</p>
  </div>
</div>

## Start Here

<div class="feature-grid">
  <a class="feature-card" href="{{ '/quick-tutorial/' | relative_url }}">
    <p class="mini-label">Walkthrough</p>
    <h3>Quick Tutorial</h3>
    <p>Follow a concrete first run around a silicon band-gap workflow from launch through result inspection.</p>
  </a>
  <a class="feature-card" href="{{ '/getting-started/' | relative_url }}">
    <p class="mini-label">Install</p>
    <h3>Getting Started</h3>
    <p>Choose Docker, Singularity, or local deployment, mount a workspace, and launch QUASAR correctly the first time.</p>
  </a>
  <a class="feature-card" href="{{ '/cli/' | relative_url }}">
    <p class="mini-label">Interface</p>
    <h3>CLI</h3>
    <p>Learn the interactive CLI, headless runs, resume behavior, cleanup commands, history browsing, and runtime checks.</p>
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
    <p>Learn when to install software in the prompt, when to bake it into the environment, and where first-class tools live in the codebase.</p>
  </a>
</div>

## What a Typical Run Looks Like

<div class="card-grid">
  <div class="step-card">
    <p class="mini-label">1. Prompt</p>
    <h3>Start From a Research Goal</h3>
    <p>Describe the scientific task you want done and the artifacts you want kept in the workspace.</p>
  </div>
  <div class="step-card">
    <p class="mini-label">2. Plan</p>
    <h3>Break Work Into Tasks</h3>
    <p>The Strategist creates a plan that reflects your requested rigor, granularity, and current workspace state.</p>
  </div>
  <div class="step-card">
    <p class="mini-label">3. Execute</p>
    <h3>Use Tools and Scientific Software</h3>
    <p>The Operator can read files, run Python, query documentation, and work through the task list inside the mounted workspace.</p>
  </div>
  <div class="step-card">
    <p class="mini-label">4. Review</p>
    <h3>Validate and Archive</h3>
    <p>The Evaluator checks task completion, and completed runs are archived for later inspection or follow-up work.</p>
  </div>
</div>

## Coverage Today

QUASAR is designed around atomistic research workflows and can support pipelines that touch DFT, machine-learning potentials, molecular dynamics, and adsorption-style simulation tasks. The broader toolchain around QUASAR includes projects such as Quantum ESPRESSO, ASE, MACE, pymatgen, LAMMPS, and RASPA3.

<div class="metric-grid">
  <div class="metric-card">
    <p class="mini-label">Runtime</p>
    <h3>CLI + Headless</h3>
    <p>The same run engine powers both the interactive terminal UI and direct one-shot prompts.</p>
  </div>
  <div class="metric-card">
    <p class="mini-label">Modeling</p>
    <h3>Provider Flexibility</h3>
    <p>The current codebase is especially tuned for Gemini-oriented setups, with additional provider support continuing to mature.</p>
  </div>
  <div class="metric-card">
    <p class="mini-label">Storage</p>
    <h3>Workspace-Centered</h3>
    <p>Results, logs, checkpoints, archives, and cached documentation all stay anchored to one mounted workspace.</p>
  </div>
</div>

## Recommended Reading Order

1. Read [Getting Started]({{ '/getting-started/' | relative_url }}) if you are installing or launching QUASAR for the first time.
2. Run the [Quick Tutorial]({{ '/quick-tutorial/' | relative_url }}) for a concrete end-to-end example.
3. Jump to [CLI]({{ '/cli/' | relative_url }}) for the interactive and headless command surface.
4. Keep [Configuration]({{ '/configuration/' | relative_url }}) nearby when tuning models, RAG, or execution rigor.
5. Use [Workspace & History]({{ '/workspace-history/' | relative_url }}) to understand result locations, archive behavior, and restart semantics.
6. Use [Extending QUASAR]({{ '/extending-quasar/' | relative_url }}) when you want to add more software or true first-class tools.