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

## Releases

`VERSION` is the release source of truth. When it changes on `main`, the release workflow validates the version, runs the tests, creates tag `v<version>`, publishes a GitHub Release, and attaches:

- `runtime-report.json`
- `release-manifest.txt`

After publication, the workflow downloads those assets again and verifies them byte-for-byte against the generated originals. Actions artifacts remain useful for CI diagnostics; GitHub Releases are the durable delivery surface.

## Issue-driven remote probes

Opening an Issue with the exact title `[workspace-probe]` triggers a controlled GitHub Actions task, but only when the Issue actor is the repository owner. The workflow runs the tests, executes the fixed runtime probe, posts a structured result back to the Issue, and closes the Issue on success.

For failure-path diagnostics, `[workspace-probe-fail]` deliberately fails the fixed probe contract after the tests. The workflow still posts a structured failure result, leaves the Issue open for diagnosis, and marks the Actions run as failed.

Opening `[network-probe]` runs a separate fixed-target DNS + HTTPS check against `https://example.com/`. The URL is hard-coded in the workflow; Issue content cannot choose the destination.

Issue bodies are deliberately ignored and are never executed as shell input.

## Review workflow

The repository has also exercised an inline review loop where the initial 3-version CI suite passed but review found a shared-mutable-state bug. The PR was corrected, a repeated-call regression test was added, the review thread was replied to and resolved, and the updated CI matrix passed before merge.

GitHub correctly refuses self-approval of a PR; independent approval still requires a separate GitHub identity.

## Current experiment status

The end-to-end path has been verified across repository mutation, low-level Git objects, PRs, inline review, CI failure diagnosis and repair, 3-version regression testing, Actions artifacts, automatic branch cleanup, durable Releases with asset round-trip verification, Issue-driven success/failure tasks, and a fixed-target network probe from GitHub Actions. The latest verified release is `v0.1.1`.

See `PROJECT_STATE.md` for the durable handoff notes and known platform/account boundaries.
