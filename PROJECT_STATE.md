# Project State

Last verified: 2026-09-23

## Purpose

This private repository is a durable coordination point for experiments where ChatGPT reasoning, an ephemeral ChatGPT sandbox, the GitHub connector, and ephemeral GitHub Actions runners cooperate on a long-lived software project.

The repository is the source of truth. Temporary sandbox files and individual Actions runner filesystems are disposable.

## Current authoritative state

- Default branch: `main`.
- Repository visibility: private.
- Automatic deletion of merged PR head branches: enabled and verified.
- Current application version: `0.2.1`.
- Latest verified release: `v0.2.1`.
- `v0.2.1` target commit: `131925b66b5ec7bec319cc2a9acaaef3d76e74a1`.
- Latest executable Release asset: `hello-github.pyz`.
- Executable SHA-256: `9945c0f8c4a31d2064af72c633528f79a85d769edcdd075c5f6b60e45909cd45`.
- Runtime dependencies: Python standard library only.

## Verified GitHub connector capabilities

- Read repository metadata and exact file contents.
- Create, update, and delete files through the contents API.
- Create branches.
- Create Git blobs, trees, and commits directly and move refs.
- Compare commits and inspect PR diffs/files.
- Open, inspect, comment on, and merge pull requests.
- Create, read, comment on, update, and close issues.
- Submit inline PR reviews, reply to review comments, list review threads, and resolve review threads.
- Read Actions runs, jobs, steps, logs, artifacts, and Release metadata.
- Download Actions artifacts through the connector's dedicated artifact action.
- Re-run supported failed Actions jobs/runs when needed.

## Verified development loop

A complete development loop has been exercised:

```text
branch
  ↓
code change
  ↓
pull request
  ↓
GitHub Actions
  ↓
inspect status/logs
  ↓
repair if needed
  ↓
inline review
  ↓
regression test
  ↓
resolve review thread
  ↓
merge
  ↓
automatic head-branch deletion
```

A deliberate CI failure was observed, diagnosed from the real Actions log, corrected in the same PR, and re-run successfully.

A separate review experiment demonstrated that green CI does not imply correctness: an inline review found a module-level shared-mutable-state bug that the original tests missed. The bug was fixed, repeated-call regression coverage was added, the review thread was resolved, and the updated matrix passed.

GitHub rejected an attempt to approve a PR authored by the same identity with:

```text
Review Can not approve your own pull request
```

Independent approval therefore still requires another GitHub identity.

## CI and reproducible executable delivery

Linux CI runs Python 3.11, 3.12, and 3.13.

Portability CI additionally runs Python 3.13 on:

- Windows,
- macOS.

The deterministic zipapp builder:

- fixes member ordering,
- fixes ZIP timestamps,
- fixes member permissions,
- uses deterministic compression settings,
- normalizes Python source text to LF before archiving.

The newline normalization was added after a real cross-platform discrepancy was diagnosed:

- Linux/macOS checkout: `hello_github/__main__.py` was 570 bytes with LF line endings.
- Windows checkout: the same file was 594 bytes with 24 CRLF sequences.
- Before normalization, Windows produced a different zipapp digest.
- After normalization, Linux, macOS, and Windows all produce the same artifact bytes.

For `v0.2.1`, all three operating systems produced:

```text
SHA-256 9945c0f8c4a31d2064af72c633528f79a85d769edcdd075c5f6b60e45909cd45
```

The same digest is recorded by GitHub for the released `hello-github.pyz` asset.

## Version consistency

`VERSION` is the single authoritative version input.

Source-tree execution reads `VERSION` directly. During zipapp construction, the builder injects the same value into `hello_github/_build_version.py`, so the built artifact does not depend on a nearby source-tree VERSION file.

The following agreement has been verified for `v0.2.1`:

```text
VERSION            = 0.2.1
release tag        = v0.2.1
source --version   = 0.2.1
zipapp --version   = 0.2.1
runtime JSON       = 0.2.1
downloaded zipapp  = 0.2.1
```

The release job logged:

```text
PASS: release tag, embedded version, assets, and runnable zipapp all agree
```

## GitHub Releases

The release workflow is triggered when `VERSION` changes on `main`.

It validates the version, runs tests, builds the executable twice, checks reproducibility, validates the embedded version, creates the GitHub Release, downloads the Release assets again, compares them byte-for-byte, runs the downloaded executable, and re-validates its version/runtime report.

Verified releases include:

- `v0.1.0`
- `v0.1.1`
- `v0.1.2`
- `v0.2.0`
- `v0.2.1`

The current `v0.2.1` assets are:

- `hello-github.pyz` — 2307 bytes — SHA-256 `9945c0f8c4a31d2064af72c633528f79a85d769edcdd075c5f6b60e45909cd45`
- `release-manifest.txt` — 247 bytes — SHA-256 `5bba6d102115b49f045ceb310b505654129f993bce652e3b2a8e1a7ead71e691`
- `runtime-report.json` — 167 bytes — SHA-256 `b105d8ca386c9097e9e81e61b294f27071963e4b681b741fbb00072bb860436e`

For private Release assets, the connector can read Release metadata and digests but could not directly download via `browser_download_url` in this experiment. The authenticated Release workflow therefore performs its own download-and-compare round trip. Actions artifacts remain directly downloadable through the dedicated connector action.

## Controlled Issue-driven workers

Only exact fixed Issue titles created by the repository owner are accepted. The Issue body is deliberately ignored and is never used as shell input, a URL, or another command parameter.

### `[workspace-probe]`

- runs the unit tests,
- executes a fixed runtime probe,
- posts structured results to the Issue,
- closes the Issue on success.

### `[workspace-probe-fail]`

- runs the same controlled path,
- deliberately fails a fixed probe contract,
- posts structured diagnostics before failing,
- leaves the Issue open for diagnosis,
- causes the Actions run to conclude `failure`.

### `[network-probe]`

A fixed outbound check to `https://example.com/` was verified.

An Issue body intentionally named `https://example.org/`, but the workflow still contacted only the hard-coded `example.com` target. DNS resolved and HTTPS returned 200.

This demonstrates that GitHub Actions can act as a controlled networked execution plane even though the ChatGPT sandbox itself lacked direct outbound GitHub/network access.

### `[cache-probe]`

A small counter is restored through GitHub Actions Cache and advanced on each valid run.

The verified chain is:

```text
0 → 1
1 → 2
2 → 3
3 → 4
```

The state survived independent ephemeral runners and an official Actions runtime refresh. This demonstrates that selected computation state can persist outside any individual runner filesystem.

## GitHub Actions supply-chain hardening

Official GitHub Actions are pinned to immutable full commit SHAs rather than movable tags:

- `actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1` — v7
- `actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97` — v7
- `actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a` — v7
- `actions/cache@55cc8345863c7cc4c66a329aec7e433d2d1c52a9` — v6

CI and probe workflows have successfully executed after this pinning.

## Observed platform/account boundaries

- The temporary ChatGPT Linux sandbox used in this experiment did not have direct outbound DNS/HTTPS access to GitHub.
- GitHub access came through the authorized GitHub connector.
- GitHub Actions is a separate execution environment and does have outbound network access.
- The connector currently exposes no direct `delete_ref` / `delete_branch` action.
- The repository's `delete_branch_on_merge` setting is enabled and has been verified as the normal cleanup mechanism.
- The connector currently exposes no general workflow-dispatch mutation, so fixed owner-created Issues are the controlled remote-task entry point used here.
- GitHub code search can lag behind writes; exact file reads are the authoritative immediate check.
- Reading `main` branch protection through the current integration returned `403 Resource not accessible by integration`.
- Repository rulesets on this private repository returned GitHub's `403` message that GitHub Pro is required or the repository must be public.
- Required-status-check enforcement is therefore not currently a server-side merge gate. CI-before-merge remains an explicit project convention.
- GitHub does not permit the PR author to self-approve.

## Cold-start recovery

A new ChatGPT session can reconstruct the project without relying on a previous sandbox or chat transcript by reading:

1. repository metadata,
2. `README.md`,
3. this `PROJECT_STATE.md`,
4. `VERSION`,
5. current branches,
6. recent commits,
7. open PRs/issues,
8. relevant Actions runs,
9. current Releases and asset metadata.

A repository-only cold-start audit has already recovered the project purpose, run/build commands, CI model, private visibility, branch policy, recent history, and outstanding work successfully.

## Durable model

```text
                         persistent
┌─────────────────────────────────────────────────┐
│ GitHub                                          │
│ code / Git history / PR / review / issues       │
│ Actions / cache / artifacts / tags / Releases   │
└───────────────────────┬─────────────────────────┘
                        ↕
                 GitHub connector
                        ↕
                     ChatGPT
                        ↕
             ephemeral local sandbox
```

The important state is intentionally kept outside the ephemeral sandbox and outside any single Actions runner.
