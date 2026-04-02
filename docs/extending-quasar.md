---
title: Extending QUASAR
description: "How to let QUASAR use additional software and capabilities through prompt-time install, environment setup, or system-prompt inclusion."
section: Advanced
lead: "There are three practical ways to extend QUASAR: install something temporarily during a run, bake it into the environment for reliable reuse, or add system-prompt guidance so QUASAR knows to use it by default."
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
    <h3>System Prompt Inclusion</h3>
    <p>Best when the software is already available and QUASAR should be guided to use it by default without repeating the instruction in each user prompt.</p>
  </div>
</div>

## The Short Rule

1. For a one-off experiment or temporary dependency, include the install instruction directly in the prompt.
2. For repeated use, difficult installs, compiled software, or anything you want to rely on long term, add it to the repo environment with `requirements.txt` or the Dockerfile.
3. If the software is already available and should be part of QUASAR's default behavior, add that guidance to the relevant system prompts.

## Option 1: Temporary Use Through the Prompt

If you only need a package for a single run, you can tell QUASAR to install it as part of the workflow.

This works best for:

- Python packages that can be installed with `pip`
- lightweight tools that can be fetched with `wget` or `curl`
- exploratory runs where you are still deciding whether the dependency is worth keeping

Example prompt:

```text
Calculate the accessible surface area of MOF-5. Installation of Zeo++ is needed.
```

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

## Option 3: System Prompt Inclusion

Use this level when the software is already installed and you want QUASAR to know, by default, when and how to use it.

Typical integration points include the agent system prompts in:

- [src/agents/strategist.py]({{ site.repository_url }}/blob/main/src/agents/strategist.py)
- [src/agents/operator.py]({{ site.repository_url }}/blob/main/src/agents/operator.py)
- [src/agents/evaluator.py]({{ site.repository_url }}/blob/main/src/agents/evaluator.py)

## Suggested Workflow

For most extensions, the cleanest progression is:

1. Try it once with explicit install instructions in the prompt.
2. If the dependency is useful and stable, move it into `requirements.txt` or the relevant Dockerfile.
3. If the software should be part of QUASAR's default behavior, add the relevant guidance to the system prompts.