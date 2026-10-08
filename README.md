# Hello GitHub — Persistent Workspace Lab

This public repository is an experiment in using GitHub as the durable state and execution/control plane for an otherwise ephemeral ChatGPT working environment.

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
- Required real-browser checks run in Chrome and Firefox, including Chrome mobile reflow at 320/375/768 CSS px, keyboard Tab navigation, live status semantics, evidence-link accessibility and degraded network/error states. These do not constitute a full WCAG or physical-device audit.

Official GitHub Actions are pinned to immutable full commit SHAs rather than movable major-version tags. The pinned artifact upload/download Actions were refreshed to v7.0.2/v8.0.2 on 2026-10-08; a monthly Dependabot check proposes future update PRs for review (never auto-merged).

## Releases

Changing `VERSION` on `main` triggers the release workflow. It:

1. validates the semantic version,
2. runs the tests,
3. builds the zipapp twice and compares the bytes,
4. verifies the zipapp's embedded `--version`,
5. publishes tag `v<version>`,
6. creates or reuses Release `v<version>`,
7. publishes five formal assets: `hello-github.pyz`, `runtime-report.json`, `release-manifest.txt`, `hello-github.cdx.json`, and `hello-github-recovery.zip`,
8. downloads the published assets again,
9. byte-compares all five downloaded files,
10. executes the downloaded zipapp and recovery verifier,
11. re-verifies the version and runtime report.

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

The existing `v0.3.0` workflow was re-run successfully: it reused the existing Release,
rebuilt the five local artifacts, verified them against the already-published assets, and
did not replace or duplicate those assets.

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

## Repository protection and verified boundaries

The default branch is protected by the active repository Ruleset `main-protection`.
Changes to `main` must go through a pull request, deletion and force-push are blocked,
and the required status check is the stable `workspace-ci gate`. A controlled direct-write
probe was rejected by GitHub, confirming that the rule is enforced server-side.

The Pages workflow uses only `contents: read`, `pages: write`, and `id-token: write`.
A controlled probe using that same job token received HTTP 403 when attempting to create
a Git ref, while the same run still uploaded and deployed the Pages artifact and verified
the public page byte-for-byte.

Native GitHub Artifact Attestation is also verified for this public repository: a fixed
probe artifact was attested and then verified with `gh attestation verify`.

Formal Release provenance is now integrated for future VERSION-triggered
releases: all five published assets are attested after download and byte
validation, and independently verified by a read-only runner. The existing
`v0.3.0` assets are separately witnessed by a post-hoc verification
workflow; that **does not** imply the original build was attested at its
creation. Neither path adds or overwrites a formal Release asset. See
`PROJECT_STATE.md` for the security and evidence boundaries.

The current connector still does not expose direct branch/ref deletion or arbitrary
workflow-dispatch creation. Merged PR branches are normally removed by the repository's
automatic head-branch deletion setting; exceptional stale branches may require a small
manual cleanup in GitHub.

The current official `actions/deploy-pages v5.0.1` release still emits the
upstream Node `DEP0040` `punycode` warning. The latest
`actions/download-artifact v8.0.2` also still emits `DEP0005` `Buffer()`
warnings during artifact downloads. Both are documented rather than locally
suppressed; the older Node 20 and `url.parse()` warnings were resolved by
earlier Pages Action upgrades.

For the detailed durable handoff and exact verified boundaries, see `PROJECT_STATE.md`.
