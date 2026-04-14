---
title: Quick Tutorial
description: A fast first-run tutorial for QUASAR using silicon band-gap calculation as the example.
section: Walkthrough
lead: This tutorial walks through a simple first run with QUASAR using the prompt “calculate the band gap of silicon,” from launch to inspecting the final results.
permalink: /quick-tutorial/
---

## Before You Start

Make sure you already have:

- a working runtime path such as Docker, Singularity, or local deployment
- `MODEL` and `MODEL_API_KEY` configured, or access to the interactive `\settings` panel
- a mounted or exported workspace directory

If not, complete [Get Started]({{ '/installation/' | relative_url }}) first.

## User Request

Here we need to provided scientific request to QUASAR. Providing a more detailed prompt is always recommended, as it gives QUASAR the scientific context needed to plan the right actions and ensures you receive the specific outputs you need. For tutorial purposes, we will use a short prompt.

```text
       ╭─────────────────────────────────────────────────────────────────────────────────────────╮
       │                                                                                         │
       │         ██████    █████  █████   █████████    █████████    █████████   ███████████      │
       │       ███░░░░███ ░░███  ░░███   ███░░░░░███  ███░░░░░███  ███░░░░░███ ░░███░░░░░███     │
       │      ███    ░░███ ░███   ░███  ░███    ░███ ░███    ░░░  ░███    ░███  ░███    ░███     │
       │     ░███     ░███ ░███   ░███  ░███████████ ░░█████████  ░███████████  ░██████████      │
       │     ░███   ██░███ ░███   ░███  ░███░░░░░███  ░░░░░░░░███ ░███░░░░░███  ░███░░░░░███     │
       │     ░░███ ░░████  ░███   ░███  ░███    ░███  ███    ░███ ░███    ░███  ░███    ░███     │
       │      ░░░██████░██ ░░████████   █████   █████░░█████████  █████   █████ █████   █████    │
       │        ░░░░░░ ░░   ░░░░░░░░   ░░░░░   ░░░░░  ░░░░░░░░░  ░░░░░   ░░░░░ ░░░░░   ░░░░░     │
       │                                                                                         │
       │                                                                                         │
       │                Quantum Universal Autonomous System for Atomistic Research               │
       │                                          v0.3.0                                         │
       │                                                                                         │
       ╰─────────────────────────────────────────────────────────────────────────────────────────╯


       ───────────────────────────────────────────────────────────────────────────────────────────
        ✴ Calculate the band gap of silicon.                                               Ctx 0%
       ───────────────────────────────────────────────────────────────────────────────────────────
        Shortcuts: \settings · ESC interrupt · Ctrl+D/Ctrl+C exit
```

## Confirmation and Settings

After submitting your request, QUASAR presents the current runtime settings for review. Confirm that these settings are correct before the autonomous run begins, then enter `yes` to proceed. For this tutorial, we configure the accuracy to `eco` and the `granularity` to low to enable a faster, lightweight run.

```text
        ╭─ Settings ───────────────────────────────────────────────────╮
        │ MODEL                    : gemini-3-flash-preview            │
        │ MODEL_API_KEY            : Set                               │
        │ OPENAI_API_BASE          : (not set)                         │
        │ ACCURACY                 : [eco]  standard   pro             │
        │ GRANULARITY              : [low]  medium   high              │
        │ CONTEXT_THRESHOLD        :  low  [medium]  high              │
        │ ENABLE_RAG               : [true]  false                     │
        │ PMG_MAPI_KEY             : Set                               │
        │ CHECK_INTERVAL           : (not set)                         │
        │ AUTO_IMPROVE_CYCLES      : 0                                 │
        │ NUM_CORES                : Auto                              │
        │ STRATEGIST_MODEL         : (not set)                         │
        │ STRATEGIST_MODEL_API_KEY : (not set)                         │
        │ STRATEGIST_API_BASE_URL  : (not set)                         │
        │ OPERATOR_MODEL           : (not set)                         │
        │ OPERATOR_MODEL_API_KEY   : (not set)                         │
        │ OPERATOR_API_BASE_URL    : (not set)                         │
        │ EVALUATOR_MODEL          : (not set)                         │
        │ EVALUATOR_MODEL_API_KEY  : (not set)                         │
        │ EVALUATOR_API_BASE_URL   : (not set)                         │
        ╰──────────────────────────────────────────────────────────────╯



       ───────────────────────────────────────────────────────────────────────────────────────────
        ✴ Submit this request? (yes/no)                                                    Ctx 0%
       ───────────────────────────────────────────────────────────────────────────────────────────
        Request to send: Calculate the band gap of silicon.
        Shortcuts: \settings · ESC interrupt · Ctrl+D/Ctrl+C exit
```

## Planning and Strategy

Once settings are confirmed, QUASAR’s **Strategist** takes over. It analyzes your prompt and environment to build a detailed execution plan. For this silicon example, it suggests a multi-task workflow involving structural relaxation, electronic density calculations, and final band structure extraction:

```text
        ¤ Strategist
          L ✓ Created Initial Plan
          L ✓ Reviewed Plan
            ╭─ Execution Plan ──────────────────────────────────────────────────────────────────╮
            │                                                                                   │
            │ Task 1: Integrated Structural Relaxation and Electronic Density Generation        │
            │ Guidance: Execute a unified workflow to obtain the ground-state configuration...  │
            │ ... [steps for relaxation, SCF, and convergence checks]                           │
            │                                                                                   │
            │ Task 2: Band Structure Execution, Gap Analysis, and Reporting                     │
            │ Guidance: Calculate the energy dispersion and synthesize results...               │
            │ ... [steps for NSCF, eigenvalues, plotting, and final summary]                    │
            ╰───────────────────────────────────────────────────────────────────────────────────╯


       ───────────────────────────────────────────────────────────────────────────────────────────
        ✴ Proceed with this plan? (yes/no)                                                 Ctx 0%
       ───────────────────────────────────────────────────────────────────────────────────────────
        Shortcuts: \settings · ESC interrupt · Ctrl+D/Ctrl+C exit
```

Review the plan and enter `yes` to begin the simulation.

## Execution and Tools

Once authorized, the Operator begins executing the tasks. In this phase, QUASAR starts preparing inputs and running calculations:

```text
        ¤ Operator
         ╭─ Task 1 ─────────────────────────────────────────────────────────────────────────────╮
         │ Integrated Structural Relaxation and Electronic Density Generation                   │
         ╰──────────────────────────────────────────────────────────────────────────────────────╯
          L ✓ Listed workspace
          L ✓ Listed docs/q-e
          L ✓ Listed docs/q-e/SSSP
          L ✓ Listed docs/q-e/SSSP/SSSP_1.3.0_PBE_efficiency (Si*)
          L ✓ Queried RAG pw.x input file for vc-relax and scf Sil... in qe
          L ⠸ Analysing Task


       ───────────────────────────────────────────────────────────────────────────────────────────
        ✸ yes                                                                    Ctx 1%  Task 1/2
       ───────────────────────────────────────────────────────────────────────────────────────────
        Shortcuts: \settings · ESC interrupt · Ctrl+D/Ctrl+C exit
```

## Task Completion and Evaluation

After each task, the **Evaluator** reviews the Operator's work to ensure scientific consistency and goal alignment. Here is the summary produced after Task 1 (Silicon relaxation and SCF):

```text
        ¤ Operator
         ╭─ Task 1 ─────────────────────────────────────────────────────────────────────────────╮
         │ Integrated Structural Relaxation and Electronic Density Generation                   │
         ╰──────────────────────────────────────────────────────────────────────────────────────╯
                ╭─ Evaluation Summary ──────────────────────────────────────────────────────────╮
                │ The Operator has successfully performed a unified workflow for Silicon. 1)    │
                │ They identified the PBE pseudopotential (SSSP efficiency). 2) Conducted a     │
                │ vc-relax calculation with a 40 Ry cutoff and 6x6x6 k-grid, resulting in an    │
                │ optimized cell parameter of 2.7346 Angstrom (which corresponds to a lattice   │
                │ constant of ~5.469 A). 3) Followed up with a high-accuracy SCF calculation    │
                │ using the relaxed geometry and a convergence threshold of 1e-8 Ry. Both       │
                │ calculations converged. The electronic density and ground-state configuration │
                │ are now ready for Task 2. Next, an NSCF calculation should be performed along │
                │ high-symmetry paths to determine the band gap.                                │
                ╰───────────────────────────────────────────────────────────────────────────────╯
```

With Task 1 validated, QUASAR automatically proceeds to Task 2 to calculate the final band gap dispersion and synthesize the results.

## Interrupt and Resume

If you need to stop an active run, press `ESC` twice in succession to interrupt. QUASAR will mark the run as interrupted and preserve the active checkpoint in the workspace.

To continue later, relaunch QUASAR with the same workspace and resume from that checkpoint:

```text
       ───────────────────────────────────────────────────────────────────────────────────────────
        ✴ Resume from checkpoint? (yes/no)                                                 Ctx 0%
       ───────────────────────────────────────────────────────────────────────────────────────────
        Shortcuts: \settings · ESC interrupt · Ctrl+D/Ctrl+C exit
```

If you decide not to continue the interrupted run, clear the active checkpoint before starting over:

```bash
quasar --clear
```

## Final Run Summary

When the entire research goal is reached, QUASAR produces a final **Run Summary**. This integrates the technical findings from all tasks into a single cohesive report:

```text
         ╭─ Run Summary ────────────────────────────────────────────────────────────────────────╮
         │                                                                                      │
         │ Band Gap Calculation of Silicon                                                      │
         │                                                                                      │
         │ Structural Parameters                                                                │
         │ - Optimized Lattice Constant: 5.4693 Å (PBE-relaxed)                                 │
         │ - Calculated Band Gap: 0.613 eV                                                      │
         │ ... [nature of the gap and methodological details]                                   │
         │                                                                                      │
         │ Contextualization                                                                    │
         │ The calculated band gap of 0.613 eV is significantly lower than the experimental     │
         │ value of 1.17 eV. This is a well-known behavior of the PBE functional ...            │
         │ ... [suggestions for higher-order methods like hybrid functionals or GW]             │
         ╰──────────────────────────────────────────────────────────────────────────────────────╯


       ───────────────────────────────────────────────────────────────────────────────────────────
        ✴ Previous results found. Enter to auto-improve (or 'no' to start fresh) Ctx 3%  Task 2/2
       ───────────────────────────────────────────────────────────────────────────────────────────
        Shortcuts: \settings · ESC interrupt · Ctrl+D/Ctrl+C exit
```

Once the summary is displayed, the agent remains active. You can press `Enter` to trigger an **auto-improvement cycle** where QUASAR self-evaluates the results for potential refinements, or you can type a follow-up request to extend the research (e.g., "Now calculate the effective masses at the VBM and CBM").

## Where to Look for Results

After a completed run, QUASAR archives the results under:

```text
workspace/archive/run_N/
```

Inspect these locations in the workspace:

| Path | Description |
| --- | --- |
| `logs/execution_overview.md` | A concise status file with the user request, current plan, and summaries of completed tasks. QUASAR updates it throughout the run, so it is the quickest way to check progress. |
| `logs/conversation.md` | A chronological record of agent activity, selected messages, completed tool calls, and evaluation results. Use it when you want a detailed view of what happened during the run. |
| `logs/input_messages.md` | A debugging log of the full messages sent to each agent, including timestamps and tool-call details. This is most useful when you need to inspect the exact context an agent received. |
| `final_results/summary.md` | The main written summary of the run's outcome. If the run ends without a complete result, this file may instead describe the unresolved issues. |
| `final_results/` | The folder containing the run's final deliverables, including any generated artifacts such as plots, tables, or exported data. |
| `logs/usage_report.md` | A usage report covering run status, duration, model and run settings, token counts, API requests, system details, and cost estimates when available. |
