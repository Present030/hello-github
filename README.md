# Hello GitHub — Persistent Workspace Lab

This repository is a small experiment in using GitHub as the durable state for an otherwise ephemeral ChatGPT execution environment.

## Why it exists

The ChatGPT sandbox can run code, but its filesystem is temporary and it does not have direct outbound access to GitHub. The durable workflow tested here is therefore:

```text
ChatGPT reasoning
    ↕
GitHub connector
    ↕
repository / branches / pull requests
    ↕
GitHub Actions
    ↕
CI logs and artifacts
```

The repository is intentionally dependency-free so the experiment tests the collaboration path rather than package installation.

## Run locally

```bash
python -m hello_github
python -m hello_github --json
python -m unittest discover -s tests -v
```

## What CI verifies

GitHub Actions runs the unit tests on Python 3.11, 3.12, and 3.13. Each matrix job also uploads a small runtime report artifact. That artifact lets a later ChatGPT session inspect the result of code executed outside its temporary sandbox.

## Current experiment status

The initial capability pass verified repository reads/writes, branches, commits, pull requests, issues, CI execution, CI logs, and merges. The next pass adds a tested Python project and artifact round-trip.
