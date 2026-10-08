"""Exercise the real incident handler against a small in-memory GitHub API."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import unittest

from tools.incident_monitor import process_event


REPO = "Present030/hello-github"
SHA = "a" * 40


def event(name="workspace-ci", run_id=100, conclusion="failure", *,
          attempt=1, origin="push", branch="main", repository=REPO,
          workflow_id=17, sha=SHA):
    return {"workflow_run": {
        "name": name, "id": run_id, "workflow_id": workflow_id,
        "run_attempt": attempt, "conclusion": conclusion,
        "head_sha": sha, "head_branch": branch,
        "head_repository": {"full_name": repository},
        "event": origin, "status": "completed",
    }}


class FakeGitHub:
    def __init__(self):
        self.issues = []
        self.runs = {}
        self.comments = []
        self.calls = []

    def __call__(self, method, path, payload=None):
        self.calls.append((method, path, deepcopy(payload)))
        if method == "GET" and "/actions/workflows/" in path:
            workflow = path.split("/actions/workflows/", 1)[1].split("/", 1)[0]
            return {"workflow_runs": deepcopy(self.runs.get(workflow, []))}
        if method == "GET" and "/issues?" in path:
            return [deepcopy(x) for x in self.issues if x.get("state") == "open"]
        if method == "POST" and path.endswith("/issues"):
            item = {"number": len(self.issues) + 1, "state": "open", **payload}
            self.issues.append(item)
            return deepcopy(item)
        if method == "POST" and path.endswith("/comments"):
            self.comments.append(payload["body"])
            return {}
        if method == "PATCH" and "/issues/" in path:
            number = int(path.rsplit("/", 1)[1])
            issue = next(x for x in self.issues if x["number"] == number)
            issue.update(payload)
            return deepcopy(issue)
        raise AssertionError(f"unexpected API call: {method} {path}")

    def add_run(self, data):
        self.runs.setdefault(str(data["workflow_run"]["workflow_id"]), []).append(
            deepcopy(data["workflow_run"])
        )


class IncidentMonitorTests(unittest.TestCase):
    def test_failure_deduplicates_and_newer_success_closes_with_evidence(self):
        api = FakeGitHub()
        first = event()
        api.add_run(first)
        self.assertEqual(process_event(first, REPO, api), "opened")
        self.assertEqual(len(api.issues), 1)
        self.assertIn("incident-failure:100:1", api.issues[0]["body"])
        self.assertEqual(process_event(first, REPO, api), "ignored_duplicate_or_older_failure")
        self.assertEqual(len(api.comments), 0)

        second = event(run_id=101, conclusion="timed_out")
        api.add_run(second)
        self.assertEqual(process_event(second, REPO, api), "updated")
        self.assertEqual(len(api.issues), 1)
        self.assertEqual(len(api.comments), 1)
        self.assertIn("incident-failure:101:1", api.issues[0]["body"])

        success = event(run_id=102, conclusion="success")
        api.add_run(success)
        self.assertEqual(process_event(success, REPO, api), "closed")
        self.assertEqual(api.issues[0]["state"], "closed")
        self.assertIn("runs/102", api.comments[-1])
        self.assertEqual(process_event(success, REPO, api), "no_incident")

    def test_stale_success_never_closes_newer_failure(self):
        api = FakeGitHub()
        failed = event(run_id=120)
        api.add_run(failed)
        self.assertEqual(process_event(failed, REPO, api), "opened")
        old = event(run_id=119, conclusion="success")
        api.add_run(old)
        self.assertEqual(process_event(old, REPO, api), "ignored_stale_event")
        self.assertEqual(api.issues[0]["state"], "open")

    def test_rerun_attempt_can_resolve_same_run_id(self):
        api = FakeGitHub()
        failed = event(run_id=120, attempt=1)
        api.add_run(failed)
        self.assertEqual(process_event(failed, REPO, api), "opened")
        succeeded = event(run_id=120, attempt=2, conclusion="success")
        api.runs["17"] = [succeeded["workflow_run"]]
        self.assertEqual(process_event(succeeded, REPO, api), "closed")
        self.assertIn("attempts/2", api.comments[-1])

    def test_api_index_lag_keeps_current_event_authoritative(self):
        api = FakeGitHub()
        api.runs["17"] = [event(run_id=99)["workflow_run"]]
        self.assertEqual(process_event(event(run_id=100), REPO, api), "opened")

    def test_skips_pull_request_fork_invalid_or_non_actionable_events(self):
        cases = (
            event(origin="pull_request"),
            event(branch="feature"),
            event(repository="other/fork"),
            event(conclusion="skipped"),
            event(name="artifact-attestation-probe"),
        )
        for data in cases:
            with self.subTest(data=data):
                api = FakeGitHub()
                self.assertTrue(process_event(data, REPO, api).startswith("ignored"))
                self.assertEqual(api.calls, [])

    def test_expected_ci_failure_does_not_make_second_project_health_issue(self):
        api = FakeGitHub()
        failed_ci = event()
        api.runs["ci.yml"] = [failed_ci["workflow_run"]]
        downstream = event(
            name="project-health", run_id=201, workflow_id=18,
            origin="workflow_run", conclusion="failure"
        )
        api.add_run(downstream)
        self.assertEqual(
            process_event(downstream, REPO, api),
            "ignored_expected_ci_degradation",
        )
        self.assertEqual(api.issues, [])

    def test_independent_project_health_error_does_open_incident(self):
        api = FakeGitHub()
        api.runs["ci.yml"] = [event(conclusion="success")["workflow_run"]]
        downstream = event(
            name="project-health", run_id=201, workflow_id=18,
            origin="workflow_run", conclusion="failure"
        )
        api.add_run(downstream)
        self.assertEqual(process_event(downstream, REPO, api), "opened")
        self.assertEqual(api.issues[0]["title"], "[workflow-failure] project-health")

    def test_workflow_wiring_and_failure_artifact_contract(self):
        root = Path(__file__).resolve().parents[1]
        monitor = (root / ".github/workflows/incident-monitor.yml").read_text()
        health = (root / ".github/workflows/project-health.yml").read_text()
        self.assertIn("head_branch == 'main'", monitor)
        self.assertIn("head_repository.full_name == github.repository", monitor)
        self.assertIn("ref: main", monitor)
        self.assertIn("persist-credentials: false", monitor)
        self.assertNotIn("github.event.workflow_run.head_sha", monitor)
        self.assertNotIn("actions: write", monitor)
        self.assertIn("id: build_health", health)
        self.assertIn("always() && steps.build_health.outcome != 'skipped'", health)


if __name__ == "__main__":
    unittest.main()
