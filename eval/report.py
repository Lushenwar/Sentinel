"""Scores eval results files. One file: summary. Two files (baseline, rag): side by side + paired.

python -m eval.report eval/results/baseline_<date>.json [eval/results/rag_<date>.json]
"""

import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

from eval.config import FLOOR_CANDIDATES


def load(path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _pct(k, n) -> str:
    return f"{100 * k / n:.1f}% ({k}/{n})" if n else "n/a (0/0)"


def summarize(records: list[dict]) -> dict:
    """LLM errors have culprit_rank None, so they count as misses in every ranking metric."""
    n = len(records)
    ranks = [r["culprit_rank"] for r in records]
    right, wrong = [], []
    for r in records:
        if r["error"] or not r["ranking"]:
            continue
        (right if r["culprit_rank"] == 1 else wrong).append(r["ranking"][0]["confidence_score"])
    return {
        "n": n,
        "top1": sum(k == 1 for k in ranks),
        "top3": sum(k is not None and k <= 3 for k in ranks),
        "mrr": sum(1 / k for k in ranks if k) / n if n else 0.0,
        "errors": sum(bool(r["error"]) for r in records),
        "conf_right": statistics.mean(right) if right else None,
        "conf_wrong": statistics.mean(wrong) if wrong else None,
        "n_right": len(right),
        "n_wrong": len(wrong),
        "latency_median_s": statistics.median(r["rank_latency_s"] for r in records) if records else None,
        # runs before token metering have no usage; report None rather than a fake zero
        "tokens_in_mean": _mean_usage(records, "input_tokens"),
        "tokens_out_mean": _mean_usage(records, "output_tokens"),
    }


def _mean_usage(records: list[dict], key: str):
    vals = [r["usage"][key] for r in records if r.get("usage")]
    return round(statistics.mean(vals)) if vals else None


def _label(a: dict, b: dict) -> tuple[str, str]:
    """Name the two runs by whatever differs: condition for an A/B, model for a model comparison."""
    if a["condition"] != b["condition"]:
        return a["condition"], b["condition"]
    return a["model"], b["model"]


def retrieval(records: list[dict]) -> dict:
    """Retrieval is deterministic per case, so score one record per case."""
    per_case = {}
    for r in records:
        per_case.setdefault(r["case_id"], r)
    expected = [r for r in per_case.values() if r["expected_runbook_id"]]
    nulls = [r for r in per_case.values() if not r["expected_runbook_id"]]

    def top(r):
        return (
            r["retrieved_runbooks"][0] if r["retrieved_runbooks"] else {"id": None, "similarity_score": 0.0}
        )

    def expected_score(r):
        return next(
            (
                rb["similarity_score"]
                for rb in r["retrieved_runbooks"]
                if rb["id"] == r["expected_runbook_id"]
            ),
            None,
        )

    return {
        "n_expected": len(expected),
        "top1_hits": sum(top(r)["id"] == r["expected_runbook_id"] for r in expected),
        "n_null": len(nulls),
        "correct_scores": sorted(s for s in map(expected_score, expected) if s is not None),
        "null_top_scores": sorted(top(r)["similarity_score"] for r in nulls),
        "floors": {
            f: {
                # null case with anything above floor = wrong context would be sent
                "false_match": sum(top(r)["similarity_score"] >= f for r in nulls),
                # expected case whose correct runbook sits below floor = right context withheld
                "correct_dropped": sum((expected_score(r) or 0.0) < f for r in expected),
            }
            for f in FLOOR_CANDIDATES
        },
    }


def paired(a: list[dict], b: list[dict]) -> list[tuple]:
    """(case_id, hits_a, trials_a, hits_b, trials_b) per case."""
    hits = defaultdict(lambda: [0, 0, 0, 0])
    for i, recs in enumerate((a, b)):
        for r in recs:
            h = hits[r["case_id"]]
            h[2 * i] += r["culprit_rank"] == 1
            h[2 * i + 1] += 1
    return [(cid, *h) for cid, h in sorted(hits.items())]


def _fmt_conf(x):
    return f"{x:.2f}" if x is not None else "n/a"


def print_summary(name: str, res: dict):
    s = summarize(res["records"])
    print(
        f"\n== {name}: condition={res['condition']} eval_set={res['eval_set_version']} "
        f"corpus={res['runbook_corpus_version']} model={res['model']} dry_run={res['dry_run']}"
    )
    print(f"  top-1        {_pct(s['top1'], s['n'])}")
    print(f"  top-3        {_pct(s['top3'], s['n'])}")
    print(f"  MRR          {s['mrr']:.3f} (n={s['n']})")
    print(f"  LLM errors   {s['errors']}/{s['n']} (counted as misses)")
    print(
        f"  conf of #1   right {_fmt_conf(s['conf_right'])} (n={s['n_right']}), "
        f"wrong {_fmt_conf(s['conf_wrong'])} (n={s['n_wrong']})"
    )
    print(f"  rank latency median {s['latency_median_s']}s (n={s['n']})")
    if s["tokens_in_mean"] is not None:
        print(f"  tokens/call  in {s['tokens_in_mean']}, out {s['tokens_out_mean']} (mean)")
    if res.get("aborted"):
        print(f"  WARNING run ABORTED, not a valid measurement: {res['aborted']}")
    truncated = sorted({r["case_id"] for r in res["records"] if r["truncated_diffs"]})
    if truncated:
        print(f"  WARNING diffs hit the 3000-char truncation in: {', '.join(truncated)}")


def print_retrieval(res: dict):
    rt = retrieval(res["records"])
    print("\n== Retrieval (one record per case)")
    print(f"  runbook top-1 on expected cases  {_pct(rt['top1_hits'], rt['n_expected'])}")
    print(f"  correct-runbook scores   {rt['correct_scores']}")
    print(f"  null-case top-1 scores   {rt['null_top_scores']}")
    print(f"  {'floor':>6}  {'null false-match':>18}  {'correct dropped':>17}")
    for f, v in rt["floors"].items():
        print(
            f"  {f:>6}  {_pct(v['false_match'], rt['n_null']):>18}  "
            f"{_pct(v['correct_dropped'], rt['n_expected']):>17}"
        )


def print_comparison(a: dict, b: dict):
    rows = paired(a["records"], b["records"])
    la, lb = _label(a, b)
    wins = sum(hb / tb > ha / ta for _, ha, ta, hb, tb in rows)
    losses = sum(hb / tb < ha / ta for _, ha, ta, hb, tb in rows)
    print(f"\n== Paired per-case top-1 hits ({la} vs {lb})")
    print(f"  {'case':<34} {la:>15} {lb:>15}")
    for cid, ha, ta, hb, tb in rows:
        mark = "+" if hb / tb > ha / ta else "-" if hb / tb < ha / ta else " "
        print(f"  {cid:<34} {ha:>11}/{ta:<3} {hb:>11}/{tb:<3} {mark}")
    ties = len(rows) - wins - losses
    print(f"  {lb} wins {wins}, losses {losses}, ties {ties} (n={len(rows)} cases)")

    print("\n== Null-runbook cases only (does irrelevant context hurt?)")
    for label, res in ((la, a), (lb, b)):
        s = summarize([r for r in res["records"] if not r["expected_runbook_id"]])
        print(f"  {label:<15} top-1 {_pct(s['top1'], s['n'])}, MRR {s['mrr']:.3f}")


def main(argv=None):
    paths = argv if argv is not None else sys.argv[1:]
    if not 1 <= len(paths) <= 2:
        sys.exit("usage: python -m eval.report RESULTS.json [RESULTS_B.json]")
    results = [load(p) for p in paths]
    for p, res in zip(paths, results):
        print_summary(Path(p).name, res)
    print_retrieval(results[0])
    if len(results) == 2:
        print_comparison(*results)


if __name__ == "__main__":
    main()
