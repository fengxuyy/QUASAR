---
title: Configuration
description: Environment variables and runtime controls for QUASAR.
section: Tuning
lead: QUASAR is primarily configured via environment variables, with the same controls exposed in the browser Settings panel and CLI settings view.
permalink: /configuration/
---

## Core Environment Variables

| Variable | Required | Purpose | Default |
| --- | --- | --- | --- |
| `MODEL` | Yes | Base model name for the system. | None |
| `MODEL_API_KEY` | Yes | API key for the base model provider. | None |
| `OPENAI_API_BASE` | No | Base URL for OpenAI-compatible global endpoints (same effect as `API_BASE_URL`). | None |
| `API_BASE_URL` | No | Alias for `OPENAI_API_BASE` when routing the primary model through an OpenAI-compatible HTTP API. | None |

| `ACCURACY` | No | Planning/execution rigor: `eco`, `standard`, `pro`, or `adaptive` (experimental: scales numerical rigor with workflow stage). | `standard` |
| `GRANULARITY` | No | Task decomposition depth: `low`, `medium`, `high`, or `adaptive` (experimental: scales task count with perceived complexity). | `adaptive` |
| `AUTO_IMPROVE_CYCLES` | No | Number of automatic auto-improve follow-up runs after a successful user-started run. | `0` |
| `PMG_MAPI_KEY` | No | Materials Project database access | None |
| `IF_RESTART` | No | Resume from checkpoint when present. | `false` |

## Advanced Environment Variables

These settings are helpful for specialized workflows and can usually be left at their defaults unless you have a specific reason to change them.

| Variable | Required | Purpose | Default |
| --- | --- | --- | --- |
| `CONTEXT_THRESHOLD` | No | Context compression trigger level: `low` = 20%, `medium` = 40%, `hard` = 60% of model context. | `medium` |
| `ENABLE_RAG` | No | Enable documentation retrieval. | `true` |
| `NUM_CORES` | No | Override physical core detection. | `Auto` |
| `AUTO_CONFIRM_PLAN` | No | If `true`/`1`/`yes`/`on`, skips interactive plan confirmation (useful for headless or batch runs). | unset (confirmation on) |


Long-running Python check-ins are scheduled by the Operator per tool call through `execute_python(check_in_after=...)` and can be rescheduled with `continue_execution(next_check_in_after=...)`; there is no active `CHECK_INTERVAL` environment variable.



When resuming from a checkpoint, `ACCURACY` and `GRANULARITY` are locked to the saved run values so an interrupted workflow continues with the same planning assumptions.

## OpenAI-compatible LLM endpoints

QUASAR routes requests through an OpenAI-compatible HTTP client when:

- **`OPENAI_API_BASE` or `API_BASE_URL` is set** — all traffic for the primary model uses that base URL (for example a gateway, proxy, or third-party OpenAI-compatible host), regardless of model name.
- **The model name looks like OpenAI `gpt-*` and no custom base URL is set** — native OpenAI is used.
- **Per-agent base URLs** — `STRATEGIST_API_BASE_URL`, `OPERATOR_API_BASE_URL`, and `EVALUATOR_API_BASE_URL` override the global base URL for that agent when set (see table below).

Models whose names do **not** match built-in providers (Gemini, Claude, Grok, or `gpt-*`) **require** a base URL (`OPENAI_API_BASE`, `API_BASE_URL`, or the relevant per-agent URL); otherwise initialization fails with a clear configuration error.

## Per-Agent Model Overrides

You can override the shared global model for each agent independently.

| Agent | Model | API key | Base URL |
| --- | --- | --- | --- |
| Strategist | `STRATEGIST_MODEL` | `STRATEGIST_MODEL_API_KEY` | `STRATEGIST_API_BASE_URL` |
| Operator | `OPERATOR_MODEL` | `OPERATOR_MODEL_API_KEY` | `OPERATOR_API_BASE_URL` |
| Evaluator | `EVALUATOR_MODEL` | `EVALUATOR_MODEL_API_KEY` | `EVALUATOR_API_BASE_URL` |

For Gemini-oriented deployments, a common pattern is to use a stronger model for Strategist and Evaluator work while using a faster model for Operator execution. The exact model names should match the providers available in your environment.

## Configuration Profiles

| Configuration Pattern | Typical Settings | Best For |
| --- | --- | --- |
| Balanced default | `ACCURACY=standard`, `GRANULARITY=adaptive` | General research workflows where you want a good balance of speed, structure, and completeness. |
| Faster exploration | `ACCURACY=eco`, optionally `GRANULARITY=low` | Early-stage investigation, quick experiments, and situations where you want shorter iteration cycles. |
| Higher rigor | `ACCURACY=pro`, often with `GRANULARITY=high` | More demanding analyses where explicit planning, stronger verification, and fuller scientific coverage matter more than speed. |
| Adaptive control (experimental) | `ACCURACY=adaptive` and/or `GRANULARITY=adaptive` | Lets the Strategist and Operator adjust theory level and task breakdown based on workflow complexity instead of fixed presets. |


A practical research workflow is to begin with `ACCURACY=eco` to establish a fast baseline, then switch to higher accuracy mode to refine the result through auto-improvement or a human-guided follow-up pass based on that initial run.

## Machine learning in workflows

The Operator is instructed that the Python stack can include **scikit-learn** (declared in package metadata) and **PyTorch** (pulled in with the MACE ML potential stack and GPU-oriented images). You can ask QUASAR to fit models, preprocess data, or run small training jobs as part of a research workflow when your environment provides the necessary dependencies.
