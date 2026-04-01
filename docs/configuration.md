---
title: Configuration
description: Environment variables and runtime controls for QUASAR-CHEM.
section: Tuning
lead: QUASAR-CHEM is configured primarily through environment variables, with command-level controls exposed through the CLI.
permalink: /configuration/
---

## Core Environment Variables

| Variable | Required | Purpose | Default |
| --- | --- | --- | --- |
| `MODEL` | Yes | Base model name for the system. | None |
| `MODEL_API_KEY` | Yes | API key for the base model provider. | None |
| `OPENAI_API_BASE` | No | Custom API base URL for the global model endpoint. | None |
| `ACCURACY` | No | Planning/execution rigor: `eco`, `standard`, `pro`. | `standard` |
| `GRANULARITY` | No | Task decomposition depth: `low`, `medium`, `high`. | `medium` |
| `CONTEXT_THRESHOLD` | No | Context compression trigger level: `low` = 40%, `medium` = 60%, `high` = 80% of model context. | `medium` |
| `ENABLE_RAG` | No | Enable documentation retrieval. | `true` |
| `CHECK_INTERVAL` | No | Minutes between long-run LLM check-ins. | `15` |
| `AUTO_IMPROVE_CYCLES` | No | Number of automatic auto-improve follow-up runs after a successful user-started run. | `0` |
| `NUM_CORES` | No | Override physical core detection. | `Auto` |
| `PMG_MAPI_KEY` | No | Materials Project access for `pymatgen`-driven tasks. | None |
| `IF_RESTART` | No | Resume from checkpoint when present. | `false` |
| `HF_TOKEN` | No | Hugging Face token for index/resource access when needed. | None |

## Per-Agent Model Overrides

You can override the shared global model for each agent independently.

| Agent | Model | API key | Base URL |
| --- | --- | --- | --- |
| Strategist | `STRATEGIST_MODEL` | `STRATEGIST_MODEL_API_KEY` | `STRATEGIST_API_BASE_URL` |
| Operator | `OPERATOR_MODEL` | `OPERATOR_MODEL_API_KEY` | `OPERATOR_API_BASE_URL` |
| Evaluator | `EVALUATOR_MODEL` | `EVALUATOR_MODEL_API_KEY` | `EVALUATOR_API_BASE_URL` |

If an agent override is not set, that agent falls back to the global `MODEL` and `MODEL_API_KEY`.

## Practical Tuning Advice

<div class="card-grid">
  <div class="step-card">
    <h3>`ACCURACY`</h3>
    <p>Use <code>eco</code> for faster exploration, <code>standard</code> for balanced work, and <code>pro</code> when you want the strongest emphasis on rigor and reproducibility.</p>
  </div>
  <div class="step-card">
    <h3>`GRANULARITY`</h3>
    <p>Lower values create broader tasks; higher values encourage more decomposition and more explicit execution steps.</p>
  </div>
  <div class="step-card">
    <h3>`ENABLE_RAG`</h3>
    <p>Keep this on if you want local documentation retrieval across the supported scientific toolchain.</p>
  </div>
  <div class="step-card">
    <h3>`CONTEXT_THRESHOLD`</h3>
    <p>Use <code>low</code> for earlier compression, <code>medium</code> for the balanced default, and <code>high</code> to preserve more raw conversation before compression kicks in.</p>
  </div>
  <div class="step-card">
    <h3>`CHECK_INTERVAL`</h3>
    <p>Helpful for long Python jobs that need periodic review rather than fully silent execution.</p>
  </div>
  <div class="step-card">
    <h3>`AUTO_IMPROVE_CYCLES`</h3>
    <p>Set this above <code>0</code> when you want QUASAR-CHEM to automatically launch additional auto-improve passes after a successful run completes.</p>
  </div>
</div>

## Checkpoint-Aware Settings

When QUASAR-CHEM resumes a checkpoint, it loads settings from `checkpoint_settings.json` and merges sensitive values like API keys back in from environment variables. This helps preserve the run’s original execution assumptions while avoiding direct checkpoint storage of secrets.

That means changing settings during resume is intentionally constrained. In particular, `ACCURACY` and `GRANULARITY` should stay aligned with the checkpointed run.

Automatic auto-improve chains also persist their remaining cycle budget in checkpoint metadata, so an interrupted follow-up run can resume and continue the remaining automatic passes.

## Example

```bash
export MODEL=gemini-2.5-pro
export MODEL_API_KEY=your_key_here
export ACCURACY=standard
export GRANULARITY=medium
export CONTEXT_THRESHOLD=medium
export ENABLE_RAG=true
export CHECK_INTERVAL=15
export AUTO_IMPROVE_CYCLES=0
export PMG_MAPI_KEY=your_materials_project_key
```

If you want to see how those settings affect run storage and resume behavior, continue with [Workspace & History]({{ '/workspace-history/' | relative_url }}).
