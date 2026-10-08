# Project State

Last reviewed: 2026-10-08 (latest successful cold-start evidence: 2026-09-29)

## Purpose

This public repository is a durable coordination point for experiments where ChatGPT reasoning, an ephemeral ChatGPT sandbox, the GitHub connector, and ephemeral GitHub Actions runners cooperate on a long-lived software project.

The repository is the source of truth. Temporary sandbox files and individual Actions runner filesystems are disposable.

## Current authoritative state

- Default branch: `main`.
- Repository visibility: public.
- Automatic deletion of merged PR head branches: enabled and verified.
- Active default-branch Ruleset: `main-protection` (PR required; deletion and force-push blocked; required check: `workspace-ci gate`; no bypass actors).
- Current application version: `0.3.0`.
- Latest verified release: `v0.3.0`.
- `v0.3.0` target commit: `8e7b6fbc69de8fceb8afcfef468a501fa69f43e9`.
- Latest executable Release asset: `hello-github.pyz`.
- Executable SHA-256: `a9ebb8c1e1bfd8686d3fdeacf1441e3388a13d6749ee98707f5f5167e9d6c30a`.
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
- `v0.3.0`

The current `v0.3.0` assets are:

- `hello-github.pyz` — 2307 bytes — SHA-256 `a9ebb8c1e1bfd8686d3fdeacf1441e3388a13d6749ee98707f5f5167e9d6c30a`
- `hello-github.cdx.json` — 639 bytes — SHA-256 `da151d3d4f1a26c8e397de2c654fe0884a4fbca3719ad56be0bbf945eade2c24`
- `hello-github-recovery.zip` — 5545 bytes — SHA-256 `2b4492aab5595d6b59d6d13c216ade03a0318e9a4d092fdc6d82a1c5ce2db420`
- `release-manifest.txt` — 335 bytes — SHA-256 `4de085701ff30ad02fcd81a015454fbdd88872609a204cb7136a93ecb29ce7e0`
- `runtime-report.json` — 167 bytes — SHA-256 `0190cedf575e85633d480a19fea7ac314129cd6fbbae9df3766ef9671c3d1785`

The formal Release workflow performs its own authenticated download-and-compare round trip for all five assets. The `v0.3.0` workflow was also re-run successfully against the existing Release: it reused the Release, reproduced all five local artifacts, matched every published asset byte-for-byte, and left the existing asset timestamps unchanged. Actions artifacts remain directly downloadable through the connector's dedicated artifact action.

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

## Repository protection, Pages permissions, and platform boundaries

- The temporary ChatGPT Linux sandbox used in this experiment did not have direct outbound DNS/HTTPS access to GitHub.
- GitHub access came through the authorized GitHub connector.
- GitHub Actions is a separate execution environment and does have outbound network access.
- The repository is now public.
- Ruleset `main-protection` is active on the default branch. It requires pull requests, blocks deletion and non-fast-forward updates, and requires `workspace-ci gate`; there are no bypass actors.
- A direct-write probe against `main` was rejected by GitHub, providing server-side evidence that the Ruleset is enforced.
- The connector can read the Ruleset, while the legacy branch-protection detail endpoint still returns `403 Resource not accessible by integration` because the managed GitHub App lacks the required administration scope.
- The connector currently exposes no direct `delete_ref` / `delete_branch` action.
- The repository's `delete_branch_on_merge` setting is enabled and has been verified as the normal cleanup mechanism.
- The connector currently exposes no general workflow-dispatch mutation. Manual `workflow_dispatch` runs that require inputs are triggered through the GitHub UI.
- GitHub code search can lag behind writes; exact file reads are the authoritative immediate check.
- GitHub does not permit the PR author to self-approve.
- Native GitHub Artifact Attestation is verified on the public repository: the dedicated probe generated provenance and `gh attestation verify` succeeded.
- The Pages workflow's declared permissions are `contents: read`, `pages: write`, and `id-token: write`. In a controlled manual run, its token received HTTP 403 when attempting Git-ref creation, while Pages upload/deploy, byte-for-byte public-content verification, and published-link verification all succeeded.
- The current pinned Pages actions use Node 24. The former Node 20 and `url.parse()` warnings are gone; `actions/deploy-pages v5.0.1` still emits one upstream `DEP0040` `punycode` deprecation warning, which is intentionally not hidden locally.

## Project health and Pages verification

`project-health` runs after a successful push-triggered `workspace-ci` on `main`. Two false-degraded edge cases were found and fixed during validation:

- the Actions runs API could briefly lag the just-completed CI run, so the triggering `workflow_run` event is now authoritative for the current CI evidence;
- limiting history to the first 100 Actions runs could hide an older critical workflow, so the workflow now paginates the complete run history before building the snapshot.

The post-fix run on `main@af957d31623df8c4bb992435005c9bfe8a42c27c` completed successfully and printed:

```text
PROJECT_HEALTH=healthy
```

The final manual Pages permission-boundary run on the same commit completed successfully. The token's Git-ref creation attempt was rejected with HTTP 403, then the same job deployed Pages and verified the live HTML byte-for-byte against the rendered artifact. The verified HTML SHA-256 was:

```text
e00e0c552d2393d12fbd461dbdc29e49e07b3ce71e26a04b1cc46e5318807bab
```

### Health evidence relationship and freshness policy (2026-10-08)

The `project-health` snapshot is a **point-in-time** assessment generated after a
completed push-triggered `workspace-ci` run on `main`. It is not a live monitoring
service; without a new snapshot, an old JSON artifact does not refresh itself.

Each required workflow entry records the GitHub Actions run ID, conclusion,
commit SHA, completion/update timestamp (`observed_at`), age, commit
`relation`, `freshness`, and derived `state`:

- `current`: successful, no older than **30 days**, with a commit SHA matching the
  triggering `main` CI commit. Only the triggering push CI can prove the current
  main CI gate, since ordinary probes and Pages run on separate triggers.
- `historical`: successful and within 30 days, but run against an older commit.
  This is supporting evidence **only**, not proof that the current `main`
  revision or current `v0.3.0` Release was tested by that workflow.
- `stale`: otherwise successful evidence older than 30 days.
- `unknown`: no completed run, missing/invalid timestamp or SHA, or
  timestamps too far in the future.
- `failed`: a recent completed run whose conclusion is not `success`.

An overall `healthy` result now requires: a successful fresh CI event for the
current `main` commit; `VERSION` agreement with the latest Release metadata;
and no required workflow evidence missing, failing, unknown, or stale. Recent
**historical** probe evidence is permitted but remains explicitly labeled
`historical`, never `current`.

The required workflow set also includes `cold-start-audit` and
`Deploy website to GitHub Pages`, in addition to CI, weekly health-check and
the existing release/recovery probes. The Pages run is tied to the commit
containing the deployed site, not necessarily today's `main` HEAD. Historical
recovery probes can intentionally exercise `v0.2.1`; success alone must not
be interpreted as a fresh recovery test of `v0.3.0`.

When a workflow ages beyond 30 days without a new qualifying run, the **next**
health snapshot becomes `degraded`. The separate failure-only snapshot from
item 01 retains its evidence of non-success main CI and does not pretend the
other audits were executed. A future public status feed must evaluate snapshot
age at viewing time and avoid publishing an old `healthy` as live status.

### Public Pages status feed (2026-10-08)

The `Deploy website to GitHub Pages` workflow now publishes
`https://present030.github.io/hello-github/status.json`, with
`schema: hello-github-public-status/v1`. The status is generated from a
`project-health` Actions artifact, **not** copied wholesale.

On Pages deployment, the workflow checks out **current `main`**, lists completed
`project-health` workflow runs, and selects only the latest run whose
`head_sha` matches that checked-out commit. It downloads the
`project-health` artifact using the Pages workflow's explicit read permission
(`actions: read`) and passes it to `tools/build_public_status.py`.

The exporter permits only a fixed set of keys: overall status, version,
Release tag and boolean asset presence, selected CI/recovery/Pages workflow
IDs, conclusions, related commit SHAs and timestamps. No arbitrary fields,
raw workflow output, secrets, or token values are published. Missing,
malformed, expired (older than **30 days**), or mismatched evidence produces
`unknown`, not a previous `healthy` result. The public document includes
`published_at`, `source_generated_at`, `source_run_id`, `head_sha` and
`expires_at`. The expiry derives from the source snapshot, **not** the Pages
re-deployment time: re-deploying the same historical health artifact does not
reset its age.

Pages deployment runs on site changes, on completed `project-health` runs,
and on a daily schedule to re-evaluate expiry without code changes. The
deployed JSON is fetched and compared byte-for-byte to the local, filtered
JSON; any discrepancy fails the deployment workflow. The Pages job checks
out default-branch source rather than potentially untrusted workflow-run
source. It gains `actions: read` but no repository write permission.

The site's existing HTML cards are still static. Roadmap item 04 will read
this feed and **re-check `expires_at` in the browser**; a static JSON
response cannot mutate itself after deployment. A failure in the Pages
deployment could also leave an older public document accessible, so the
expiry check is a consumer responsibility.

### Dynamic website evidence cards (2026-10-08)

The existing `site/index.html` now reads the published
`./status.json` feed with browser `fetch` and `cache: no-store`.
No backend, private token, third-party runtime or non-reproducible build asset
is required. Without JavaScript or when loading fails, status cards default
to **未知 / unknown** instead of embedded success claims.

The site checks the public schema, exact displayed version, full commit SHA,
health source run ID, `source_generated_at` and `expires_at`. It independently
rejects an expired snapshot, excessive future timestamp, and a claimed
healthy status unsupported by current-main CI evidence. Data is refreshed
every five minutes while the page remains open, and expiry is re-evaluated
every minute and when the page becomes visible again. Successful historical
release and recovery checks are labeled as historical, **not** validation of
the current source commit. SBOM's “included” label means the Release asset
inventory lists an SBOM, **not** that its current contents were re-verified.

All dynamic content is assigned with `textContent`, not `innerHTML`;
evidence URLs are assembled from a fixed repository Actions prefix and
validated numeric run IDs. Individual cards point to matching GitHub Actions
evidence; the summary points to the producing `project-health` run.
Version and stable download URLs still come from the repository's `VERSION`
at deployment. The existing site byte-level reproducibility and public
deployment comparison remain unchanged.

Unit tests execute the actual inline script under a minimal mocked DOM and
HTTP API in Node.js where available, covering evidence states, mismatch,
expiry and network fallback. ROADMAP item 05 still covers full browser and
end-to-end dynamic deployment validation.

### Real-browser end-to-end website regression (2026-10-08)

ROADMAP 05 adds a real headless Chrome browser gate, separate from the existing
Node.js mocked-DOM tests. `tools/check_site_browser.py` serves the **actual
rendered** HTML over localhost and executes its JavaScript in Chrome. Fixture
status JSON is constructed using `tools/build_public_status.py`, not an
unverified alternate schema. Test scenarios cover successful current CI and
historical Release/recovery, failed CI, stale data, version mismatch,
contradictory healthy claims, HTTP 503, missing HTTP 404 and malformed JSON.
The browser's produced DOM is examined for appropriate status labels.

The browser job is now a required part of `workspace-ci gate`. It uses the
GitHub-hosted Ubuntu runner's preinstalled Chrome, with no new runtime
dependencies, external test server or additional GitHub Token permissions.
Existing Ubuntu/Windows/macOS HTML byte-for-byte portability remains a
separate required gate.

After **every** Pages deployment, a Chrome smoke test visits the actual
public website and compares the rendered overview to the deployed
`status.json`, including expiry and version checks. The site cold-start
audit likewise reconstructs HTML without a checked-out source, compares it
byte-for-byte to published Pages, then exercises recovered HTML with browser
fixtures and checks the public site in Chrome.

The real-browser test uses headless Chrome only; multi-browser, mobile and
accessibility acceptance remain separate ROADMAP item 12. Real failing-main
CI delivery is not deliberately triggered here: the failure outcome is
validated with an isolated synthetic status feed.

### Verified Release prerequisite for Pages deployment (2026-10-08)

`VERSION` changes trigger `release` and Pages workflows independently; without
coordination, the website could point to a future Release before artifacts
exist or before formal round-trip verification completes.

Pages now has a separate `release-ready` job with **only**
`actions: read` and `contents: read`. Its deterministic gate checks the
checked-out `main` VERSION against the formal, non-draft, non-prerelease
tag; requires the five formal assets to be uploaded with positive sizes and
complete GitHub SHA-256 digests; and requires a **successfully completed
`release` workflow run** for the exact Release target commit. A successful
CI run is not interchangeable with a successfully verified Release.

When the Release is missing, incomplete, still being verified, or its
metadata cannot be fetched, the readiness job succeeds with `ready=false`
and the Pages `deploy` job is **skipped**, leaving the previously published
site in place. It does not ship a broken new-version download link or
misrepresent pending Release verification as a success. A later successful
main-branch `release` workflow completion triggers Pages again, in addition
to the existing site changes, health workflow completions, daily refresh
and manual trigger. Non-main and non-successful Release completions are
not accepted as publication signals.

Pages also compares the actual checked-out `main` SHA to the SHA assessed
by the readiness job before uploading any site content. The Pages HTML,
public JSON, byte-for-byte comparisons and Chrome smoke tests remain intact.
No artificial VERSION bump is required for the regression tests.

**Boundary:** the first *real* version upgrade still requires end-to-end
verification of the full propagation chain (ROADMAP 07). The current state
audit also requires README and PROJECT_STATE Release metadata, including
the executable digest, to be synchronized after the actual new Release.
Until a valid fresh health snapshot exists, the public status must remain
`unknown` rather than claiming current verification. The previously
published version may remain online during a pending Release; this is
intentional conservative behavior, not a claim that the new version shipped.

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

A repository-only cold-start audit has already recovered the project purpose, run/build commands, CI model, repository visibility, branch policy, recent history, and outstanding work successfully.


### Verified website cold-start recovery

On 2026-09-29, the `cold-start-audit` workflow completed successfully on
`main@90b5f2f2394e86c47483c48fe5c3567cf56c3b15` (run
[36530214522](https://github.com/Present030/hello-github/actions/runs/36530214522)):

- `cold-start` — started without checked-out source, independently verified the
  formal `v0.3.0` Release and its recovery bundle, recovered its release tag,
  and reproduced the three deterministic assets (`hello-github.pyz`,
  `hello-github.cdx.json`, and `hello-github-recovery.zip`) byte-for-byte.
- `site-cold-start` — independently started with no checked-out source,
  discovered the public Pages URL using the GitHub API, recovered the current
  default branch `main`, rendered `site/index.html` using the recovered
  `VERSION` and `tools/render_site.py`, then compared the HTML with the live
  Pages site byte-for-byte.

The independently recovered site matched
`https://present030.github.io/hello-github/`:

```text
SITE_SHA256=e00e0c552d2393d12fbd461dbdc29e49e07b3ce71e26a04b1cc46e5318807bab
```

The website recovery anchor is **current `main`**, not the `v0.3.0` release
tag: the website was introduced after that formal release. The first website
recovery run (PR #83) exposed an HTTP 404 when anonymously querying the Pages
API. PR #84 corrected discovery with a job-specific token granting
`contents: read` and `pages: read`; the original release recovery job
retained its existing `contents: read` boundary. The final run passed both
jobs without logged warnings.


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
