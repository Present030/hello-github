# hello-github Improvement Roadmap

Last audited: 2026-10-08

This is the durable backlog for the Persistent Workspace Lab. It distinguishes verified baselines from unfinished work. Change one item at a time through a PR, required CI gate, merge, and post-merge verification. Do not manufacture a version bump solely to run a release experiment.

## P0 — Trustworthy status and dynamic website

- [x] **01. Record non-success main CI outcomes.** Extend `project-health` to emit a `degraded` artifact when `workspace-ci` on `main` fails or is cancelled, without relying on the failed revision's source tree. Verify the event-to-JSON contract with synthetic failure/cancellation tests. *Note: an intentionally failing protected-main CI run is not part of this change; its first real occurrence must be checked independently.*
- [x] **02. Define health evidence freshness and scope.** Distinguish current, historical, unknown, and stale evidence. Extend checks to relevant website/recovery workflows; document how timestamps and version/commit relationships affect health.
- [x] **03. Publish an anonymous-safe status feed for Pages.** Expose a stable structured resource derived from controlled Actions evidence; ensure no private tokens or internal data reach the public site.
- [x] **04. Render real project status on the website.** Replace hard-coded CI/Release/Recovery/SBOM labels with evidence-backed status, timestamps, and links. Make unavailable data visibly unknown rather than silently green.
- [x] **05. Test the dynamic website end-to-end.** Cover success, failure, stale data, network errors, cross-platform rendering, cold-start recovery, and verification of the published site.

## P1 — Publication and operational closure

- [x] **06. Coordinate Release and Pages version propagation.** Confirm that VERSION-triggered Pages deployment cannot falsely report an unverified or unavailable Release. Verify release-first behavior or explicit pending status.
- [ ] **07. Verify propagation on the next real version release.** Check `VERSION → Release → SBOM → recovery bundle → Pages → live links`. Do not fabricate a version solely for this experiment.
- [ ] **08. Attest formal Release artifacts.** Extend the already-proven native Artifact Attestation probe to formal deliverables and verify the published provenance independently.
- [ ] **09. Expand unattended integrity checks.** Ensure periodic checks cover all formal Release assets, provenance, and selected recovery paths, not only the executable zipapp.
- [ ] **10. Improve alerts and recovery closure.** Cover key workflow failures consistently without noisy duplicate Issues; record recovery evidence and close resolved incidents.
- [ ] **11. Maintain pinned GitHub Actions dependencies.** Periodically assess official Action updates and warnings, keep immutable SHA pins, and do not hide upstream deprecations.

## P2 — Presentation and long-term maintenance

- [ ] **12. Add browser, mobile, and accessibility checks.** Validate interactive states, keyboard navigation, and graceful error behavior.
- [ ] **13. Review SBOM and exposure-audit coverage.** Make known limits explicit, add coverage as dependencies and public content expand, and keep privacy heuristics separate from high-confidence secret detection.
- [ ] **14. Enable independent reviews when multi-person development begins.** The current protected main requires PR plus `workspace-ci gate`, but permits zero approvals as a conscious single-maintainer choice.

## Verified foundation (keep as regression gates)

- GitHub-backed cross-session code history, PR review and automatic merged-branch cleanup.
- Multi-Python / multi-OS reproducible builds and website rendering.
- Formal `v0.3.0` five-asset Release, round-trip integrity, idempotent re-run.
- Enforced `main-protection` Ruleset; least-privilege workflow probes and job-level permission auditing.
- Project health CI sequencing/pagination fixes.
- Source-free Release recovery and independent site cold-start byte comparison.
- Native Artifact Attestation probe (not yet attached to the formal Release).

## Evidence discipline

A passing previous run is historical evidence, not proof that the current main or website is healthy. Failure snapshots must identify the triggering run and may leave unrelated checks unknown. A real failing-main end-to-end drill is deferred rather than introducing a deliberately broken commit into the protected branch.
