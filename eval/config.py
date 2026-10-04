# Frozen eval inputs. Bump a version whenever its inputs change; never edit after a compared run.
RUNBOOK_CORPUS_VERSION = "v1"  # sandbox/runbooks/*.md, 10 docs, frozen at Phase 9B
# v2 replaced v1 after the v1 baseline hit 100% top-1 (ceiling); v1 lives in git history at d6f6bd1.
EVAL_SET_VERSION = "v2"  # eval/cases/*.json + eval/bases/, 24 cases, frozen at Phase 9C (rev)

ALERT_TS = "2026-09-01T12:00:00+00:00"  # fixed so fixture commit dates are reproducible
DEFAULT_TRIALS = 3

# Candidate runbook similarity floors; report.py prints the false-match rate at each.
# The chosen floor is frozen in 9E from 9D's retrieval scores, before any RAG run.
FLOOR_CANDIDATES = [0.15, 0.2, 0.25, 0.3, 0.35, 0.4]

# Words that would announce the culprit. Checked (word-prefix, case-insensitive) in commit
# messages and in every file the case writes, including the shared base.
BANNED_WORDS = ["bug", "inject", "break", "fault", "fail", "chaos", "oops", "fix", "hotfix", "revert"]

# Runbook similarity floor for the RAG condition, frozen at 9E before any RAG run. Chosen from the v2 baseline
# retrieval table alone: the candidate maximising (correct runbooks kept - null cases given a runbook):
# 0.15->5, 0.25->3, 0.30->6, 0.35->7, 0.40->5. Must equal core.services.llm_analyzer.RUNBOOK_FLOOR.
RUNBOOK_FLOOR = 0.35
