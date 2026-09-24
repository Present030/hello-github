# Hello GitHub — Persistent Workspace Lab

This private repository is an experiment in using GitHub as the durable state and execution/control plane for an otherwise ephemeral ChatGPT working environment.

## Architecture

```text
ChatGPT reasoning
    ↕
GitHub connector
    ↕
repository / branches / pull requests / issues / releases
    ↕
GitHub Actions
    ↕
CI / networked execution / cache / artifacts
```

The ChatGPT sandbox is treated as disposable. GitHub is the source of truth.

## Run from source

```bash
python -m hello_github
python -m hello_github --version
python -m hello_github --json
python -m unittest discover -s tests -v
```

`VERSION` is the single authoritative application version. Source execution reads it directly; built zipapps receive the same value at build time.

## Build the runnable zipapp

The project has no third-party runtime dependencies.

```bash
python tools/build_zipapp.py --output dist/hello-github.pyz
python dist/hello-github.pyz --version
python dist/hello-github.pyz --json
```

The builder normalizes Python source newlines and fixes ZIP member ordering, timestamps, permissions, and compression settings. This makes the built artifact independent of Windows CRLF checkout conversion.

For release `v0.2.1`, Linux, macOS, and Windows all produced the same zipapp SHA-256:

```text
9945c0f8c4a31d2064af72c633528f79a85d769edcdd075c5f6b60e45909cd45
```

## CI

The main CI verifies:

- Python 3.11, 3.12, and 3.13 on Linux.
- Python 3.13 portability on Windows and macOS.
- Unit tests.
- Two independent zipapp builds are byte-for-byte identical.
- The zipapp runs successfully.
- Source and zipapp JSON reports agree.
- Cross-platform builds produce a stable reproducible artifact.

Official GitHub Actions are pinned to immutable full commit SHAs rather than movable major-version tags.

## Releases

Changing `VERSION` on `main` triggers the release workflow. It:

1. validates the semantic version,
2. runs the tests,
3. builds the zipapp twice and compares the bytes,
4. verifies the zipapp's embedded `--version`,
5. publishes tag `v<version>`,
6. attaches `hello-github.pyz`, `runtime-report.json`, and `release-manifest.txt`,
7. downloads the published assets again,
8. byte-compares the downloaded files,
9. executes the downloaded zipapp,
10. re-verifies its version and runtime report.

Latest verified release: **v0.3.0**.

Its executable asset is:

```text
hello-github.pyz
SHA-256: a9ebb8c1e1bfd8686d3fdeacf1441e3388a13d6749ee98707f5f5167e9d6c30a
```

Starting with v0.3.0, the formal Release also publishes a deterministic CycloneDX SBOM
(`hello-github.cdx.json`) and a deterministic self-verifying disaster-recovery bundle
(`hello-github-recovery.zip`). The release workflow downloads and byte-compares all
published assets and runs the downloaded recovery bundle verifier.

The release workflow verified:

```text
VERSION
= release tag
= source --version
= built zipapp --version
= runtime-report.version
= downloaded zipapp --version
```

## Issue-driven remote probes

Only Issues opened by the repository owner and having an exact fixed title can trigger these workflows. Issue bodies are ignored and never executed as commands.

- `[workspace-probe]`: runs tests and a fixed runtime probe, posts a structured result, then closes on success.
- `[workspace-probe-fail]`: deliberately exercises the failure path; diagnostics are posted before the Actions run fails, and the Issue remains open for diagnosis.
- `[network-probe]`: performs a fixed DNS + HTTPS check against `https://example.com/`. The Issue body cannot choose another destination.
- `[cache-probe]`: restores and advances a tiny counter stored through GitHub Actions Cache.

The cache experiment demonstrated state restoration across independent ephemeral runners:

```text
0 → 1 → 2 → 3 → 4
```

The chain continued successfully across an Actions runtime refresh.

## Review workflow

The repository has exercised a full inline review loop where the initial Linux matrix CI was green but review found a shared-mutable-state bug. The fix added regression coverage, the review thread was replied to and resolved, and the corrected CI passed before merge.

GitHub correctly refuses self-approval of a pull request. Independent approval requires another GitHub identity.

## Known boundaries

The current connector does not expose direct branch/ref deletion or arbitrary workflow-dispatch creation. Merged PR branches are instead removed using the repository's verified `delete_branch_on_merge` setting.

For this private repository, native repository rulesets require a higher GitHub plan; required-status-check enforcement is therefore not currently a server-side merge gate. CI-before-merge is an explicit project convention.

For the detailed durable handoff and exact verified boundaries, see `PROJECT_STATE.md`.
