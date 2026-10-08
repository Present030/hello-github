# Contributing and independent review

## Current enforced workflow (audited 2026-10-08)

`main` is protected by the active [`main-protection` Ruleset](https://github.com/Present030/hello-github/rules/24155190). Every change requires a pull request and the successful **`workspace-ci gate`** check; branch deletion and force-push are prohibited and no bypass actors are configured. The pull-request rule currently requires **zero approvals**, deliberately supporting the present single-maintainer workflow. A passing CI run or an AI-assisted review is **not** an independent human approval.

Before merging a PR: describe its scope, inspect changes and CI logs, resolve issues, check version/Release and public-exposure boundaries when applicable, merge only after the required check passes, and verify the resulting `main` runs. Update `ROADMAP.md` / `PROJECT_STATE.md` as part of task closure. Never bump `VERSION` merely to exercise a release.

## Trigger to enable required independent review

Do **not** turn on required approvals until an independent, available human collaborator (a distinct GitHub identity with repository write permission) is confirmed and willing to review future changes. A PR author cannot approve their own PR. Do not create a second account, fake a review, appoint an unavailable reviewer, or treat a bot / automated analysis as an independent human approval. Collaborator availability is **not verified** by the current GitHub connector; the contributor or owner must confirm it in the repository UI.

Once that condition is met:

1. Open **Settings → Rules → Rulesets → `main-protection`**. Keep the existing target `~DEFAULT_BRANCH`, pull-request requirement, `workspace-ci gate`, deletion/non-fast-forward protections, and empty bypass list.
2. Under the **Require a pull request before merging** rule, change **Required approvals from 0 to 1**. Enable **Dismiss stale pull request approvals when new commits are pushed**, and **Require conversation resolution before merging**. Keep review attribution to an actual other person. Do not add a `CODEOWNERS` requirement until file ownership and independent coverage are confirmed; a solo code owner does not create a second reviewer. Avoid simultaneously enabling more stringent last-push controls without checking reviewer availability and GitHub's merge-base behavior.
3. Save the Ruleset and **read it back**, confirming `required_approving_review_count: 1`, `dismiss_stale_reviews_on_push: true`, `required_review_thread_resolution: true` while all existing checks and protections remain unchanged.
4. Exercise a real, harmless documentation PR by one maintainer: with green CI and **without** approval, GitHub must block merge. A different authorized human reviewer then submits an **Approve** review; only then should merge be available.
5. Before actually merging a separate test PR, or using an additional test PR if needed, push a new reviewable commit **after** approval and confirm the approval becomes stale and a **new** independent approval is necessary. If there is an unresolved review thread, confirm the rule blocks merging until it is resolved. Keep evidence links to the tested PR, reviewer identity, check run and Ruleset read-back.
6. Update `ROADMAP.md`, this guide and `PROJECT_STATE.md` with actual activation evidence. Only then mark ROADMAP 14 complete.

A collaborator may review PRs voluntarily before activation; that does **not** mean approvals are enforceable. The installed GitHub connector can read repository Rulesets and PR reviews, but **cannot update Ruleset administration settings**. The owner / authorized administrator must make the actual configuration change in GitHub's web UI. If the reviewer becomes unavailable, assess staffing and review continuity before changing policy; do not silently bypass enforcement.

## Evidence boundaries

As of the audit, [Ruleset 24155190](https://github.com/Present030/hello-github/rules/24155190) requires zero approving reviews, does not dismiss stale approvals, and does not require resolved conversations. PRs #100, #106 and #108 have no submitted approval reviews. These observations do **not** prove that no other collaborators exist; the connector cannot enumerate collaborator membership. ROADMAP 14 remains **pending activation**, not completed.

Official reference: [GitHub: available Ruleset rules](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets).
