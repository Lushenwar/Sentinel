# Frozen eval inputs. Bump a version whenever its inputs change; never edit after a compared run.
RUNBOOK_CORPUS_VERSION = "v1"  # sandbox/runbooks/*.md, 10 docs, frozen at Phase 9B
EVAL_SET_VERSION = "v1"  # eval/cases/*.json + eval/bases/, 29 cases, frozen at Phase 9C

ALERT_TS = "2026-09-01T12:00:00+00:00"  # fixed so fixture commit dates are reproducible
DEFAULT_TRIALS = 3

# Candidate runbook similarity floors; report.py prints the false-match rate at each.
# The chosen floor is frozen in 9E from 9D's retrieval scores, before any RAG run.
FLOOR_CANDIDATES = [0.15, 0.2, 0.25, 0.3, 0.35, 0.4]

# Words that would announce the culprit. Checked (word-prefix, case-insensitive) in commit
# messages and in every file the case writes, including the shared base.
BANNED_WORDS = ["bug", "inject", "break", "fault", "fail", "chaos", "oops", "fix", "hotfix", "revert"]
