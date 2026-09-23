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
- Verify that merged PR branches are deleted automatically; deletion is asynchronous and may lag the merge by a few seconds.
- Create VERSION-driven GitHub Releases from Actions.
- Publish `runtime-report.json` and `release-manifest.txt` as Release assets and read their metadata, sizes, and SHA-256 digests through the connector.
- Verify Release assets end to end inside GitHub Actions by downloading the published assets and comparing them byte-for-byte with the files generated before publication.
- Release `v0.1.1` was published successfully from commit `79db05344ad606be6d8be6f39b8c2533bf0a88e5`; the workflow logged `PASS: release assets round-trip byte-for-byte`.
- Trigger a controlled remote workspace task from an owner-created `[workspace-probe]` Issue. The Actions job runs tests, generates a runtime report, comments the result, and closes the Issue on success.
- Verify the remote-task failure path with `[workspace-probe-fail]`: the workflow posts structured diagnostics first, leaves the Issue open, and the Actions run concludes `failure`.
- Verify that Issue body text is ignored by the worker and is not executed as shell input.
- Perform inline pull-request review, reply to a review thread, detect an issue that the initial CI suite missed, add a regression test, and resolve the thread after the corrected matrix CI passed.
- Verify that GitHub rejects self-approval of a pull request with `Review Can not approve your own pull request`; an independent approval requires another GitHub identity.
- Use an owner-only `[network-probe]` Issue to run a fixed-target DNS + HTTPS check from GitHub Actions. The verified run resolved `example.com` and received HTTP 200 from `https://example.com/`.
- Verify that the network probe ignores a different URL placed in the Issue body; the destination remains hard-coded in the workflow.

## Observed boundaries

- The temporary ChatGPT Linux sandbox used during this experiment did not have direct outbound DNS/HTTPS access to GitHub.
- GitHub access therefore came through the authorized GitHub connector rather than ordinary `git clone` / `git push` from the sandbox.
- GitHub Actions is a separate execution environment and does have outbound network access; controlled workflows can therefore handle fixed, reviewed network tasks without granting arbitrary network input through Issues.
- The connector surface used in this experiment did not expose a direct branch-delete operation.
- Repository setting `delete_branch_on_merge` is enabled and has been verified as the replacement for a connector delete-ref operation.
- GitHub code search can lag behind writes when the repository has not yet been indexed; exact file reads remain reliable.
- For this private repository, Release metadata and asset digests are readable, but attempting to fetch a private Release asset directly through its `browser_download_url` returned 404 with the current connector surface. The Release workflow therefore performs its own authenticated download-and-compare verification; Actions artifacts remain directly downloadable through the dedicated connector action.
- Reading `main` branch protection through the current GitHub integration returned `403 Resource not accessible by integration`.
- Repository rulesets on this private repository returned `403` with GitHub's message that GitHub Pro is required (or the repository must be public). Native required-status-check enforcement is therefore not available in the current repository/account setup.
- Because native branch rules are unavailable here, CI-before-merge remains a process convention rather than a server-enforced merge requirement.
- GitHub does not allow the PR author to approve their own pull request, even though the connector has repository administration permissions.

## Cold-start recovery

A new session can reconstruct the working state without relying on the previous sandbox or chat transcript by reading:

1. repository metadata,
2. `README.md`,
3. this `PROJECT_STATE.md`,
4. current branches,
5. recent commits,
6. open pull requests and issues,
7. relevant Actions runs and Releases.

A repository-only cold-start audit on 2026-09-23 recovered the project purpose, run commands, CI model, private visibility, branch policy, current branch state, recent history, and absence of open PRs/issues.

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
inline review can catch issues beyond the current tests
      ↓
repair + regression test + resolve review thread
      ↓
merge
      ↓
GitHub deletes merged head branch
      ↓
VERSION change publishes a durable GitHub Release
      ↓
Release workflow downloads its own assets and verifies them byte-for-byte

owner-created fixed Issue
      ↓
GitHub Actions controlled worker
      ↓
post structured success/failure result back to Issue
```

The GitHub repository is the source of truth. Temporary sandbox files are disposable and should not be treated as persistent project state.
