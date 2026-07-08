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
