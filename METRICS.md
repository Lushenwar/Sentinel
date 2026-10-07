# METRICS.md — Measured Sentinel Performance

All figures below were measured against real infrastructure. No mocked shortcuts
were in the executed path. Any externally cited number (resume, README,
interviews) must appear in this file first.

## Measurement Setup

- **Date:** 2026-07-08
- **Hardware:** Windows 11 laptop (local dev machine)
- **Database:** Neon-hosted PostgreSQL (us-east-1, pooled connection) — network
  round-trips to Neon are included in every timing
- **Vector store:** Chroma (local, persistent, cosine similarity)
- **LLM:** `anthropic/claude-sonnet-5` via OpenRouter (network latency included)
- **Slack:** live Incoming Webhook (card delivery confirmed per run)

## What Was Measured

Instrumented directly in `core/orchestrator.py` (`[metrics]` log lines):

1. **Alert → suspects surfaced:** wall time from the alert's own timestamp
   (set by `sandbox.chaos_cli` when the bug is injected) to the moment ranked
   suspect commits + matched runbooks are committed to Postgres. Covers: alert
   HTTP hop, git diff-window extraction, Claude commit ranking, Chroma runbook
   match, and the Postgres write.
2. **Resolve → postmortem complete:** wall time from the resolution request
   entering the orchestrator to the generated postmortem markdown being
   committed to Postgres. Covers: incident fetch, Claude postmortem generation,
   and the Postgres write.

## Runs (2026-07-08, three consecutive end-to-end loops)

| Run | Injected bug | Alert → suspects (s) | Resolve → postmortem (s) | Injected commit ranked #1? | Confidence | Correct runbook top match? |
|-----|--------------|----------------------|--------------------------|----------------------------|------------|----------------------------|
| 1   | db_failure   | 12.5                 | 12.0                     | Yes                        | 0.98       | Yes (`db_failures`, 0.359) |
| 2   | memory_leak  | 13.3                 | 13.5                     | Yes                        | 0.97       | Yes (`memory_leaks`, 0.499) |
| 3   | null_pointer | 13.4                 | 13.5                     | Yes                        | 0.95       | n/a — no null-pointer runbook exists; low scores returned honestly |

| Metric                | Min  | Median | Max  |
|-----------------------|------|--------|------|
| Alert → suspects (s)  | 12.5 | **13.3** | 13.4 |
| Resolve → postmortem (s) | 12.0 | **13.5** | 13.5 |

**Cite the medians: ~13s to surface the faulty commit, ~14s to a complete
postmortem draft.**

> **Caveat (added in Phase 9):** these runs used chaos-CLI commits whose
> messages named the injected bug, with typically one commit in the window;
> they verify the pipeline end-to-end but are not a measure of diagnostic
> accuracy. See [Phase 9](#phase-9--diagnostic-accuracy-and-runbook-context-in-ranking).

## Resume Reconciliation

- The prior `<10s` suspect-commit claim is **not supported** — measured median
  is 13.3s. The resume must say **"under 15 seconds"** (or "~13s"), not <10s.
- The prior `<30s` postmortem claim is supported (13.5s median) but should be
  tightened to **"under 15 seconds"** to match the measurement.
- **Manual baseline:** no timed manual-investigation run has been performed.
  Until someone actually times finding an injected bad commit by hand (git log
  → read diffs → correlate with the error), the "20+ min manual baseline"
  comparison must be **removed** from the resume, per the Resume Integrity
  Constraint.

## Verification Notes (Phase 5)

- Every run: injected commit ranked #1 by Claude, Slack card delivered
  (HTTP 200), postmortem markdown 1.9–2.6 KB generated on resolution.
- Real bug found and fixed during verification: `git_client` crashed on
  Windows when a diff contained non-ASCII bytes (`subprocess` defaulted to
  cp1252). Fixed with explicit UTF-8 decoding.

## Reproducing

```bash
# terminal 1 — core against real Postgres (DATABASE_URL in .env)
python -m uvicorn core.main:app --port 8000

# terminal 2 — one full loop
python -m sandbox.chaos_cli trigger-bug --type db_failure
# wait for "[metrics] ... alert_to_suspects_s=" in terminal 1
python -m sandbox.chaos_cli resolve-bug --incident <incident_id>
# wait for "[metrics] ... resolve_to_postmortem_s=" in terminal 1
```

## Phase 9 — Diagnostic accuracy and runbook context in ranking

**Question:** does giving Claude the matched runbooks improve its ability to
find the commit that caused an incident?

**Answer at this corpus size: no measurable benefit.** `SENTINEL_RAG_RANKING`
stays off by default. Raw results:
[`eval/results/`](eval/results/); every table below is reproduced by
`python -m eval.report eval/results/baseline_v2_2026-10-04.json eval/results/rag_v2_2026-10-04.json`.

### Methodology

- **Harness:** `eval/` builds each case as a throwaway git repo (never the
  Sentinel repo) and calls the production `get_recent_diffs`,
  `find_matching_runbooks` and `rank_suspect_commits`; it never rebuilds the
  prompt itself.
- **Model:** `claude-sonnet-5`, Anthropic API direct, provider-default
  sampling (non-deterministic), `max_tokens` 16000. **3 trials per case.**
- **Runbook corpus v1:** 10 generic runbooks in `sandbox/runbooks/`, written
  before any eval case and frozen at Phase 9B.
- **Eval set v2:** 24 cases, 17 fault categories, 5 commits per case (2 cases
  have 4). Culprit position from newest: 0→5 cases, 1→6, 2→6, 3→4, 4→3.
  7/24 cases (29%) deliberately have no matching runbook.
  - Every case carries a **decoy** that matches the alert as well as the
    culprit at first glance: same config key, same subsystem, or the very
    line that raises.
  - Commit messages are neutral; a lint test bans words that announce the
    answer. A leakage test asserts that no case id, category or label value
    reaches the prompt in either condition.
- **Eval set v1 (superseded):** the first 29-case set scored **87/87 top-1**
  at baseline (`eval/results/baseline_2026-10-04.json`). It was too easy to
  show any difference, so it was replaced by v2 before any RAG run (the one
  revision the protocol allows).
- **Similarity floor 0.35:** chosen from the v2 baseline retrieval table alone,
  before the RAG run, as the candidate maximising (correct runbooks kept −
  null cases given a runbook): 0.15→5, 0.25→3, 0.30→6, **0.35→7**, 0.40→5.

### Results (eval set v2, n = 24 cases × 3 trials = 72 per condition)

| Metric | Baseline | RAG (floor 0.35) |
|---|---|---|
| Top-1 (culprit ranked #1) | 90.3% (65/72) | 91.7% (66/72) |
| Top-3 | 100% (72/72) | 100% (72/72) |
| MRR | 0.947 | 0.958 |
| LLM failures (counted as misses) | 0/72 | 0/72 |
| Mean #1 confidence, right / wrong | 0.90 (n=65) / 0.89 (n=7) | 0.89 (n=66) / 0.83 (n=6) |
| Ranking latency, median | 5.8s | 6.0s |

**Paired per case (top-1 hits out of 3):** RAG wins 2, loses 1, ties 21.

| Case | Baseline | RAG | Runbook text in RAG prompt? |
|---|---|---|---|
| `export_tempfile_never_closed` | 0/3 | 1/3 | yes (`file_handle_exhaustion`) |
| `page_size_zero_division` | 2/3 | 3/3 | **no** — prompt byte-identical to baseline |
| `payments_retry_loop` | 3/3 | 2/3 | yes (`rate_limiting`) |
| `httpx_028_drops_proxies` | 0/3 | 0/3 | no (best match 0.29) |

**Where runbooks actually reached the prompt** (10 of 24 cases had a runbook
above the floor): baseline 27/30, RAG 27/30 — identical. The one extra RAG hit
overall came from a case whose prompt was unchanged, i.e. run-to-run noise.

**Null-runbook cases** (7 cases, 21 trials): 21/21 in both conditions. One of
them (`worker_queue_renamed`) received three irrelevant runbooks above the
floor and was still ranked correctly 3/3, so wrong context did not visibly
hurt either.

**How large a difference would matter:** a 1/3 swing on a single case occurred
with a byte-identical prompt, so per-case noise is at least that large. With
only 10 cases where the prompt differs, a real effect would need to show up as
several (roughly 3+) net case wins concentrated in those cases. This is a
judgement from the observed noise, not a significance test; none was computed.

### Confidence signal

Pooling both v2 conditions (144 trials: 131 right #1 picks, 13 wrong):

| Signal | AUC right-vs-wrong (0.5 = coin flip) |
|---|---|
| Top-1 `confidence_score` | 0.60 |
| Gap between #1 and #2 confidence | **0.86** |

Raw confidence is near-useless: wrong picks averaged 0.83–0.89. The Slack card
and dashboard therefore flag a **close call** when the top two suspects are
within 0.1, and show both. On these trials that rule flags 9/13 wrong picks
and 9/131 right ones. The 0.1 cut was chosen on the same 144 trials (in-sample,
13 wrong picks), so treat it as a working rule. Two wrong picks had a 0.7 gap:
the signal does not catch confidently wrong rankings.

### Retrieval

- Runbook top-1 on cases with an expected runbook: **10/17**; correct runbook
  anywhere in top-3: 13/17.
- At floor 0.35: 1 of 7 null cases still receives a runbook, and only 8 of 17
  expected cases receive the correct one.
- Indexing only title + Symptoms (11/17) or title + Symptoms + Root Causes
  (12/17) was measured offline and did not separate correct matches from null
  cases either; retrieval was left unchanged. The limiting factor is short
  error strings against the default embedding model.

### Limitations

- Synthetic cases written by the same author as the system and the runbooks.
- Small n: 24 cases × 3 trials; single model (`claude-sonnet-5`).
- Sandbox repo; each case's diffs are small and fit the 3000-char truncation.
- The baseline is already 90% top-1, leaving little room for runbook context to
  help; retrieval only delivers the right runbook in about half the cases.
