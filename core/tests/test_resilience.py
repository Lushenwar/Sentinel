# ponytail: all external boundaries (db, git, chroma, openrouter, slack) mocked — offline + deterministic
import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import httpx
import jsonschema
import pytest

from core import orchestrator
from core.services import vector_store
from core.services.llm_analyzer import LLMUnavailable, rank_suspect_commits
from core.services.postmortem import generate_postmortem

SCHEMA = json.loads((Path(__file__).parent.parent.parent / "contract" / "pipeline_schema.json").read_text())

_ALERT = {
    "source": "mock_sentry",
    "alert_name": "HTTP_500_Internal_Server_Error",
    "timestamp": "2026-07-08T00:00:00Z",
    "error_signature": "OperationalError: connection refused",
}

_DIFFS = [
    {
        "commit_hash": "a1b2c3d",
        "full_hash": "a1b2c3d0000000000000000000000000000000000",
        "author": "dev@co.com",
        "timestamp": "2026-07-07T23:55:00Z",
        "subject": "chore: inject bug=db_failure",
        "diff": '-{"bug": null}\n+{"bug": "db_failure"}',
    }
]

_RANKED = [
    {
        "commit_hash": "a1b2c3d",
        "author": "dev@co.com",
        "timestamp": "2026-07-07T23:55:00Z",
        "rationale": "Set db_failure bug.",
        "confidence_score": 0.95,
    }
]

_RUNBOOKS = [
    {"id": "db_failures", "title": "Db Failures", "similarity_score": 0.5, "primary_action": "Check pool."}
]


def _tool_response(arguments: str):
    return {
        "choices": [
            {"message": {"tool_calls": [{"function": {"name": "rank_commits", "arguments": arguments}}]}}
        ]
    }


# ---------- LLM failure modes (7A) ----------


def test_llm_timeout_raises_llm_unavailable():
    with patch("core.services.llm_analyzer.chat", side_effect=httpx.TimeoutException("timed out")):
        with pytest.raises(LLMUnavailable, match="request failed"):
            rank_suspect_commits(_DIFFS, _ALERT)


def test_llm_malformed_json_raises_llm_unavailable():
    with patch("core.services.llm_analyzer.chat", return_value=_tool_response("{not json")):
        with pytest.raises(LLMUnavailable, match="malformed"):
            rank_suspect_commits(_DIFFS, _ALERT)


def test_llm_non_schema_output_raises_llm_unavailable():
    bad = json.dumps({"ranked_commits": [{"commit_hash": "abc", "confidence_score": 7}]})
    with patch("core.services.llm_analyzer.chat", return_value=_tool_response(bad)):
        with pytest.raises(LLMUnavailable, match="malformed"):
            rank_suspect_commits(_DIFFS, _ALERT)


def test_llm_empty_response_raises_llm_unavailable():
    with patch("core.services.llm_analyzer.chat", return_value={"choices": [{"message": {}}]}):
        with pytest.raises(LLMUnavailable, match="empty or refused"):
            rank_suspect_commits(_DIFFS, _ALERT)


def test_postmortem_empty_content_raises_llm_unavailable():
    incident = {"id": "inc_x", "trigger_data": _ALERT, "diagnostics": {}}
    with patch("core.services.postmortem.chat", return_value={"choices": [{"message": {"content": ""}}]}):
        with pytest.raises(LLMUnavailable):
            generate_postmortem(incident)


# ---------- State machine transitions (7B) ----------


def _run_diagnostics(llm_effect):
    """Run orchestrator.run_diagnostics with all boundaries mocked; return db call captures."""
    calls = {}
    with patch.object(orchestrator, "db") as mock_db, patch.object(
        orchestrator.git_client, "get_recent_diffs", return_value=_DIFFS
    ), patch.object(
        orchestrator.vector_store, "find_matching_runbooks", return_value=_RUNBOOKS
    ), patch.object(
        orchestrator.llm_analyzer, "rank_suspect_commits", **llm_effect
    ), patch.object(
        orchestrator.notifier, "post_incident_to_slack"
    ):
        mock_db.get_incident.return_value = {"id": "inc_t", "status": "triaging"}
        orchestrator.run_diagnostics("inc_t", _ALERT)
        calls["update_status"] = [c.args for c in mock_db.update_status.call_args_list]
        calls["diagnostics"] = mock_db.update_diagnostics.call_args.args[1]
    return calls


def test_diagnose_hop_success_saves_ranked_suspects():
    calls = _run_diagnostics({"return_value": _RANKED})
    assert calls["update_status"][0] == ("inc_t", "triaging")
    assert calls["diagnostics"]["suspect_commits"] == _RANKED
    assert calls["diagnostics"]["matched_runbooks"] == _RUNBOOKS
    assert "degraded" not in calls["diagnostics"]
    # never entered the degraded terminal state
    assert ("inc_t", "degraded") not in calls["update_status"]


def test_diagnose_hop_llm_failure_degrades_honestly():
    calls = _run_diagnostics({"side_effect": LLMUnavailable("forced timeout")})
    d = calls["diagnostics"]
    assert d["suspect_commits"] == []  # no fabricated diagnosis
    assert d["degraded"] is True
    assert "manual investigation required" in d["degraded_reason"]
    assert d["raw_commits"] == _DIFFS  # raw material still surfaced
    assert d["matched_runbooks"] == _RUNBOOKS  # non-LLM diagnostics still delivered
    assert ("inc_t", "degraded") in calls["update_status"]


def test_degraded_payload_conforms_to_contract():
    calls = _run_diagnostics({"side_effect": LLMUnavailable("forced timeout")})
    payload = {
        "incident_id": "inc_t",
        "status": "degraded",
        "trigger": _ALERT,
        "diagnostics": calls["diagnostics"],
        "postmortem_draft_url": None,
    }
    jsonschema.validate(payload, SCHEMA)  # raises on violation


def test_resolve_hop_llm_failure_writes_honest_placeholder():
    with patch.object(orchestrator, "db") as mock_db, patch.object(
        orchestrator.postmortem, "generate_postmortem", side_effect=LLMUnavailable("bad api key")
    ):
        mock_db.get_incident.return_value = {"id": "inc_t", "trigger_data": _ALERT, "diagnostics": {}}
        orchestrator.resolve_incident("inc_t")
        draft = mock_db.update_postmortem.call_args.args[1]
    assert "Postmortem unavailable" in draft
    assert "bad api key" in draft


# ---------- Diff-window extraction (7B) ----------


def _git(repo, *args, env_date=None):
    env = None
    if env_date:
        import os

        env = {**os.environ, "GIT_AUTHOR_DATE": env_date, "GIT_COMMITTER_DATE": env_date}
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, env=env)


def test_diff_window_includes_only_commits_in_window(tmp_path):
    from core.services.git_client import get_recent_diffs

    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "t@t.t")
    _git(repo, "config", "user.name", "t")

    (repo / "old.txt").write_text("old")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "old commit", env_date="2026-07-08T00:00:00Z")
    (repo / "new.txt").write_text("new")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "inside window", env_date="2026-07-08T11:30:00Z")

    commits = get_recent_diffs(str(repo), "2026-07-08T12:00:00Z", window_minutes=60)
    assert [c["subject"] for c in commits] == ["inside window"]
    assert "new.txt" in commits[0]["diff"]


# ---------- Runbook match ranking (7B) ----------


def test_runbook_matches_ranked_by_similarity():
    fake_results = {
        "ids": [["db_failures", "memory_leaks"]],
        "metadatas": [[{"title": "Db Failures"}, {"title": "Memory Leaks"}]],
        "documents": [["## Immediate Actions\n1. Check pool limits.", "no actions section"]],
        "distances": [[0.4, 0.9]],
    }

    class FakeCol:
        def count(self):
            return 2

        def query(self, **kwargs):
            return fake_results

    with patch.object(vector_store, "_col", return_value=FakeCol()):
        out = vector_store.find_matching_runbooks("connection refused")

    assert [r["id"] for r in out] == ["db_failures", "memory_leaks"]
    assert out[0]["similarity_score"] == pytest.approx(0.6)
    assert out[0]["primary_action"] == "Check pool limits."
    assert out[1]["primary_action"] == "See runbook for details."
