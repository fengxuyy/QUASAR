<p align="center">
    <img src="logos/logo_text_fancy.png" alt="MOF-ChemUnity Logo" width="400"/>
</p>

<h1 align="center">Universal Autonomous System for Atomistic Research</h1>

A research-ready autonomous computational chemistry agentic system. QUASAR covers the full atomistic simulation pipeline with integrated tools including Quantum ESPRESSO, ASE, MACE, pymatgen, LAMMPS, and RASPA3. Currently optimised for Gemini models; other providers may not be fully functional. Broader compatibility coming in future releases.

<details>
<summary><strong>Quick Start</strong></summary>

### 1. Run via Docker

#### **Option A: CLI**
```bash
docker run --rm \
  -v "<workspace_path>:/workspace" \
  fengxuyang/quasar-chem:<tag> quasar
```

#### **Option B: Batch Mode (Headless)**
Pass a prompt directly as an argument for automated jobs:
```bash
docker run --rm \
  -e MODEL_API_KEY=<api_key> \
  -e MODEL=<model_name> \
  -v "<workspace_path>:/workspace" \
  --home "<workspace_path>:/workspace" \
  fengxuyang/quasar-chem:<tag> \
  quasar "Calculate the band structure of silicon"
```

### 2. HPC Singularity

#### **Option A: CLI (Interactive)**
```bash
singularity exec --cleanenv \
  -B "<workspace_path>:/workspace" \
  --home "<workspace_path>:/workspace" \
  --env MODEL_API_KEY=<api_key> \
  --env MODEL=<model_name> \
  <tag>.sif quasar
```

#### **Option B: Batch Mode (Headless)**
```bash
singularity exec --cleanenv \
  -B "<workspace_path>:/workspace" \
  --home "<workspace_path>:/workspace" \
  --env MODEL_API_KEY=<api_key> \
  --env MODEL=<model_name> \
  <tag>.sif quasar "Your research prompt here"
```

</details>

<br>

<details>
<summary><strong>Configuration</strong></summary>

When using CLI, configure the system via environment variables:

| Variable | Description | Default |
| :--- | :--- | :--- |
| `MODEL_API_KEY` | **Required.** Your API key (Gemini, Claude, OpenAI, etc.). | - |
| `MODEL` | **Required.** Model name. | - |
| `ACCURACY` | `eco` (fast/balanced) or `pro` (maximum rigor). | `pro` |
| `GRANULARITY` | Workflow task breakdown level (`low`, `medium`, `high`). | `medium` |
| `ENABLE_RAG` | Enable/disable documentation search. | `true` |
| `IF_RESTART` | Resume from the last checkpoint. | `false` |
| `PMG_MAPI_KEY` | Materials Project API key for `pymatgen`. | - |
| `CHECK_INTERVAL`| Minutes between LLM check-ins for long Python runs. | `15` |

</details>

<br>

<details>
<summary><strong>Workspace Structure</strong></summary>

All outputs are saved within the mounted workspace directory:

```
workspace/
├── final_results/      # Final outputs and analysis from the current run
│   └── summary.md      # Results summary
├── logs/               # Execution logs and usage reports
│   ├── usage_report.md # Token usage and cost breakdown
│   ├── overview.md     # High-level run summary
│   ├── input_messages.md # Input prompts sent to the agent
│   └── conversation/   # Conversation history
├── checkpoints.sqlite  # Checkpoint database for resumption
├── checkpoint_settings.json  # Run settings and token stats
├── archive/            # Historical runs (preserved across runs)
│   ├── run_1/          # First completed run
│   │   ├── final_results/
│   │   ├── logs/
│   │   └── ...         # All workspace files from that run
│   └── run_N/          # Subsequent runs
└── docs/               # Downloaded documentation (preserved)
```

When a run completes:
1. All workspace files are copied to `archive/run_N/`
2. Checkpoint files are removed from the workspace
3. The `archive/` and `docs/` directories are preserved for future runs

</details>

<br>

<details>
<summary><strong>Restart Mechanism</strong></summary>

QUASAR automatically checkpoints progress during execution. To resume from the last checkpoint:

**Docker:**
```bash
docker run --rm -e IF_RESTART=true \
  -v "<workspace_path>:/workspace" \
  fengxuyang/quasar-chem:<tag> quasar
```

**Singularity:**
```bash
singularity exec --cleanenv \
  --env IF_RESTART=true \
  -B "<workspace_path>:/workspace" \
  --home "<workspace_path>:/workspace" \
  <tag>.sif quasar
```

**When changing hardware** (e.g., moving to a different node or GPU):
1. Ensure the same workspace path is mounted
2. Set `IF_RESTART=true` to resume from the checkpoint
3. The system will continue from exactly where it left off

> **Note:** Checkpoints are stored in `checkpoints.sqlite` within the workspace. Completed runs are archived to `archive/run_N/` with their checkpoint data preserved.

</details>

<br>

### Contact & Advanced Usage

For the web service and advanced use, please email j.evans@adelaide.edu.au for more information.
