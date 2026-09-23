# Project State

Last verified: 2026-09-23

## Purpose

This repository is a durable coordination point for experiments where ChatGPT reasoning and temporary execution environments collaborate through GitHub.

## Verified capabilities

- Read repository metadata and exact file contents.
- Create, update, and delete repository files.
- Create branches and move refs.
- Create Git blobs, trees, and commits directly.
- Compare commits and inspect diffs.
- Open, inspect, comment on, and merge pull requests.
- Create, read, comment on, update, and close issues.
- Create GitHub Actions workflows.
- Observe a failing CI run, read the failing job log, diagnose the assertion, push a correction, and observe the next run succeed.
- Run the test suite on Python 3.11, 3.12, and 3.13.
- Upload runtime-report artifacts from GitHub Actions.
- Download an Actions artifact back into a ChatGPT execution environment and inspect its contents.

## Observed boundaries

- The temporary ChatGPT Linux sandbox used during this experiment did not have direct outbound DNS/HTTPS access to GitHub.
- GitHub access therefore came through the authorized GitHub connector rather than ordinary `git clone` / `git push` from the sandbox.
- The connector surface used in this experiment did not expose a direct branch-delete operation, so merged test branches may remain until cleaned up elsewhere.
- GitHub code search can lag behind writes when the repository has not yet been indexed; exact file reads remain reliable.

## Durable workflow

```text
reason about change
      ↓
create/update branch through GitHub connector
      ↓
open PR
      ↓
GitHub Actions executes tests
      ↓
read status / logs / artifacts
      ↓
repair if needed
      ↓
merge
```

The GitHub repository is the source of truth. Temporary sandbox files are disposable and should not be treated as persistent project state.
