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
      <a class="button-link" href="{{ '/installation/' | relative_url }}">Get Started</a>
      <a class="button-link button-link-subtle" href="{{ '/quick-tutorial/' | relative_url }}">Quick Tutorial</a>
    </div>
  </div>
</div>

## Why Use QUASAR

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
  <a class="feature-card" href="{{ '/installation/' | relative_url }}">
    <p class="mini-label">Setup</p>
    <h3>Get Started</h3>
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
    <p>Learn when to install software in the prompt, when to bake it into the environment, and when system-prompt inclusion is enough versus when code changes are needed.</p>
  </a>
</div>
