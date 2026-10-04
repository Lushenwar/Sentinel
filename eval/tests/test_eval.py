"""Offline eval-harness tests: no API calls, no embedding model, vector store mocked."""

import inspect
import re
from unittest.mock import patch

import anthropic
import httpx
import pytest

from core.services import git_client, llm_analyzer
from eval import config, fixture, report, run_eval

CASES = [fixture.load_case(p) for p in fixture.all_case_paths()]
_BANNED = re.compile(r"\b(" + "|".join(config.BANNED_WORDS) + r")", re.IGNORECASE)
# label-independent stand-in, so a label value can only reach the prompt by leaking
_DUMMY_RUNBOOKS = [
    {
        "id": "rb_dummy",
        "title": "Dummy",
        "similarity_score": 0.5,
        "primary_action": "n/a",
        "content": "## Symptoms\n- something\n",
    }
]


def _commit_texts(case):
    for commit in case["commits"]:
        yield commit["message"]
        for change in commit["files"].values():
            if isinstance(change, str):
                yield change
            else:
                for _old, new in change:
                    yield new


# ---------- case lint ----------


def test_case_set_shape():
    assert 24 <= len(CASES) <= 30
    assert len({c["category"] for c in CASES}) >= 6
    nulls = sum(c["label"]["expected_runbook_id"] is None for c in CASES)
    assert 0.2 <= nulls / len(CASES) <= 0.3


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_case_lint(case):
    assert set(case) >= {"id", "category", "base", "alert", "commits", "label"}
    assert 3 <= len(case["commits"]) <= 6
    assert 0 <= case["label"]["culprit_index"] < len(case["commits"])
    minutes = [c["minutes_before_alert"] for c in case["commits"]]
    assert minutes == sorted(minutes, reverse=True), "commits must be listed oldest first"
    assert all(0 < m < 60 for m in minutes), "every commit must fall inside the 60-min window"
    for text in _commit_texts(case):
        assert not _BANNED.search(text), f"banned word in: {text[:80]!r}"


def test_base_has_no_banned_words():
    for path in (fixture.BASES_DIR).rglob("*"):
        if path.is_file():
            assert not _BANNED.search(path.read_text(encoding="utf-8")), path


# ---------- fixture ----------


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_fixture_commits_land_in_window_in_order(case):
    with fixture.build(case) as (repo, alert, label):
        diffs = git_client.get_recent_diffs(repo, alert["timestamp"])
    assert [d["subject"] for d in diffs] == [c["message"] for c in reversed(case["commits"])]
    assert label["culprit_hash"] in {d["commit_hash"] for d in diffs}
    assert all(len(d["diff"]) < 3000 for d in diffs), "diff hit the truncation limit"


# ---------- scorer ----------


def _rec(case_id, rank, conf=0.9, error=None, expected="rb_a"):
    ranking = [] if error else [{"commit_hash": "x", "confidence_score": conf}]
    return {
        "case_id": case_id,
        "culprit_rank": rank,
        "ranking": ranking,
        "error": error,
        "rank_latency_s": 1.0,
        "expected_runbook_id": expected,
        "retrieved_runbooks": [{"id": "rb_a", "similarity_score": 0.4}],
        "truncated_diffs": 0,
    }


def test_summarize_counts_errors_as_misses():
    s = report.summarize([_rec("a", 1), _rec("b", 2, conf=0.6), _rec("c", 4), _rec("d", None, error="x")])
    assert (s["n"], s["top1"], s["top3"], s["errors"]) == (4, 1, 2, 1)
    assert s["mrr"] == pytest.approx((1 + 1 / 2 + 1 / 4 + 0) / 4)
    assert s["conf_right"] == 0.9 and s["conf_wrong"] == pytest.approx(0.75)


def test_retrieval_and_floors():
    recs = [_rec("a", 1), _rec("b", 1, expected=None), _rec("b", 1, expected=None)]
    rt = report.retrieval(recs)
    assert (rt["n_expected"], rt["top1_hits"], rt["n_null"]) == (1, 1, 1)  # one record per case
    assert rt["floors"][0.35] == {"false_match": 1, "correct_dropped": 0}
    assert rt["floors"][0.4] == {"false_match": 1, "correct_dropped": 0}


def test_paired():
    a = [_rec("a", 1), _rec("a", 2), _rec("b", 1)]
    b = [_rec("a", 1), _rec("a", 1), _rec("b", 3)]
    assert report.paired(a, b) == [("a", 1, 2, 2, 2), ("b", 1, 1, 0, 1)]


# ---------- leakage + dry run through the real ranking path ----------

_RAG_READY = "runbooks" in inspect.signature(llm_analyzer.rank_suspect_commits).parameters


@pytest.mark.parametrize(
    "condition",
    [
        "baseline",
        pytest.param("rag", marks=pytest.mark.skipif(not _RAG_READY, reason="runbooks param lands in 9E")),
    ],
)
def test_no_label_leaks_into_prompt(condition):
    prompts = []

    def capture(messages, **kw):
        prompts.append(messages[0]["content"])
        return run_eval._fake_chat(messages, **kw)

    with (
        patch.object(llm_analyzer, "chat", capture),
        patch.object(run_eval.vector_store, "find_matching_runbooks", return_value=_DUMMY_RUNBOOKS),
    ):
        for case in CASES:
            rec = run_eval.run_trial(case, condition)
            assert rec["error"] is None and rec["culprit_rank"] is not None, case["id"]
            prompt = prompts[-1]
            leaks = [case["id"], case["category"], case["label"]["expected_runbook_id"]]
            for value in filter(None, leaks):
                assert value not in prompt, f"{case['id']}: {value!r} leaked into prompt"
            assert "culprit" not in prompt.lower()
    assert len(prompts) == len(CASES)


def test_run_aborts_after_consecutive_llm_errors(tmp_path):
    out = tmp_path / "r.json"

    def dead_key(*_a, **_kw):
        raise anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com"))

    with (
        patch.object(llm_analyzer, "chat", dead_key),
        patch.object(run_eval.vector_store, "ingest_runbooks", return_value=0),
        patch.object(run_eval.vector_store, "find_matching_runbooks", return_value=[]),
        pytest.raises(SystemExit),
    ):
        run_eval.main(["--condition", "baseline", "--trials", "3", "--out", str(out)])
    res = report.load(out)
    assert len(res["records"]) == run_eval.MAX_CONSECUTIVE_ERRORS and "aborted" in res
