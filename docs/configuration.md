---
title: Configuration
description: Environment variables and runtime controls for QUASAR.
section: Tuning
lead: QUASAR is primarily configured via environment variables, with additional runtime options available through the command-line interface (CLI).
permalink: /configuration/
---

## Core Environment Variables

| Variable | Required | Purpose | Default |
| --- | --- | --- | --- |
| `MODEL` | Yes | Base model name for the system. | None |
| `MODEL_API_KEY` | Yes | API key for the base model provider. | None |
| `OPENAI_API_BASE` | No | Base URL for OpenAI-compatible global endpoints. | None |
| `ACCURACY` | No | Planning/execution rigor: `eco`, `standard`, `pro`. | `standard` |
| `GRANULARITY` | No | Task decomposition depth: `low`, `medium`, `high`. | `medium` |
| `AUTO_IMPROVE_CYCLES` | No | Number of automatic auto-improve follow-up runs after a successful user-started run. | `0` |
| `PMG_MAPI_KEY` | No | Materials Project database access | None |
| `IF_RESTART` | No | Resume from checkpoint when present. | `false` |

## Advanced Environment Variables

These settings are helpful for specialized workflows and can usually be left at their defaults unless you have a specific reason to change them.

| Variable | Required | Purpose | Default |
| --- | --- | --- | --- |
| `CONTEXT_THRESHOLD` | No | Context compression trigger level: `low` = 40%, `medium` = 60%, `high` = 80% of model context. | `medium` |
| `ENABLE_RAG` | No | Enable documentation retrieval. | `true` |
| `CHECK_INTERVAL` | No | Minutes between long-run LLM check-ins. Leave unset or use `0` to disable. | Disabled |
| `NUM_CORES` | No | Override physical core detection. | `Auto` |

## Per-Agent Model Overrides

You can override the shared global model for each agent independently.

| Agent | Model | API key | Base URL |
| --- | --- | --- | --- |
| Strategist | `STRATEGIST_MODEL` | `STRATEGIST_MODEL_API_KEY` | `STRATEGIST_API_BASE_URL` |
| Operator | `OPERATOR_MODEL` | `OPERATOR_MODEL_API_KEY` | `OPERATOR_API_BASE_URL` |
| Evaluator | `EVALUATOR_MODEL` | `EVALUATOR_MODEL_API_KEY` | `EVALUATOR_API_BASE_URL` |

A strong current combination in QUASAR is to use `gemini-3.1-pro-preview` for planning and evaluation, while using `gemini-3-flash-preview` for operation.

## Configuration Profiles

| Configuration Pattern | Typical Settings | Best For |
| --- | --- | --- |
| Balanced default | `ACCURACY=standard`, `GRANULARITY=medium` | General research workflows where you want a good balance of speed, structure, and completeness. |
| Faster exploration | `ACCURACY=eco` | Early-stage investigation, quick experiments, and situations where you want shorter iteration cycles. |
| Higher rigor | `ACCURACY=pro`, often with `GRANULARITY=high` | More demanding analyses where explicit planning, stronger verification, and fuller scientific coverage matter more than speed. |
| Long-running execution | Include `CHECK_INTERVAL` with any of the above profiles | Ideal for prolonged Python tasks, enabling periodic status checks instead of silent runs. Suggested initial value: 30 minutes |

A practical research workflow is to begin with `ACCURACY=eco` to establish a fast baseline, then switch to higher accuracy mode to refine the result through auto-improvement or a human-guided follow-up pass based on that initial run.