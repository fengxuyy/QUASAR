---
title: Extending QUASAR
description: "How to let QUASAR use additional software, dependencies, and first-class tools."
section: Advanced
lead: "There are two practical ways to extend QUASAR: tell it to install something during a run for temporary use, or bake the dependency into the project for permanent and more reliable use."
permalink: /extending-quasar/
---

## Choose the Right Extension Level

<div class="card-grid">
  <div class="step-card">
    <p class="mini-label">Fastest</p>
    <h3>Prompt-Time Install</h3>
    <p>Best when you are experimenting and only need a dependency for one run.</p>
  </div>
  <div class="step-card">
    <p class="mini-label">Reliable</p>
    <h3>Project-Level Dependency</h3>
    <p>Best when the software should already exist every time QUASAR starts.</p>
  </div>
  <div class="step-card">
    <p class="mini-label">Reusable</p>
    <h3>First-Class Tool</h3>
    <p>Best when the capability deserves an explicit tool interface instead of being driven only through prompt instructions.</p>
  </div>
</div>

## The Short Rule

Use this rule of thumb:

1. For a one-off experiment or temporary dependency, include the install instruction directly in the prompt.
2. For repeated use, difficult installs, compiled software, or anything you want to rely on long term, add it to the repo environment with `requirements.txt` or a Dockerfile.

That matches how QUASAR is structured today.

## Option 1: Temporary Use Through the Prompt

If you only need a package for a single run, you can tell QUASAR to install it as part of the workflow.

This works best for:

- Python packages that can be installed with `pip`
- lightweight tools that can be fetched with `wget` or `curl`
- exploratory runs where you are still deciding whether the dependency is worth keeping

Example prompt:

```text
Calculate the band gap of silicon. If the required package is missing, install it first in the current environment and then continue. Treat the installation as temporary for this run, save the key scripts and outputs in the workspace, and summarize what was installed.
```

You can also be more explicit:

```text
Calculate the band gap of silicon. If needed, install <package_name> with pip before using it. If installation fails, explain the failure clearly and stop rather than silently changing methods.
```

### When This Is a Good Fit

- you are testing a new library
- the dependency is pure Python or otherwise easy to install
- you do not mind slower startup for that run
- you do not need the install to persist across fresh containers or future sessions

### Limitations

Prompt-based installs are less reliable when:

- the package needs system libraries or compilers
- the install is slow or brittle
- you need the dependency in many runs
- you want reproducible behavior across machines and images

In those cases, move to a permanent install.

## Option 2: Permanent Support in the Repo

If you want QUASAR to use software reliably and repeatedly, bake it into the environment.

### Add Python Dependencies to `requirements.txt`

Use [requirements.txt]({{ site.repository_url }}/blob/main/requirements.txt) when the new dependency is mainly a Python package.

This is the right place for packages like:

- analysis libraries
- file format libraries
- scientific Python packages
- helper packages QUASAR should always be able to import

After editing `requirements.txt`, rebuild the image you use for QUASAR.

### Add System Software to a Dockerfile

Use the Dockerfiles under [docker/]({{ site.repository_url }}/tree/main/docker) when the new dependency needs:

- `apt-get install`
- native binaries
- compilers
- GPU-specific runtime support
- large external scientific codes that should already exist in the image

Examples in this repo include:

- [docker/Dockerfile.amd64]({{ site.repository_url }}/blob/main/docker/Dockerfile.amd64)
- [docker/Dockerfile.arm64]({{ site.repository_url }}/blob/main/docker/Dockerfile.arm64)
- [docker/Dockerfile.cuda]({{ site.repository_url }}/blob/main/docker/Dockerfile.cuda)
- [docker/Dockerfile.rocm]({{ site.repository_url }}/blob/main/docker/Dockerfile.rocm)

If the install is architecture-specific or accelerator-specific, update the relevant image variant rather than only one file.

### When Permanent Installation Is the Better Choice

- you want the tool available in every run
- the installation is error-prone
- the software is large or compiled
- reproducibility matters
- you do not want the agent spending time reinstalling dependencies at runtime

## Which File Should I Change?

Use this quick guide:

| Situation | Best place |
| --- | --- |
| One-off package for a single run | Put install instructions in the prompt |
| Python package QUASAR should always have | `requirements.txt` |
| OS package, binary, compiler, or complex scientific code | A Dockerfile under `docker/` |
| Architecture- or GPU-specific software | The matching Dockerfile variant |

## Important Practical Difference

There are really two extension levels:

1. **Make software available** so QUASAR can use it from scripts during a run.
2. **Add a first-class QUASAR tool** so the agents can call it directly as part of the tool system.

Most people should start with level 1.

## If You Want a True First-Class QUASAR Tool

If you want something beyond “software the Operator can use from Python,” you will need code changes.

The main integration points are:

- tool definitions in [src/tools/]({{ site.repository_url }}/tree/main/src/tools)
- exported tools in [src/tools/__init__.py]({{ site.repository_url }}/blob/main/src/tools/__init__.py)
- agent tool maps in [src/agents/operator.py]({{ site.repository_url }}/blob/main/src/agents/operator.py), [src/agents/strategist.py]({{ site.repository_url }}/blob/main/src/agents/strategist.py), and [src/agents/evaluator.py]({{ site.repository_url }}/blob/main/src/agents/evaluator.py)

That path is worth taking when:

- the capability should be called repeatedly
- you want a stable interface instead of prompt instructions
- the same behavior should be available across many workflows

## Suggested Workflow

For most extensions, the cleanest progression is:

1. Try it once with explicit install instructions in the prompt.
2. If the dependency is useful and stable, move it into `requirements.txt` or the relevant Dockerfile.
3. If the capability deserves a reusable interface, implement it as a proper QUASAR tool.

This lets you explore quickly without committing too early, while still giving you a path to a durable setup once the tool proves useful.
