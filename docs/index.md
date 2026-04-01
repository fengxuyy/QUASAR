---
title: QUASAR-CHEM Documentation
description: Documentation hub for installing, running, and understanding QUASAR-CHEM.
show_title: false
---

<div class="hero">
  <div>
    <span class="pill">Universal Autonomous System for Atomistic Research</span>
    <h1>Documentation for the full atomistic simulation workflow</h1>
    <p>
      QUASAR-CHEM is a research-ready autonomous computational chemistry system with a terminal-native CLI.
      It can plan a workflow, execute tasks inside a shared workspace, validate outputs, and archive complete runs for later inspection.
    </p>
    <div class="hero-actions">
      <a class="button-link" href="{{ '/getting-started/' | relative_url }}">Start With Setup</a>
      <a class="button-link button-link-subtle" href="{{ site.repository_url }}">Open GitHub</a>
    </div>
  </div>
  <div class="hero-panel">
    <p class="mini-label">Inside the loop</p>
    <ol class="stack-list">
      <li><strong>Strategist</strong> turns a research request into an execution plan.</li>
      <li><strong>Operator</strong> works through tasks with filesystem, Python, RAG, and web tools.</li>
      <li><strong>Evaluator</strong> checks whether each task is scientifically complete before the run advances.</li>
      <li><strong>Archive + restart</strong> preserve finished runs and let interrupted work resume from checkpoints.</li>
    </ol>
  </div>
</div>

## Start Here

<div class="feature-grid">
  <a class="feature-card" href="{{ '/quick-tutorial/' | relative_url }}">
    <p class="mini-label">Walkthrough</p>
    <h3>Quick Tutorial</h3>
    <p>Follow a first run using “calculate the band gap of silicon” as the working example.</p>
  </a>
  <a class="feature-card" href="{{ '/getting-started/' | relative_url }}">
    <p class="mini-label">Install</p>
    <h3>Getting Started</h3>
    <p>Run QUASAR-CHEM with Docker or Singularity using the interactive CLI or headless prompts.</p>
  </a>
  <a class="feature-card" href="{{ '/cli/' | relative_url }}">
    <p class="mini-label">Interface</p>
    <h3>CLI</h3>
    <p>Use interactive runs, headless prompts, checkpoint control, history, and system info.</p>
  </a>
  <a class="feature-card" href="{{ '/configuration/' | relative_url }}">
    <p class="mini-label">Tuning</p>
    <h3>Configuration</h3>
    <p>Set models, RAG, execution rigor, task granularity, Materials Project access, and agent overrides.</p>
  </a>
  <a class="feature-card" href="{{ '/workspace-history/' | relative_url }}">
    <p class="mini-label">Results</p>
    <h3>Workspace & History</h3>
    <p>Understand checkpoints, archives, preserved documentation, and where run outputs are stored.</p>
  </a>
  <a class="feature-card" href="{{ '/architecture/' | relative_url }}">
    <p class="mini-label">System</p>
    <h3>Architecture</h3>
    <p>See how Strategist, Operator, Evaluator, RAG resources, and restart behavior fit together.</p>
  </a>
  <a class="feature-card" href="{{ '/extending-quasar/' | relative_url }}">
    <p class="mini-label">Advanced</p>
    <h3>Extending QUASAR</h3>
    <p>Learn when to install extra software in the prompt, when to add it to the image, and where first-class tools live in the codebase.</p>
  </a>
</div>

## What QUASAR-CHEM Covers

QUASAR-CHEM is designed around atomistic research workflows and integrates tools including Quantum ESPRESSO, ASE, MACE, pymatgen, LAMMPS, and RASPA3. The current codebase is optimized primarily for Gemini-based model setups, while broader compatibility is still evolving.

<div class="metric-grid">
  <div class="metric-card">
    <p class="mini-label">Execution</p>
    <h3>CLI</h3>
    <p>Use the same run engine through the interactive terminal UI or direct headless prompts.</p>
  </div>
  <div class="metric-card">
    <p class="mini-label">Recovery</p>
    <h3>Checkpoint Resume</h3>
    <p>Interrupted runs can continue from saved state instead of starting over.</p>
  </div>
  <div class="metric-card">
    <p class="mini-label">Reference</p>
    <h3>Built-In Docs</h3>
    <p>Documentation repositories and example inputs are cached into the workspace for retrieval and inspection.</p>
  </div>
</div>

## Recommended Reading Order

1. Read [Getting Started]({{ '/getting-started/' | relative_url }}) if you are installing or launching QUASAR-CHEM for the first time.
2. Run the [Quick Tutorial]({{ '/quick-tutorial/' | relative_url }}) for a concrete end-to-end example.
3. Jump to [CLI]({{ '/cli/' | relative_url }}) for the interactive and headless command surface.
4. Keep [Configuration]({{ '/configuration/' | relative_url }}) nearby when tuning models, RAG, or execution rigor.
5. Use [Workspace & History]({{ '/workspace-history/' | relative_url }}) to understand result locations, archive behavior, and restart semantics.
6. Read [Architecture]({{ '/architecture/' | relative_url }}) when you need the higher-level mental model behind the app.
7. Use [Extending QUASAR]({{ '/extending-quasar/' | relative_url }}) when you want to add more software or true first-class tools.

<div class="callout callout-accent">
  <strong>Maintainer note:</strong> this site is designed to live in the repository’s root <code>docs/</code> folder and deploy through GitHub Pages.
</div>
