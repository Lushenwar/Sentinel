"""Runs the frozen eval set through the real Sentinel ranking path.

python -m eval.run_eval --condition baseline --trials 3 --out eval/results/baseline_<date>.json
python -m eval.run_eval --condition baseline --dry-run --out <scratch>.json   # mocked chat(), no API cost
"""

import argparse
import json
import re
import subprocess
import tempfile
import time
from contextlib import nullcontext
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from core import orchestrator
from core.services import git_client, llm_analyzer, openrouter, vector_store
from eval import config, fixture

ROOT = Path(__file__).parent.parent


def run_trial(case: dict, condition: str) -> dict:
    with fixture.build(case) as (repo, alert, label):
        diffs = git_client.get_recent_diffs(repo, alert["timestamp"])
        rag = condition == "rag"
        runbooks = (
            vector_store.find_matching_runbooks(alert["error_signature"], include_content=True)
            if rag
            else vector_store.find_matching_runbooks(alert["error_signature"])
        )
        record = {
            "case_id": case["id"],
            "category": case["category"],
            "culprit_hash": label["culprit_hash"],
            "expected_runbook_id": label["expected_runbook_id"],
            "commits_in_window": len(diffs),
            "truncated_diffs": sum(len(d["diff"]) >= 3000 for d in diffs),
            "retrieved_runbooks": [
                {"id": r["id"], "similarity_score": r["similarity_score"]} for r in runbooks
            ],
            "ranking": [],
            "culprit_rank": None,
            "error": None,
        }
        t0 = time.monotonic()
        try:
            # the harness never builds a prompt itself; it calls the production function
            ranked = (
                llm_analyzer.rank_suspect_commits(diffs, alert, runbooks=runbooks)
                if rag
                else llm_analyzer.rank_suspect_commits(diffs, alert)
            )
            record["ranking"] = [
                {"commit_hash": r["commit_hash"][:7], "confidence_score": r["confidence_score"]}
                for r in ranked
            ]
            hashes = [r["commit_hash"] for r in record["ranking"]]
            if label["culprit_hash"] in hashes:
                record["culprit_rank"] = hashes.index(label["culprit_hash"]) + 1
        except llm_analyzer.LLMUnavailable as e:
            record["error"] = f"LLMUnavailable: {e}"  # counted as a miss by report.py, never dropped
        record["rank_latency_s"] = round(time.monotonic() - t0, 2)
        return record


def _fake_chat(messages, **_):
    """Dry-run stand-in for openrouter.chat: ranks commits in prompt order."""
    hashes = re.findall(r"^COMMIT (\w{7}) \|", messages[0]["content"], flags=re.M)
    ranked = [
        {
            "commit_hash": h,
            "author": "x",
            "timestamp": "x",
            "rationale": "dry run",
            "confidence_score": 0.9 - i / 10,
        }
        for i, h in enumerate(hashes)
    ]
    args = json.dumps({"ranked_commits": ranked})
    return {
        "choices": [{"message": {"tool_calls": [{"function": {"name": "rank_commits", "arguments": args}}]}}]
    }


def _git_sha() -> str:
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True
    ).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT, capture_output=True, text=True).stdout
    return sha + ("-dirty" if dirty.strip() else "")


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--condition", choices=["baseline", "rag"], required=True)
    p.add_argument("--trials", type=int, default=config.DEFAULT_TRIALS)
    p.add_argument("--cases", default="*.json", help="glob inside eval/cases")
    p.add_argument("--out", required=True)
    p.add_argument("--dry-run", action="store_true", help="mock chat(); no API calls")
    args = p.parse_args(argv)

    # isolated Chroma store holding exactly the frozen corpus, never the dev .chroma
    vector_store.CHROMA_PATH = tempfile.mkdtemp(prefix="sentinel_eval_chroma_")
    n_runbooks = vector_store.ingest_runbooks(orchestrator.RUNBOOKS_DIR)

    cases = [fixture.load_case(path) for path in fixture.all_case_paths(args.cases)]
    out = {
        "condition": args.condition,
        "dry_run": args.dry_run,
        "eval_set_version": config.EVAL_SET_VERSION,
        "runbook_corpus_version": config.RUNBOOK_CORPUS_VERSION,
        "runbooks_ingested": n_runbooks,
        "model": openrouter.MODEL,
        "sentinel_git_sha": _git_sha(),
        "started_at": datetime.now(timezone.utc).isoformat(),
        "trials": args.trials,
        "n_cases": len(cases),
        "records": [],
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with patch.object(llm_analyzer, "chat", _fake_chat) if args.dry_run else nullcontext():
        for trial in range(args.trials):
            for case in cases:
                rec = {"trial": trial, **run_trial(case, args.condition)}
                out["records"].append(rec)
                # rewrite after every trial so an interrupted run keeps what it measured
                out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
                status = rec["error"] or f"culprit rank {rec['culprit_rank']}"
                print(f"[eval] trial {trial} {case['id']}: {status} ({rec['rank_latency_s']}s)")

    out["finished_at"] = datetime.now(timezone.utc).isoformat()
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"[eval] wrote {len(out['records'])} records to {out_path}")


if __name__ == "__main__":
    main()
