# Aborted runs

Kept unedited for the record; never scored as measurements.

- `baseline_2026-10-04_402.json`: OpenRouter returned `402 Payment Required` on 82/87 calls (account credit exhausted).
  The 5 calls that succeeded all ranked the culprit #1. Predates the harness abort-on-consecutive-errors guard.
