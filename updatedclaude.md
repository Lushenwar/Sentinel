# CLAUDE.md — Sentinel (Hardening & Presentation)

## CURRENT STATUS

```
╔══════════════════════════════════════════════════════════╗
║  HARDENING PROGRESS                           1.5/4 DONE ║
║  █████████░░░░░░░░░░░░░░░  PHASE 6 AUTHORED               ║
║  Phase 5: Live Verification & Real Metrics  [x]  (P0)    ║
║  Phase 6: Presentation Layer                [ ]  (P1)    ║
║  Phase 7: Resilience & Test Hardening       [ ]  (P2)    ║
║  Phase 8: Diagnostic Polish                 [ ]  (P3)    ║
╚══════════════════════════════════════════════════════════╝
```

Phase: Phase 5 complete (repo side) — resume document itself still needs its numbers updated per METRICS.md
Status: Extends the base CLAUDE.md. Work phases top to bottom in priority order.
Update this box AND the per-step checkboxes inside each phase as you finish.

## WHAT THIS FILE IS

This document extends the original `CLAUDE.md` and is the authoritative guide for
taking Sentinel from a shipped MVP to a defensible, recruiter-facing portfolio
project. Every phase boundary, priority tag, step, exit criterion, and constraint
defined here is binding. Do not deviate without explicit user approval. Do not
begin a lower-priority phase before the phase above it is complete. Phase 5 (P0)
blocks all others — it is the only phase whose failure invalidates the resume.

---

## SCOPE OF THIS PHASE

### Hardening Target:

Turn a working-but-unverified MVP into a project that (a) provably runs
end-to-end against real infrastructure, (b) reads as professional in the first 60
seconds a reviewer sees it, and (c) behaves correctly and honestly under failure.
Deliberately narrow. The goal is a tight, defensible, shippable artifact — not
maximum feature count.

### The Stop Condition:

When Phases 5, 6, and 7 are complete, Sentinel is resume-ready and
interview-ready. STOP and return to job applications. Phase 8 is optional polish
for idle time only. The single largest risk to this project is over-building it
while the application window is open.

### Excluded from Hardening (Do NOT Build):

* Mocked distributed tracing / OpenTelemetry trace simulation.
* Cascading / multi-hop failure simulation across mock services.
* Live cloud provider integrations (AWS/GCP/Azure).
* Multi-repo dependency parsing or automated code-fix generation.
* Any feature that adds fake complexity to the sandbox rather than real signal to
  the reviewer. High-effort, low-payoff at this stage.

---

## RESUME INTEGRITY CONSTRAINT

The resume currently claims `<10s` suspect-commit surfacing and `<30s` postmortem
generation. These are **unverified guesses until Phase 5 is complete.** Binding
rules:

* No number reaches the resume, README, or an interview answer until it has been
  measured against a real run and recorded in `METRICS.md`.
* If a measured value differs from the current claim, the resume changes to match
  the measurement — never the reverse.
* The `20+ min manual baseline` must map to a real, describable manual process
  (how long it actually took to find a bad commit by hand) or it is removed.
* Every external-facing figure must have a defensible answer to "compared to
  what, measured how, across how many runs?"

---

## IMPLEMENTATION PHASES

---

### PHASE 5: LIVE VERIFICATION & REAL METRICS

**Priority:** P0 — Blocking. Nothing else proceeds until every step below is `[x]`.
**Duration:** Half a day to one day.
**Rationale:** A portfolio project that has not run start-to-finish is worth
almost nothing, and it is the only thing standing behind the numbers already on
the resume.
**Exit Criterion:** At least three clean end-to-end runs against a real Postgres
instance, with measured timings recorded in `METRICS.md` that match the resume
claims word-for-word, and zero mocked shortcuts anywhere in the executed path.

* **Step 5A — Provision real Postgres.** `[x]`
  * Local via Docker (`docker run --name sentinel-pg -e POSTGRES_PASSWORD=... -p 5432:5432 -d postgres:16`) or a Neon project.
  * Bind the connection string to `DATABASE_URL` in an env var / `.env`, never hardcoded.
  * Apply the schema and confirm tables exist for incident state and log warehousing.
  * *Verify:* `psql "$DATABASE_URL" -c "\dt"` lists the incident + log tables.
  * *Gotcha:* If the MVP was ever run against SQLite or an in-memory store, confirm the migrations actually target Postgres before proceeding.

* **Step 5B — Confirm orchestrator I/O against real Postgres.** `[x]`
  * Boot the FastAPI core (`uvicorn core.main:app --reload`) pointed at the real DB.
  * Confirm it reads and writes incident state cleanly — no silent ORM fallbacks, no swallowed connection errors.
  * *Verify:* A manually inserted incident row is retrievable through the API.

* **Step 5C — Ingest runbooks into the live vector store.** `[x]`
  * Run the Chroma/pgvector ingestion over `sandbox/runbooks/*.md`.
  * Confirm embeddings persist and a known error string returns the correct runbook by cosine similarity.
  * *Verify:* Querying `"connection pool"` returns `rb_db_04` (or equivalent) above your similarity floor.
  * *Gotcha:* If using `pgvector`, confirm the extension is actually enabled (`CREATE EXTENSION vector;`) on the real instance, not just locally assumed.

* **Step 5D — Dry-run each stage in isolation.** `[x]`
  * Before the full loop, exercise each service once: `git_client` slices a real diff window; `llm_analyzer` returns schema-valid JSON from a real Claude call; `vector_store` returns a match; the Slack webhook posts a test card.
  * *Verify:* Each of the four produces real output with no exceptions.
  * *Gotcha:* Confirm the Slack Incoming Webhook URL is live and the channel receives the test card. A dead webhook silently no-ops.

* **Step 5E — Execute the full end-to-end loop.** `[x]`
  * Run `python -m sandbox.chaos_cli trigger-bug`.
  * Follow the complete chain with NO mocked shortcuts: faulty commit injected → error rate spikes → alert intercepted → Postgres logs queried → git diffs pulled → Claude ranks suspect commits → runbook matched by vector similarity → Slack diagnostic card fires → postmortem markdown generated on resolution.
  * *Verify:* The injected bad commit is the one Sentinel ranks #1, the Slack card arrives formatted, and a postmortem `.md` is produced.
  * *Gotcha:* If Claude ranks the wrong commit, that is a real finding — do not paper over it. Note it; it may be a prompt or diff-window bug worth fixing before you demo.

* **Step 5F — Instrument and measure timings.** `[x]`
  * Add lightweight timestamps at two boundaries: (1) alert-fired → suspect commit surfaced, (2) resolution → postmortem draft complete.
  * Run the full loop 3–5 times. Record each run's two values.
  * Compute min / median / max for each. Median is what you cite.
  * *Verify:* You have a table of at least 3 runs with both timings each.

* **Step 5G — Write METRICS.md.** `[x]`
  * Record: what was measured, how (the two boundaries), how many runs, the median values, and the hardware/DB used (local vs Neon changes latency).
  * State the manual baseline honestly — the real process and rough time it replaces.
  * *Verify:* A reader of `METRICS.md` could reproduce your measurement.

* **Step 5H — Reconcile the resume and cutlines.** `[x]`
  * Set the resume bullets to the measured medians. If the postmortem takes 45s, the bullet says 45s.
  * Anchor or remove the manual-baseline comparison.
  * *Verify:* Every number on the Sentinel resume block appears in `METRICS.md`.

**Phase 5 Danger Zone:** Do not let "one clean run" turn into "rebuild the
sandbox." The MVP works. Verify it, measure it, move on. If a step reveals a real
bug (e.g. 5E ranks the wrong commit), fix that specific bug — do not re-architect.

---

### PHASE 6: PRESENTATION LAYER

**Priority:** P1 — Highest ROI. A reviewer forms their entire opinion here, often
without reading a line of source.
**Duration:** One day.
**Rationale:** Nobody clones and runs a student project. They watch a clip, skim
the README, and leave. This phase is where the whole build pays off.
**Exit Criterion:** A fresh clone runs with one command, the README shows the
system working above the fold, and every major architectural decision is written
down and defensible aloud.

* **Step 6A — Record the demo and embed a GIF.** `[ ]` *(script + README slot ready in `docs/demo-script.md`; recording is a user action)*
  * Record a 60–90s screen capture. Beat sheet: `0:00` healthy state / traffic → `0:15` trigger chaos script → `0:30` alert fires + dashboard updates → `0:55` faulty commit surfaced + Slack post → `1:20` postmortem generated.
  * Convert to GIF (or upload video and link a thumbnail). Embed at the very top of the README, above the fold.
  * *Verify:* GIF autoplays on GitHub (keep it under ~10MB) and communicates the full loop without audio.
  * *Gotcha:* The diff viewer and Slack card are the two most impressive on-screen moments — make sure both are clearly visible in frame.

* **Step 6B — Author docker-compose.yml.** `[ ]` *(compose + Dockerfiles authored; clean-clone verify pending — Docker not installed on this machine)*
  * Bring up four services: Next.js dashboard, FastAPI core, Postgres, load generator / sandbox.
  * Use `depends_on` + a healthcheck on Postgres so the core waits for the DB.
  * Pull all secrets from env vars / an `.env` file referenced by the compose, never inline.
  * Target: `docker-compose up` from a clean clone yields a working system.
  * *Verify:* `git clone` into a fresh directory → set env → `docker-compose up` → dashboard reachable and a triggered incident flows end-to-end.
  * *Gotcha:* This step doubles as a second reproduction of Phase 5. If it does not work in a clean container, you have an undocumented local dependency — find it now.

* **Step 6C — Write ADR.md.** `[x]`
  * Format each record: Context → Decision → Consequences / trade-offs.
  * Cover at minimum: (1) no LangChain/CrewAI — explicit state loops; (2) polling/SSE over WebSockets for the MVP; (3) Chroma/pgvector over a hosted vector DB (Pinecone); (4) FastAPI over Flask; (5) structured JSON via Claude tool calls over free-form parsing; (6) simulated sandbox over live infra.
  * *Verify:* You can read each record aloud as a complete answer to "why did you choose X over Y?"

* **Step 6D — README structure pass.** `[x]`
  * Order: demo GIF → one-line pitch → quickstart (`docker-compose up`) → architecture diagram (reuse the base CLAUDE.md ASCII) → how-it-works (Trigger → Diagnose → Communicate → Document) → link to ADR.md and METRICS.md.
  * *Verify:* A reviewer scrolling for 30 seconds understands what it is, sees it run, and knows how to run it.

---

### PHASE 7: RESILIENCE & TEST HARDENING

**Priority:** P2 — Makes it behave senior, not just look senior. Do before Phase 8.
**Duration:** One day.
**Rationale:** Fallback handling is the most interview-defensible engineering on
the list ("what happens when the LLM breaks?"), and a green CI badge is a real
trust signal.
**Exit Criterion:** A forced LLM failure degrades gracefully instead of crashing,
and the repo shows a passing CI badge backed by tests that exercise real logic.

* **Step 7A — Deterministic LLM fallbacks.** `[ ]`
  * Handle three failure modes explicitly: Claude timeout, malformed/non-schema JSON, and empty/refused response.
  * On any failure, degrade: emit the raw git diffs + logs with a `"Diagnostic unavailable — manual investigation required"` flag on the incident.
  * Model this as a real terminal state in the state machine, not a bare try/except. It must still write a valid pipeline payload conforming to `contract/pipeline_schema.json`.
  * *Verify:* Force each failure mode (bad API key, injected malformed response, forced timeout) and confirm the pipeline finishes cleanly with the degraded flag and no fabricated diagnosis.

* **Step 7B — Meaningful backend tests.** `[ ]`
  * Using `core/tests/test_orchestrator.py` and `test_llm_logic.py`, cover: state-machine transitions (each hop Trigger→Diagnose→Communicate→Document), diff-window extraction correctness, runbook match ranking, and the 7A fallback path.
  * Mock the Claude call at the boundary so tests are deterministic and offline.
  * *Verify:* `pytest` passes locally; tests fail if you deliberately break a transition.
  * *Gotcha:* Ignore coverage-percentage targets. A few tests on real logic beat 80% coverage of getters.

* **Step 7C — Frontend smoke tests (light).** `[ ]`
  * Minimal Jest / React Testing Library coverage: the incident feed renders a list, the diff viewer mounts, the postmortem editor loads content.
  * *Verify:* `npm test` passes in the dashboard package.

* **Step 7D — GitHub Actions CI + badge.** `[ ]`
  * Workflow on every push: install, run `pytest`, run `black --check`/`flake8`, run `npm test` + ESLint on the dashboard.
  * Add the passing badge to the top of the README.
  * *Verify:* A green checkmark on the latest commit; a deliberately broken test turns the badge red.

---

### PHASE 8: DIAGNOSTIC POLISH (OPTIONAL)

**Priority:** P3 — Cheap wins on things that already exist. Idle-time only, after
Phases 5–7. Skippable.
**Duration:** Half a day.
**Exit Criterion:** Uncertainty is surfaced honestly in the UI, the RAG flow is
legible and documented, and diffs render like a real tool.

* **Step 8A — Confidence-threshold flag.** `[ ]`
  * The contract already carries `confidence_score`. When it is below `0.70`, render `"Low Confidence — manual investigation recommended"` instead of presenting a guess as fact. Reinforces the same honesty story as 7A.
  * *Verify:* A low-confidence incident visibly renders differently from a high-confidence one.

* **Step 8B — RAG legibility.** `[ ]`
  * Make the chain explicit in code and named in the README: extract error string → vector query for runbook → pass diffs + logs + runbook to Claude → structured diagnostic card.
  * *Verify:* You can point at the code and narrate the RAG pattern in one breath.

* **Step 8C — Diff viewer upgrade.** `[ ]`
  * Upgrade `DiffViewer.tsx` to line-by-line, syntax-highlighted diffs (e.g. `react-diff-viewer`). This is the component most visible in the Phase 6 GIF.
  * *Verify:* Diffs render with syntax highlighting and clear add/remove coloring.

---

## DANGER ZONES — TRAPS TO AVOID

1. **Framework Over-indexing:** Do not spend time parsing or setting up massive
   orchestration wrappers (LangChain/CrewAI). Use pure, explicit state loops with
   clean Python functions. It is substantially cleaner, easier to debug, and more
   interview-defensible.
2. **Mocking Blindly:** Ensure data transitions look highly realistic. The
   simulated log lines should explicitly match production-level output profiles.
3. **Leaking Secrets:** Ensure API keys for Claude or database strings are firmly
   bound to explicit system environment variables, isolated safely from
   repository tracks. This extends to `docker-compose.yml` and CI — secrets live
   in env vars and GitHub Actions secrets, never committed.
4. **Gold-Plating Over Shipping:** The application window is open now. Once
   Phases 5–7 are done, STOP. Do not drift into the Excluded list. A tight
   defensible project beats an endlessly-polished one nobody has seen.
5. **Unverified Metrics:** Never let a resume or interview number exist that has
   not been measured against a real run and recorded in `METRICS.md` (see Resume
   Integrity Constraint).
6. **Papering Over Real Bugs:** If Phase 5 reveals the engine ranks the wrong
   commit or matches the wrong runbook, that is a finding to fix, not to hide
   behind a curated demo. A demo that only works on one rehearsed input will not
   survive an interviewer's "what if I change this?"

---

## ENGINEERING GUIDELINES

* **Principal Engineering Mindset:** Write code focused heavily on visibility and
  structured error telemetry.
* **Contract Isolation:** Changes impacting tracking variables or communication
  boundaries between backend runtimes and frontend clients must instantly map
  back to modifications inside `contract/pipeline_schema.json`. The Phase 7A
  degraded state must itself emit a contract-valid payload.
* **Strict No-Fake Rules:** The dashboard must never render fabricated diagnostic
  insights. Every markdown file or ranked layout calculation must flow naturally
  as an output calculation executed directly by your engine pipelines. Phase 7A
  exists precisely to honor this: when the LLM fails, degrade honestly rather than
  invent a diagnosis.
* **Defend Every Decision:** Any architectural choice worth making is worth
  recording in `ADR.md` with its trade-off. If you cannot state why you chose it
  over the alternative, you are not ready to defend it in an interview.
* **Measure Before Claiming:** Timings, deltas, and impact figures are recorded
  from real runs in `METRICS.md` before they appear anywhere external.
* **Every Step Has a Verify:** No step in this file is complete until its `Verify`
  line passes. A checkbox is `[x]` only when the verification, not just the code,
  is done.

---

## COMPLETION LEDGER

Sentinel is resume-ready and interview-ready when ALL of the following hold:

* [x] Phase 5 — all steps 5A–5H `[x]`; `METRICS.md` exists; resume numbers must be set to the measured medians in `METRICS.md` (user action: update the resume document).
* [ ] Phase 6 — demo GIF above the fold; `docker-compose up` works from clean clone; `ADR.md` covers all six decisions.
* [ ] Phase 7 — forced LLM failure degrades honestly; `pytest` meaningful and passing; green CI badge on README.

At that point: STOP building and return to applications. Phase 8 is bonus only.