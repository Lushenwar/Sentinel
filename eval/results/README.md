# Eval results

Raw, unedited outputs of `python -m eval.run_eval`; `python -m eval.report` reproduces the METRICS.md tables.

Each file records `sentinel_git_sha`, the commit the run used. Phase 9 was rebase-merged into `main`, so
those SHAs (`7b4dc90`, `2e1eb8d`, `530b73f`) live on the preserved branch `feat/phase9-rag-eval`, not on
`main`. Do not delete that branch.

Runs under `aborted/` are kept for the record and are never scored as measurements.
