# Architecture Decision Records — Sentinel

Format: Context → Decision → Consequences. Each record is a complete answer to
"why did you choose X over Y?"

---

## ADR-1: Explicit state loops instead of LangChain / CrewAI

**Context.** The pipeline is four sequential hops (Trigger → Diagnose →
Communicate → Document) with one LLM call in two of them. Orchestration
frameworks promise chaining, retries, and memory — none of which this shape of
problem needs.

**Decision.** Plain Python functions coordinated by a small orchestrator module
(`core/orchestrator.py`). State lives in one Postgres row per incident; each hop
is a function that reads the row, does work, writes the row.

**Consequences.** Every state transition is a grep-able line of code — debugging
is reading a 60-line file, not framework internals. No dependency churn from a
fast-moving framework. Trade-off: if the pipeline grew to many branching agent
interactions, we would be hand-rolling what a framework provides; at four fixed
hops that day is far away.

---

## ADR-2: Polling over WebSockets for the dashboard

**Context.** The dashboard needs to reflect incident state as diagnostics
complete. Incidents change state a handful of times over minutes, not thousands
of times per second.

**Decision.** The Next.js dashboard polls the REST API every 3 seconds.

**Consequences.** Zero connection-lifecycle code (reconnects, heartbeats,
sticky sessions), and the same GET endpoints serve both the UI and curl. Worst
case a state change appears 3s late — invisible next to a 13s diagnosis stage
(see METRICS.md). Trade-off: at many concurrent viewers polling would waste
requests; SSE is the documented upgrade path if that ever matters.

---

## ADR-3: Local Chroma over a hosted vector DB (Pinecone)

**Context.** Runbook matching needs cosine similarity over a corpus of
*markdown runbooks* — currently 2 documents, realistically dozens.

**Decision.** Chroma in embedded/persistent mode, ingested from
`sandbox/runbooks/*.md` at startup.

**Consequences.** No API key, no network hop, no vendor account for a corpus
that fits in memory thousands of times over; ingestion is idempotent upsert at
boot so the store can be deleted freely. Trade-off: no managed scaling or
replication — irrelevant below tens of thousands of documents, and the
`vector_store.py` interface isolates the swap if it ever happens.

---

## ADR-4: FastAPI over Flask

**Context.** The core service is a small JSON API that must run LLM diagnostics
*after* responding to the alert webhook, so the alerting side never waits on a
13-second LLM call.

**Decision.** FastAPI.

**Consequences.** `BackgroundTasks` gives fire-and-forget diagnostics with no
Celery/queue infrastructure; Pydantic-style typing and auto OpenAPI docs come
free. Trade-off: slightly more magic than Flask, but the async-background
pattern alone replaces a message broker that Flask would have needed.

---

## ADR-5: Structured JSON via tool calls over free-form LLM parsing

**Context.** Claude ranks suspect commits. The output feeds directly into the
pipeline contract (`contract/pipeline_schema.json`), Slack cards, and the
dashboard — a malformed field crashes downstream consumers.

**Decision.** Commit ranking is forced through a tool call (`rank_commits`)
with a strict JSON schema: required fields, 0–1 bounded confidence scores. The
model cannot respond except by satisfying the schema.

**Consequences.** No regex extraction from prose, no "here's your JSON:"
preamble handling; parse failures become explicit, catchable exceptions rather
than silently wrong data. Trade-off: schema rigidity means prompt iterations
must update the schema too — acceptable, since the schema *is* the contract.

---

## ADR-6: Simulated sandbox over live infrastructure

**Context.** Demonstrating incident triage requires incidents. Real
infrastructure produces them rarely, unpredictably, and with blast radius.

**Decision.** A toy FastAPI app with injectable bugs (`sandbox/`), a load
generator that fires alerts on error-rate spikes, and a chaos CLI that commits
real faulty code to a real git history. Everything downstream of the alert —
Postgres, git analysis, Claude, Chroma, Slack — is real.

**Consequences.** Incidents are reproducible on demand (the demo can run 100
times), and the injected commit gives ground truth to score the LLM against —
Phase 5 verified 3/3 correct #1 rankings *because* ground truth exists.
Trade-off: no exposure to messy production alert noise; the mitigation is that
the simulation's log and alert shapes mirror production profiles (mock Sentry
payloads, structured JSON logs).

---

## ADR-7: Runbook context in commit ranking — built, measured, left off

**Context.** Sentinel already retrieved matching runbooks (Chroma, cosine
similarity) but only used them in the postmortem and the Slack card. The open
question was whether passing them into `rank_suspect_commits` would help
Claude find the faulty commit. Two other retrieval targets were considered and
rejected: **past incidents**, because a sandbox has too little history for
retrieval over it to matter, and **diff embeddings**, because "what changed
recently" is already answered exactly by the git time window.

**Decision.** Runbook text (Symptoms + Root Causes, capped at 1500 chars) can
be passed into the ranking prompt behind `SENTINEL_RAG_RANKING`, **default
off**. Only runbooks scoring at or above `SENTINEL_RUNBOOK_FLOOR` (0.35) are
sent; if none clear it, the block is omitted and the prompt is byte-identical
to the no-runbook prompt (guarded by a golden-string test). The prompt tells
the model runbooks may be irrelevant and that diffs are the evidence. Runbook
text is never persisted. A retrieval failure is logged and ranking proceeds
without runbooks.

The floor was picked from the baseline's retrieval scores before any RAG run
(maximise correct runbooks kept minus null cases given a runbook).

**Measured result** (METRICS.md, Phase 9; 24 cases × 3 trials): baseline
90.3% top-1, RAG 91.7%. On the 10 cases where runbook text actually reached the
prompt, both scored 27/30; the single extra RAG hit came from a case whose
prompt was unchanged. **No measurable benefit**, and no measurable harm on
null-runbook cases.

**Consequences.** The flag stays off, so the shipped ranking path is the
measured baseline. The plumbing and the eval harness stay, because the answer
depends on two things that could change:
- **Retrieval quality.** The correct runbook is top-1 in only 10/17 cases, and
  at the floor only 8/17 cases receive it. Better retrieval (richer alert text
  than a one-line error, or a stronger embedding model) would raise the
  ceiling on what runbooks can contribute.
- **Baseline headroom.** At 90% top-1 there is little left to win. A larger,
  harder or real incident corpus — especially real runbooks written by the
  team that wrote the code — would be the test that could change this decision.
