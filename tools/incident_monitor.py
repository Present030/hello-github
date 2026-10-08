"""Deduplicated, main-only GitHub Actions failure and recovery incidents.

This runs only from a trusted default-branch checkout. Workflow-run payloads
are untrusted evidence: never execute their SHA, artifacts, or text.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from urllib.parse import urlencode
from urllib.request import Request, urlopen

# The weekly health-check keeps its already-verified, self-managed incident.
MONITORED = {
    "workspace-ci": {"push"},
    "project-health": {"workflow_run"},
    "release": {"push"},
    "Deploy website to GitHub Pages": {"push", "workflow_run", "schedule", "workflow_dispatch"},
    "cold-start-audit": {"push", "workflow_dispatch"},
}
FAILURES = {"failure", "cancelled", "timed_out", "action_required", "startup_failure"}
MARKER = re.compile(r"<!-- incident-failure:(\d+):(\d+) -->")
SHA = re.compile(r"[0-9a-f]{40}")


def api_request(method: str, path: str, payload: dict | None = None):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = Request(
        "https://api.github.com" + path,
        method=method,
        data=data,
        headers={
            "Authorization": "Bearer " + os.environ["GH_TOKEN"],
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        },
    )
    with urlopen(request, timeout=30) as response:
        raw = response.read()
    return json.loads(raw) if raw else None


def _key(run: dict) -> tuple[int, int]:
    return int(run.get("id", 0)), int(run.get("run_attempt") or 1)


def _runs(api, repo: str, workflow: str) -> list[dict]:
    path = f"/repos/{repo}/actions/workflows/{workflow}/runs?branch=main&per_page=100"
    response = api("GET", path)
    return response.get("workflow_runs", [])


def _open_issue(api, repo: str, title: str) -> dict | None:
    # Pagination and exact title comparison avoid a fuzzy search match.
    for page in range(1, 21):
        items = api("GET", f"/repos/{repo}/issues?state=open&per_page=100&page={page}")
        for item in items:
            if "pull_request" not in item and item.get("title") == title:
                return item
        if len(items) < 100:
            break
    return None


def _last_failure(body: str) -> tuple[int, int]:
    matches = MARKER.findall(body or "")
    return max(((int(a), int(b)) for a, b in matches), default=(0, 0))


def _evidence(run: dict, repo: str) -> str:
    run_id, attempt = _key(run)
    link = f"https://github.com/{repo}/actions/runs/{run_id}"
    if attempt > 1:
        link += f"/attempts/{attempt}"
    return link


def process_event(event: dict, repo: str, api=api_request) -> str:
    run = event.get("workflow_run") or {}
    name = run.get("name")
    if (
        name not in MONITORED
        or run.get("event") not in MONITORED[name]
        or run.get("head_branch") != "main"
        or (run.get("head_repository") or {}).get("full_name") != repo
        or run.get("status") != "completed"
        or not SHA.fullmatch(str(run.get("head_sha") or ""))
        or not isinstance(run.get("workflow_id"), int)
        or not isinstance(run.get("id"), int)
        or run.get("id", 0) < 1
    ):
        return "ignored_out_of_scope"

    conclusion = run.get("conclusion")
    if conclusion not in FAILURES | {"success"}:
        return "ignored_non_actionable"

    # Late workflow_run events must not reopen recovered failures or prematurely
    # close a newer failure. The triggering event is authoritative if API listing
    # has not indexed it yet (a known GitHub Actions eventual-consistency race).
    completed = [
        item for item in _runs(api, repo, str(run["workflow_id"]))
        if item.get("head_branch") == "main"
        and item.get("event") in MONITORED[name]
        and item.get("status") == "completed"
    ]
    if completed and max(map(_key, completed)) > _key(run):
        return "ignored_stale_event"

    # project-health intentionally fails while publishing a degraded snapshot
    # after failed main CI. The parent CI already owns that incident.
    if name == "project-health" and conclusion in FAILURES:
        ci = _runs(api, repo, "ci.yml")
        if any(
            item.get("event") == "push"
            and item.get("head_branch") == "main"
            and item.get("head_sha") == run["head_sha"]
            and item.get("status") == "completed"
            and item.get("conclusion") in FAILURES
            for item in ci
        ):
            return "ignored_expected_ci_degradation"

    title = f"[workflow-failure] {name}"
    issue = _open_issue(api, repo, title)
    current = _key(run)

    if conclusion in FAILURES:
        body = (
            f"Unresolved failure in `{name}`.\n\n"
            f"- last failure: {_evidence(run, repo)}\n"
            f"- conclusion: {conclusion}\n"
            f"- commit: {run['head_sha']}\n\n"
            f"<!-- incident-failure:{current[0]}:{current[1]} -->"
        )
        if issue is None:
            api("POST", f"/repos/{repo}/issues", {"title": title, "body": body})
            return "opened"
        previous = _last_failure(issue.get("body") or "")
        if current <= previous:
            return "ignored_duplicate_or_older_failure"
        api("PATCH", f"/repos/{repo}/issues/{issue['number']}", {"body": body})
        api("POST", f"/repos/{repo}/issues/{issue['number']}/comments", {
            "body": f"Another {name} failure ({conclusion}): {_evidence(run, repo)}"
        })
        return "updated"

    if issue is None:
        return "no_incident"
    if current <= _last_failure(issue.get("body") or ""):
        return "ignored_older_success"
    api("POST", f"/repos/{repo}/issues/{issue['number']}/comments", {
        "body": f"Recovered after a newer successful {name} run: {_evidence(run, repo)}"
    })
    api("PATCH", f"/repos/{repo}/issues/{issue['number']}", {
        "state": "closed", "state_reason": "completed"
    })
    return "closed"


def main() -> int:
    parser = argparse.ArgumentParser(description="Process a trusted-main workflow incident.")
    parser.add_argument("--event", required=True)
    parser.add_argument("--repo", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", args.repo):
        parser.error("invalid repository name")
    with open(args.event, encoding="utf-8") as handle:
        event = json.load(handle)
    print("INCIDENT_MONITOR=" + process_event(event, args.repo))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
