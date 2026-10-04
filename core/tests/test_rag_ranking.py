# ponytail: Phase 9E guards: the RAG flag must not move the A/B control; retrieval must never abort triage
import json
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch

import jsonschema

from core import orchestrator
from core.services import llm_analyzer, vector_store

SCHEMA = json.loads((Path(__file__).parent.parent.parent / "contract" / "pipeline_schema.json").read_text())

_DIFFS = [
    {
        "commit_hash": "a1b2c3d",
        "author": "dev@example.com",
        "timestamp": "2026-09-01T11:30:00+00:00",
        "subject": "config: raise pool size",
        "diff": '-  "pool_size": 10\n+  "pool_size": 12',
    },
    {
        "commit_hash": "e4f5a6b",
        "author": "ops@example.com",
        "timestamp": "2026-09-01T11:45:00+00:00",
        "subject": "docs: readme",
        "diff": "+ more docs",
    },
]
_ALERT = {
    "source": "mock_sentry",
    "alert_name": "HTTP_500_Internal_Server_Error",
    "error_signature": "PoolError: connection pool exhausted",
    "timestamp": "2026-09-01T12:00:00+00:00",
}
# Captured from rank_suspect_commits before the runbooks parameter existed (Phase 9E). Never edit:
# the baseline/RAG comparison is only valid while the no-runbook prompt is byte-identical to this.
_GOLDEN_BASELINE_PROMPT = (
    "You are an incident triage engine.\n\nALERT:\n  name: HTTP_500_Internal_Server_Error\n"
    "  error: PoolError: connection pool exhausted\n  time: 2026-09-01T12:00:00+00:00\n\n"
    "RECENT COMMITS:\nCOMMIT a1b2c3d | dev@example.com | 2026-09-01T11:30:00+00:00\n"
    'Subject: config: raise pool size\nDiff:\n-  "pool_size": 10\n+  "pool_size": 12\n\n'
    "COMMIT e4f5a6b | ops@example.com | 2026-09-01T11:45:00+00:00\nSubject: docs: readme\nDiff:\n"
    "+ more docs\n\nUse rank_commits to return every commit with a confidence_score "
    "(0=unrelated, 1=certain cause) and a one-sentence rationale."
)
_RUNBOOK = {
    "id": "db_failures",
    "title": "Db Failures",
    "similarity_score": 0.5,
    "primary_action": "Check pool.",
    "content": "Symptoms:\n- pool exhausted\n\nRoot causes:\n1. Connection leak",
}


def _prompt(runbooks):
    captured = []

    def fake_chat(messages, **_):
        captured.append(messages[0]["content"])
        return NS(
            stop_reason="tool_use",
            content=[NS(type="tool_use", name="rank_commits", input={"ranked_commits": []})],
        )

    with patch.object(llm_analyzer, "chat", fake_chat):
        llm_analyzer.rank_suspect_commits(_DIFFS, _ALERT, runbooks=runbooks)
    return captured[0]


def test_no_runbooks_prompt_is_byte_identical_to_baseline():
    assert _prompt(None) == _GOLDEN_BASELINE_PROMPT
    assert _prompt([]) == _GOLDEN_BASELINE_PROMPT


def test_runbooks_below_floor_are_omitted_entirely():
    low = {**_RUNBOOK, "similarity_score": llm_analyzer.RUNBOOK_FLOOR - 0.01}
    assert _prompt([low]) == _GOLDEN_BASELINE_PROMPT  # no empty <runbooks> block


def test_runbooks_above_floor_sit_between_alert_and_commits():
    prompt = _prompt([_RUNBOOK])
    assert '<runbook id="db_failures" similarity="0.5">' in prompt and "Connection leak" in prompt
    assert prompt.index("ALERT:") < prompt.index("<runbooks>") < prompt.index("RECENT COMMITS:")
    assert prompt.replace(llm_analyzer._runbooks_block([_RUNBOOK]), "") == _GOLDEN_BASELINE_PROMPT


def _run_diagnostics(rag: bool, retrieval: dict):
    with (
        patch.object(orchestrator, "_RAG_RANKING", rag),
        patch.object(orchestrator, "db") as mock_db,
        patch.object(orchestrator.git_client, "get_recent_diffs", return_value=_DIFFS),
        patch.object(orchestrator.vector_store, "find_matching_runbooks", **retrieval),
        patch.object(orchestrator.llm_analyzer, "rank_suspect_commits", return_value=[]) as rank,
        patch.object(orchestrator.notifier, "post_incident_to_slack"),
    ):
        mock_db.get_incident.return_value = {"id": "inc_t", "status": "triaging"}
        orchestrator.run_diagnostics("inc_t", _ALERT)
        statuses = [c.args for c in mock_db.update_status.call_args_list]
        diagnostics = mock_db.update_diagnostics.call_args.args[1]
    return rank, statuses, diagnostics


def test_retrieval_failure_still_ranks_and_does_not_revert():
    rank, statuses, diagnostics = _run_diagnostics(True, {"side_effect": RuntimeError("chroma down")})
    rank.assert_called_once()
    assert rank.call_args.kwargs["runbooks"] == []
    assert ("inc_t", "triggered") not in statuses
    assert diagnostics["matched_runbooks"] == []


def test_flag_off_ranks_without_runbooks():
    rank, _, _ = _run_diagnostics(False, {"return_value": [_RUNBOOK]})
    assert rank.call_args.kwargs["runbooks"] is None


def test_persisted_runbooks_carry_no_content_and_match_contract():
    rank, _, diagnostics = _run_diagnostics(True, {"return_value": [_RUNBOOK]})
    assert rank.call_args.kwargs["runbooks"] == [_RUNBOOK]  # content reaches the prompt...
    assert all("content" not in r for r in diagnostics["matched_runbooks"])  # ...but is never stored
    payload = {
        "incident_id": "inc_t",
        "status": "triaging",
        "trigger": _ALERT,
        "diagnostics": diagnostics,
        "postmortem_draft_url": None,
    }
    jsonschema.validate(payload, SCHEMA)


def test_include_content_returns_symptoms_and_root_causes_capped():
    doc = (
        "# T\n\n## Symptoms\n\n- s1\n\n## Root Causes\n\n1. r1 "
        + "x" * 3000
        + "\n\n## Immediate Actions\n\n1. act\n"
    )

    class FakeCol:
        def count(self):
            return 1

        def query(self, **_):
            return {
                "ids": [["rb"]],
                "metadatas": [[{"title": "Rb"}]],
                "documents": [[doc]],
                "distances": [[0.5]],
            }

    with patch.object(vector_store, "_col", return_value=FakeCol()):
        plain = vector_store.find_matching_runbooks("x")[0]
        rich = vector_store.find_matching_runbooks("x", include_content=True)[0]
    assert "content" not in plain
    assert rich["content"].startswith("Symptoms:\n- s1\n\nRoot causes:\n1. r1")
    assert len(rich["content"]) == vector_store.CONTENT_CAP and "Immediate" not in rich["content"]
