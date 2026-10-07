# CLAUDE.md — Sentinel, Phase 9: Retrieval-Augmented Ranking + Eval

## CURRENT STATUS

```
╔══════════════════════════════════════════════════════════╗
║  PHASE 9 PROGRESS                             7/7 DONE   ║
║  9A  Read & confirm the codebase           [x]           ║
║  9B  Expand runbook corpus (frozen)        [x]  ← REVIEW ║
║  9C  Eval harness + case set (frozen)      [x]  ← REVIEW ║
║  9D  Baseline eval (no RAG)                [x]  ← COST   ║
║  9E  Runbooks into the ranking prompt      [x]           ║
║  9F  A/B eval (RAG vs baseline)            [x]  ← COST   ║
║  9G  Docs, metrics, decision               [x]  ← REVIEW ║
╚══════════════════════════════════════════════════════════╝
```

Update this box and the per-step checkboxes as you go. A step is `[x]` only when
its **Verify** line passes, not when the code is written.
`← REVIEW` / `← COST` = stop and get explicit approval from Ryan before continuing
(see "Checkpoints").

---

## 0. WHO YOU ARE AND WHAT THIS IS

You are working on **Sentinel**, Ryan's automated incident-triage project. It is a
portfolio project for co-op applications. Phases 5–7 are done (see
`docs/claude-hardening.md` if present; the original build spec is in
`docs/claude-base.md` if present). This file is the authoritative guide for
Phase 9 and overrides those files where they conflict.

**The goal of Phase 9 is a defensible answer to one question:**

> Does giving Claude the matched runbooks improve its ability to find the
> commit that caused an incident, measured on a realistic eval set?

The deliverable is the *measurement*, not the feature. A well-run eval that shows
RAG did **not** help is a successful phase. A feature that "uses RAG" with no
evidence is a failed one.

---

## 1. GROUND TRUTH ABOUT THE CURRENT CODE (verified — do not re-derive wrongly)

Read these files before writing anything. The facts below were checked against
the code; if you find something that contradicts them, stop and report it.

| Area | Fact |
|---|---|
| Vector store | `core/services/vector_store.py`. Chroma, persistent at hardcoded `CHROMA_PATH = ".chroma"` (relative to cwd), collection `runbooks`, cosine space, Chroma's **default embedding function**. Only `sandbox/runbooks/*.md` are indexed (2 docs today: `db_failures`, `memory_leaks`). Ingested at startup in `core/main.py` lifespan. |
| Retrieval output | `find_matching_runbooks(error_signature, top_k=3)` returns `{id, title, similarity_score, primary_action}`. **Full runbook text is not returned.** |
| Commit diffs | `core/services/git_client.py`. **Not retrieved by similarity.** `git log --since/--until` over a 60-min window before the alert timestamp; each diff truncated to 3000 chars. Takes `repo_path` as an argument. |
| Commit ranking | `core/services/llm_analyzer.py::rank_suspect_commits(diffs, alert)`. Forced tool call `rank_commits`, strict schema, confidence 0–1, raises `LLMUnavailable` on any failure. **Prompt contains alert + diffs only. Runbooks are NOT passed in.** |
| Orchestrator order | `run_diagnostics`: diffs → runbooks → rank → save → Slack. Runbooks are already retrieved *before* ranking, so plumbing them in is cheap. A vector-store exception currently falls to the outer `except` and reverts the incident to `triggered`. |
| Postmortem | `core/services/postmortem.py` already includes matched runbooks in its prompt. This is the only place retrieval currently augments generation. |
| LLM client | `core/services/openrouter.py`, model `anthropic/claude-sonnet-5` via OpenRouter, no temperature set (provider default → non-deterministic). |
| Contract | `contract/pipeline_schema.json`. No `additionalProperties: false`, but every persisted field must still be intentional. |
| Existing metrics | `METRICS.md`: 3 runs, injected commit ranked #1 in 3/3. Timings: ~13.3s alert→suspects, ~13.5s resolve→postmortem (medians). |
| Style / CI | `black --line-length 110`, `flake8`, `pytest core/tests -q`, all external boundaries mocked in tests. Comments explaining a deliberate shortcut are prefixed `# ponytail:`. |

### The known flaw in the existing 3/3 result — read this carefully

`sandbox/chaos_cli.py` commits with the message `chore: inject bug=db_failure` and
the diff literally sets `{"bug": "db_failure"}`. The error signature says
`OperationalError`. There is usually **only one commit** in the window. So the
3/3 result measures "can Claude read a commit message that names the bug," not
"can Claude find a root cause." That is **label leakage**. Phase 9's eval must
not repeat it, and `METRICS.md` must say so honestly (Step 9G).

---

## 2. SCOPE

### In scope
1. A small, realistic runbook corpus (expand from 2 to ~8–10).
2. An offline-buildable, live-scored eval harness with ~24–30 fault cases.
3. A baseline score with the current ranking prompt.
4. Passing the relevant runbook content into `rank_suspect_commits`, behind a flag.
5. A paired A/B comparison, written up honestly in `METRICS.md` and `ADR.md`.

### Explicitly excluded (do NOT build, even if it seems like a quick win)
- **Indexing past incidents.** Too little history in a sandbox for retrieval to
  matter, so it cannot be shown to help. Defer.
- **Embedding or similarity-searching code diffs.** The time window is the right
  retrieval for "what changed recently." Vector search over diffs adds complexity
  with no expected benefit.
- LangChain / LlamaIndex / any RAG framework. Explicit functions only (ADR-1).
- Rerankers, hybrid search, chunking strategies, or swapping the embedding model
  — unless the eval shows retrieval itself is failing (wrong runbook at top-1),
  and even then propose it to Ryan first; don't do it.
- pgvector migration, hosted vector DBs, fine-tuning.
- Changing the `rank_commits` tool output schema (keeps A/B outputs comparable).
- Dashboard or Slack UI changes.
- Running the eval in CI (it costs money and is non-deterministic).

### Stop condition / timebox
Target: **2–3 working days total.** Ryan is in an active application window.
When 9G is done, stop. Do not start "one more improvement." If you are past
the timebox, stop at the end of the current step and report where things stand.

---

## 3. HARD CONSTRAINTS (non-negotiable)

1. **Measure before claiming.** No accuracy figure goes into `README.md`, `ADR.md`,
   or anything resume-facing unless it comes from a recorded eval run whose raw
   results file is committed under `eval/results/`.
2. **Never fabricate or hand-edit results.** If a run partially fails (rate
   limits, API errors), record the failures as failures and report them. Do not
   re-run only the failed cases of one condition and merge them silently.
3. **No leakage.** Ground-truth labels (culprit commit, expected runbook,
   fault category) must never reach the LLM. There is a test for this (9C).
4. **Freeze before you compare.** The runbook corpus is frozen at the end of 9B
   and the case set is frozen at the end of 9C, *before* any RAG-condition run.
   After freezing, do not edit runbooks or cases to change the outcome. If a
   case is genuinely broken (e.g. the culprit falls outside the time window),
   fix it, bump the eval-set version, and re-run **both** conditions.
5. **The baseline prompt must stay byte-for-byte identical** when the RAG flag is
   off. The A/B is only valid if the control is the real current behaviour.
   There is a regression test for this (9E).
6. **Eval imports production code.** The harness calls the real
   `git_client.get_recent_diffs`, `vector_store.find_matching_runbooks`, and
   `llm_analyzer.rank_suspect_commits`. Never re-implement the prompt inside the
   harness — that would evaluate a copy.
7. **Never pollute the Sentinel repo's git history.** Eval fixtures are built in
   temporary directories as throwaway git repos. Do not use `chaos_cli` for the eval.
8. **Secrets** stay in env vars (`OPENROUTER_API_KEY`). Nothing committed.
9. **Retrieval must not become a new failure point.** If the vector store throws,
   log it and rank without runbooks. The incident must not revert to `triggered`
   because Chroma failed.
10. Keep CI green: `black --check --line-length 110 core sandbox eval`,
    `flake8 core sandbox eval`, `pytest core/tests eval/tests -q`, all offline.

---

## 4. CHECKPOINTS — stop and wait for Ryan

| After | Why you stop | What to show |
|---|---|---|
| 9B | Corpus is about to freeze | The runbook list, one runbook in full, how they were written |
| 9C | Case set is about to freeze | Case count by category, 3 cases in full, culprit-position distribution, the leakage-test output |
| Before 9D and 9F live runs | Real API cost | `cases × trials × conditions` call estimate; run only on "go" |
| 9G | Defaults and public claims change | Results table, the proposed default for the flag, proposed README/METRICS text |

At a checkpoint, end your turn with a short summary and an explicit question.
Do not continue past it on your own.

---

## 5. STEPS

### 9A — Read and confirm the codebase `[x]`
- Read: `core/orchestrator.py`, `core/services/*.py`, `core/main.py`,
  `core/tests/*.py`, `contract/pipeline_schema.json`, `sandbox/runbooks/*.md`,
  `sandbox/chaos_cli.py`, `METRICS.md`, `ADR.md`, `.github/workflows/ci.yml`.
- Check every row of Section 1 against the code.
- Make `CHROMA_PATH` configurable: `os.getenv("SENTINEL_CHROMA_PATH", ".chroma")`.
  The eval needs an isolated store. Default behaviour unchanged.
- **Verify:** Write a 5–10 line summary of the pipeline in your reply, flag any
  mismatch with Section 1, `pytest core/tests -q` passes.

### 9B — Expand the runbook corpus, then freeze it `[x]` ← REVIEW
With 2 runbooks, "retrieval" is nearly a coin flip, and the eval can't say much.
- Add ~6–8 runbooks to `sandbox/runbooks/`, same format as `db_failures.md`
  (ID, Severity, Tags, Symptoms, Root Causes, Immediate Actions, Escalation).
  Suggested classes: request timeouts / upstream latency, null / missing-field
  handling, config type or parse errors, auth / credential failures,
  off-by-one / pagination bugs, dependency version regressions, rate limiting /
  429s, disk or file-handle exhaustion.
- **Write runbooks as generic operational documents, before writing any eval
  case.** They must not mention specific files, commits, or wording from cases.
  Writing runbooks to match cases is leakage by another route.
- Leave room for misses: some eval cases will deliberately have no matching runbook.
- **Verify:** Startup ingests all runbooks (`[core] runbooks ingested: N`);
  existing tests pass; `find_matching_runbooks` on each existing chaos error
  signature still returns the right runbook first.
- **Freeze:** record the corpus version (`RUNBOOK_CORPUS_VERSION = "v1"` in
  `eval/config.py`) and stop for review.

### 9C — Eval harness and case set, then freeze it `[x]` ← REVIEW

**Layout**
```
eval/
  __init__.py
  config.py           # versions, defaults, similarity floor candidates
  cases/              # one JSON file per case
  fixture.py          # builds a throwaway git repo for a case
  run_eval.py         # CLI: --condition {baseline,rag} --trials N --cases GLOB --out PATH
  report.py           # reads results files, prints comparison tables
  results/            # committed raw JSON outputs (one file per run)
  tests/              # offline unit tests for the harness
```
Use JSON, not YAML (no new dependency).

**Case schema**
```json
{
  "id": "cfg_pool_size_str_01",
  "category": "config_type_error",
  "alert": {
    "alert_name": "HTTP_500_Internal_Server_Error",
    "error_signature": "TypeError: '<' not supported between instances of 'str' and 'int'"
  },
  "base_files": { "app/db.py": "...", "app/config.json": "..." },
  "commits": [
    { "message": "refactor: load pool settings from env", "author": "a@example.com",
      "minutes_before_alert": 42, "files": { "app/config.json": "..." } }
  ],
  "label": {
    "culprit_index": 2,
    "expected_runbook_id": "rb_config_02"
  }
}
```
`expected_runbook_id` may be `null` (no runbook should match). The `label` block
is read only by the scorer.

**Fixture builder (`fixture.py`)**
- Create a temp dir, `git init`, commit `base_files` dated well before the window,
  then each commit with `GIT_AUTHOR_DATE` and `GIT_COMMITTER_DATE` set from
  `minutes_before_alert` relative to a fixed alert timestamp. `git log --since`
  filters on committer date, so set both.
- Return `(repo_path, alert_dict, label)`. Clean up the temp dir afterwards.

**Case-writing rules — this is where evals usually go wrong**
- **24–30 cases**, spread across ≥ 6 categories.
- **3–6 commits per case**, at least one a *plausible distractor*: it touches a
  related file or the same subsystem but isn't the cause.
- **Neutral, realistic commit messages.** Banned in messages, diffs, and code
  comments: `bug`, `inject`, `break`, `fault`, `fail`, `chaos`, `oops`, `fix`
  (for the culprit), or anything else that announces the answer.
- **Vary the culprit's position.** It must not always be the newest commit.
  Aim for a roughly even spread; report the distribution at the checkpoint.
- **~25% of cases have `expected_runbook_id: null`.**
- Keep each diff under the 3000-char truncation limit so truncation isn't a
  confound (report any case that exceeds it).
- Error signatures should look like real log lines, not descriptions of the bug.
- At least a few cases should be **hard**: the error is indirect, e.g. a
  timeout constant changed in one file surfaces as a 504 from another module.

**Scorer metrics (`report.py`)**
- Ranking: **top-1 accuracy**, **top-3 accuracy**, and **MRR**.
- Confidence: mean `confidence_score` of the #1 pick when right vs. when wrong.
- Retrieval: runbook top-1 accuracy on cases with an expected runbook, and the
  rate at which `null` cases still get a runbook above the similarity floor
  (the false-match rate).
- LLM failures (`LLMUnavailable`) are **counted as misses** and reported
  separately. Never dropped.
- Latency of the ranking call (median), for context only.
- Always print `n` (cases × trials) next to every number.

**Offline tests (`eval/tests/`)**
- Fixture builder: the commits it creates fall inside `get_recent_diffs`' window
  and come back in the expected order.
- Scorer: top-1 / top-3 / MRR on hand-built rankings.
- **Leakage test:** build every case and capture the prompt passed to the mocked
  `chat()`; assert that no `label` field value, case `id`, or `category` string
  appears in it. Run it for both conditions.
- Case lint: every case parses, has 3–6 commits, contains no banned word, and
  has `culprit_index` in range.

**Verify:** `pytest eval/tests -q` passes; harness dry-run with mocked `chat()`
over all cases completes. **Freeze:** set `EVAL_SET_VERSION = "v1"` and stop
for review.

### 9D — Baseline run `[x]` ← COST
- Isolated Chroma: `SENTINEL_CHROMA_PATH` set to a temp dir, ingest the frozen corpus.
- `python -m eval.run_eval --condition baseline --trials 3 --out eval/results/baseline_<date>.json`
- **3 trials per case.** The model is non-deterministic and n is small.
- Results file records: eval-set version, corpus version, model string, git
  SHA of Sentinel, timestamp, per-case per-trial rankings, errors.
- **Ceiling check:** if baseline top-1 is ≥ 95%, the cases are too easy to show
  any difference. Report it and propose harder cases. If Ryan approves, revise
  them, bump `EVAL_SET_VERSION`, re-freeze, re-run baseline. This is the *only*
  allowed case revision, and it happens before any RAG run.
- **Verify:** results file committed; `report.py` prints the baseline table.

### 9E — Runbooks into the ranking prompt `[x]`

**Code changes**
- `vector_store.find_matching_runbooks(..., include_content=False)`. When `True`,
  also return the runbook's **Symptoms** and **Root Causes** sections (parse the
  markdown headings; cap each runbook at ~1500 chars). Default output and the
  persisted `matched_runbooks` shape are **unchanged**. Content goes to the
  prompt only, never into Postgres or Slack.
- `rank_suspect_commits(diffs, alert, runbooks=None)`.
- Flag: `SENTINEL_RAG_RANKING` (`"0"`/`"1"`), **default `"0"`** until 9G decides.
- Similarity floor: `SENTINEL_RUNBOOK_FLOOR`. **Do not default to 0.7.** The
  correct `db_failures` match in METRICS.md scored 0.359. Pick the floor from
  9D's retrieval scores (the gap between correct matches and `null`-case
  scores), set it, and **freeze it before 9F**. Write down how it was picked.
- Orchestrator: wrap retrieval in its own `try/except`; on failure log
  `[orchestrator] {id} -- runbook retrieval failed, ranking without: {e}` and
  continue with `[]` (Constraint 9).

**Prompt design** (for the RAG branch only; the baseline string stays identical)
- Put runbooks *after* the alert and *before* the commits, inside clearly
  delimited tags, e.g. `<runbooks>` … `<runbook id="..." similarity="0.41">` …
- Tell the model what runbooks are **for** and what they are **not**:
  - They describe known *failure classes* and help interpret the error signature.
  - They are retrieved by text similarity and **may be irrelevant**. Ignore any
    that don't fit the error.
  - **The diffs are the evidence.** Rank a commit highly only if its diff content
    plausibly produces this error. Don't promote a commit just because it
    touches a file or keyword that a runbook mentions.
  - Root-cause lists in runbooks are possibilities, not findings.
- If no runbook clears the floor, omit the block entirely. Don't send an empty
  `<runbooks>` section, which invites the model to infer something from absence.
- Keep the instruction short. Long prompts here mostly add noise.
- Do not change `_RANK_TOOL`.

**Tests (offline, in `core/tests/`)**
- Flag off → the prompt passed to `chat()` is **exactly** equal to a stored
  golden string of the current prompt. (This is the A/B-validity regression test.)
- Flag on, runbooks above floor → the `<runbooks>` block is present, with content.
- Flag on, all runbooks below floor → no `<runbooks>` block.
- Retrieval raises → ranking still runs, incident is not reverted to `triggered`.
- Persisted `diagnostics.matched_runbooks` still validates against the contract
  and contains no runbook content.
- **Verify:** all of the above pass; CI commands from Constraint 10 pass.

### 9F — A/B run `[x]` ← COST
- Same frozen cases, same corpus, same floor, same model, same trial count.
- `python -m eval.run_eval --condition rag --trials 3 --out eval/results/rag_<date>.json`
- `report.py` prints, side by side:
  - top-1 / top-3 / MRR / LLM-failure count per condition, with n;
  - a **paired per-case table**: for each case, top-1 hits out of 3 in each
    condition, plus wins / losses / ties for RAG;
  - a breakdown for `null`-runbook cases specifically (does wrong context hurt?);
  - mean confidence when correct vs. incorrect, per condition.
- Don't compute a p-value and call it significant. With ~25 cases, report the
  paired counts and say plainly how large a difference would be needed to be
  meaningful.
- **Verify:** both results files committed; report output pasted into your reply.

### 9G — Docs, metrics, decision `[x]` ← REVIEW

**Decision rule for the flag default**
- RAG has **more case wins than losses** and **no drop in top-1** → propose
  default `"1"`.
- Roughly equal → propose default `"0"`, document it as "no measurable benefit
  at this corpus size."
- RAG is worse (especially on `null` cases) → keep `"0"` and document *why*
  (likely misleading context). This is a good finding, not a failure.
- Ryan decides. Don't flip the default before he approves.

**`METRICS.md` — add a new section; do not edit the Phase 5 tables**
- Methodology: eval-set + corpus versions, case count and categories, culprit
  position spread, distractor policy, trials, model, floor and how it was chosen.
- Results tables from 9F.
- A short "Limitations" list: synthetic cases written by the same author as the
  system, small n, single model, sandbox repo.
- Add a note under the Phase 5 runs: *"These runs used chaos-CLI commits whose
  messages named the injected bug, with typically one commit in the window; they
  verify the pipeline end-to-end but are not a measure of diagnostic accuracy.
  See Phase 9."*

**`ADR.md` — add ADR-7: Runbook context in commit ranking**
Context → Decision → Consequences, including: why runbooks and not past
incidents or diff embeddings; why behind a flag; the floor choice; the measured
result; what would change the decision (a bigger corpus, real incident history).

**`README.md`**
- Only if 9G's result supports it, update the "How it works → Diagnose" step to
  say runbook context is used in ranking, and link the METRICS section.
- If the flag stays off, the README doesn't claim RAG in ranking.

**Resume-claim guidance** (put this in your checkpoint message; don't edit
anything resume-facing yourself)
- Supported phrasing depends on the result, e.g. *"ranked the faulty commit #1
  in X% of N injected-fault cases (Y% → X% with runbook retrieval)"*. Use the
  numbers exactly as they appear in METRICS.md.
- If RAG didn't help: the baseline accuracy number stands on its own, and "RAG"
  stays attached only to the postmortem.

**Verify:** every number in README/ADR traces to a committed results file;
CI is green; status box fully `[x]`.

---

## 6. HOW TO WORK

- **One step at a time.** Finish, verify, update the status box, then move on.
- **Plan before editing** for 9C and 9E: state which files you'll touch and why,
  in 3–6 lines, then do it.
- **Small, reviewable diffs.** One logical change per commit, conventional
  commit messages (`feat(eval): ...`, `test(core): ...`, `docs: ...`).
- After every code change: `black --line-length 110`, `flake8`, relevant `pytest`.
- Use `# ponytail:` comments for deliberate shortcuts, matching the existing code.
- If something in this file turns out to be wrong about the code, **stop and
  say so.** Don't quietly work around it.
- If you're unsure whether something is in scope, it isn't. Ask.
- Report honestly. "Baseline top-1 was 64%, RAG was 62%, RAG lost 3 cases and
  won 2" is a perfectly good report.

---

## 7. TRAPS TO AVOID

1. **Leaky cases.** Commit messages or comments that name the cause make the
   eval meaningless. This already happened once (the Phase 5 runs).
2. **Tuning to the test.** Editing runbooks, cases, the floor, or the prompt
   *after* seeing RAG results, then re-running until it wins. Freezes exist to
   prevent this.
3. **Evaluating a copy.** Harness code that rebuilds the prompt instead of
   calling `rank_suspect_commits`.
4. **A moving control.** Any change to the baseline prompt string invalidates
   the comparison. The golden-string test guards it.
5. **Silent drops.** Excluding LLM failures, timeouts, or awkward cases from
   the denominator.
6. **Over-reading small n.** 25 cases × 3 trials doesn't support claims of
   statistical significance. Report counts.
7. **Context pollution.** Sending low-similarity runbooks "just in case." Wrong
   context can make ranking worse, which is why `null` cases and the floor exist.
8. **Scope creep.** Past-incident indexing, diff embeddings, rerankers, UI work.
   All excluded. Ryan's application window is the binding constraint.
9. **Persisting runbook text.** Content belongs in the prompt, not in Postgres,
   the contract, or Slack cards.
10. **Embedding-model downloads in CI.** Chroma's default embedder fetches a
    model on first use. Keep all CI tests mocked at the `vector_store` boundary.

---

## 8. DEFINITION OF DONE

- [ ] Runbook corpus v1 and eval set v1 frozen and reviewed by Ryan
- [ ] Baseline and RAG results files committed under `eval/results/`
- [ ] `report.py` reproduces the published tables from those files
- [ ] Flag default set per Ryan's decision; golden-prompt and retrieval-failure tests pass
- [ ] `METRICS.md` Phase 9 section + Phase 5 caveat; `ADR.md` ADR-7
- [ ] README claims match the result, and nothing more
- [ ] CI green
- [ ] **Stop.** Return to applications.