---
title: Quick Tutorial
description: A fast first-run tutorial for QUASAR-CHEM using silicon band-gap calculation as the example.
section: Walkthrough
lead: This tutorial walks through a simple first run with QUASAR-CHEM using the prompt “calculate the band gap of silicon,” from launch to inspecting the final results.
permalink: /quick-tutorial/
---

## Goal

In this tutorial, we will ask QUASAR-CHEM to:

> Calculate the band gap of silicon.

This is a good first example because it is small enough to understand, but still exercises the full QUASAR flow:

- planning
- documentation retrieval
- task execution
- evaluation
- result archiving

## Before You Start

Make sure you already have:

- a working container image
- `MODEL` and `MODEL_API_KEY` configured
- a mounted workspace directory

If not, go through [Getting Started]({{ '/getting-started/' | relative_url }}) first.

## Recommended Prompt

You can use the short version:

```text
Calculate the band gap of silicon.
```

Or a slightly more explicit version:

```text
Calculate the band gap of silicon. Use a reproducible workflow, save the key input and output files in the workspace, and summarize the final band gap value, method, and assumptions.
```

The second version is often better for first runs because it nudges the final summary toward the information most people expect to review.

## Run the Example

Run a headless job:

```bash
docker run --rm \
  -e MODEL_API_KEY=<api_key> \
  -e MODEL=<model_name> \
  -v "<workspace_path>:/workspace" \
  fengxuyang/quasar:<tag> \
  quasar "Calculate the band gap of silicon. Use a reproducible workflow, save the key input and output files in the workspace, and summarize the final band gap value, method, and assumptions."
```

This is the fastest way to see QUASAR-CHEM do useful work end to end.

## What QUASAR-CHEM Will Typically Do

For this prompt, QUASAR-CHEM will usually move through a pattern like this:

1. The **Strategist** creates a plan for computing the band gap of silicon.
2. The **Operator** gathers context, checks relevant documentation/examples, prepares inputs, and runs the necessary calculations.
3. The **Evaluator** reviews whether the produced result is scientifically adequate for the current task.
4. If needed, QUASAR-CHEM loops until the task is complete or the run stops.

The exact workflow can vary depending on your model, settings, and environment.

## What to Watch During the Run

You will usually see:

- task progress updates as the plan advances
- agent activity from Strategist, Operator, and Evaluator
- files appearing in the workspace
- logs and summaries building up over time

## Where to Look for Results

When the run completes, inspect these locations in the workspace:

- `final_results/summary.md`
- `logs/execution_overview.md`
- `logs/usage_report.md`
- any generated calculation inputs/outputs relevant to the silicon workflow

After a completed run, QUASAR-CHEM archives the results under:

```text
workspace/archive/run_N/
```

You can inspect that archived run directly from the filesystem or from the CLI history tools.

## What Success Looks Like

A successful tutorial run should leave you with:

- a written summary of the silicon band gap result
- the method used to obtain it
- preserved logs showing how the run progressed
- archived artifacts you can reopen later

For a first pass, focus less on the exact numerical value and more on whether the workflow is reproducible and the outputs are easy to inspect.

## If the Run Stops Early

If QUASAR-CHEM is interrupted, do not start over immediately. Resume from the checkpoint instead:

```bash
quasar --resume
```

Or launch the container again with `IF_RESTART=true`.

This is especially important for longer scientific runs where you do not want to lose progress.

## Good Next Steps

Once the silicon example works, good follow-up prompts are:

- calculate the band structure of silicon and compare it with the reported band gap
- rerun the silicon workflow with a different level of rigor
- improve the previous run and explain what changed

From here, the most useful references are [Configuration]({{ '/configuration/' | relative_url }}) for tuning behavior and [Workspace & History]({{ '/workspace-history/' | relative_url }}) for understanding how results are stored.

If you want QUASAR-CHEM to use software that is not already available in the image, continue with [Extending QUASAR]({{ '/extending-quasar/' | relative_url }}).
