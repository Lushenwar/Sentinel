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
