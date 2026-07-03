# CLAUDE.md — Sentinel

## CURRENT STATUS

```
╔══════════════════════════════════════════════════════════╗
║  MVP DEVELOPMENT PROGRESS                       3/4 DONE ║
║  ██████████████████░░  PIPELINE ACTIVE                  ║
║  Phase 1: Simulation & Core Orchestrator    [DONE]       ║
║  Phase 2: Context Extraction & LLM Layer    [DONE]       ║
║  Phase 3: Integration & Slack Briefing      [DONE]       ║
║  Phase 4: Next.js Incident Dashboard        [PENDING]    ║
╚══════════════════════════════════════════════════════════╝

```

Phase: Phase 4 — Next.js Incident Dashboard
Status: Phase 3 complete — Ready for Phase 4
Update this as you finish each step.

## WHAT THIS FILE IS

This document is the authoritative guide for developing Sentinel. Every architectural decision, phase boundary, data contract, and engineering constraint defined here is binding. Do not deviate from it without explicit user approval.

---

## PRODUCT DEFINITION

Sentinel is an automated incident triage engine that intercepts operational alerts, correlates infrastructure context with recent code changes, matches failure signatures against runbooks, and instantly briefs engineers before drafting an automated postmortem.

Instead of connecting to high-risk production infrastructure, Sentinel operates entirely against a high-fidelity **Simulated Sandbox Environment** consisting of a toy codebase (capable of receiving injected "bad commits"), a mock traffic generator, and a localized alerting simulation. It provides a flawless, end-to-end demonstration of automated incident response.

### What Sentinel IS:

* A deterministic incident orchestration pipeline (Trigger → Diagnose → Communicate → Document).
* A root-cause analyzer that correlates commit histories, git diffs, and log traces using structured LLM evaluation.
* A local-first developer tool that uses vector embeddings to map raw exceptions to existing runbooks.
* A highly scannable Next.js operational dashboard for tracking active incidents and generated postmortems.

### What Sentinel IS NOT:

* A real-time production monitoring agent or an APM competitor (like Datadog or New Relic).
* A free-form conversational chatbot meant for debugging infrastructure live.
* A tool that performs automated rollbacks or modifies live cloud codebases.

### How It Works:

1. **Trigger:** A mock deployment script injects a faulty commit into the sandbox repository, spiking the traffic generator's error rates and triggering a simulated critical alert webhook.
2. **Diagnose:** Sentinel intercepts the alert, queries local Postgres logs, pulls recent git diffs, ranks suspect commits using Claude Sonnet structured JSON outputs, and fetches matching runbooks using vector similarity.
3. **Communicate:** The system constructs an incredibly concise operational summary and dispatches an asynchronous structured diagnostic card to an active Slack channel via an Incoming Webhook.
4. **Document:** Upon simulated incident resolution, the orchestration loop synthesizes the entire timeline into an perfectly structured postmortem markdown document ready for human export to Notion/Confluence.

---

## SCOPE CONSTRAINTS

### MVP Target Domain:

Web application infrastructure errors (HTTP 5xx spikes, database connection timeouts, processing queues stalling). Deliberately narrow to ensure absolute reliability during live demonstrations.

### Supported Sandbox Ecosystem:

* Single-target Node.js or Python toy application codebase.
* Linear Git commit history mimicking normal development workflows.
* Structured logs outputting in JSON formats (`timestamp`, `level`, `message`, `traceback`, `endpoint`).
* Local or Neon-hosted PostgreSQL instance for internal state tracking and log data warehousing.

### Excluded from MVP:

* Real-time cloud provider integrations (AWS, GCP, Azure IAM profiling).
* Live distributed tracing frameworks (OpenTelemetry collector orchestration).
* Multi-repo cross-dependency parsing.
* Automated code fix generation or live deployment self-healing loops.

---

## SYSTEM ARCHITECTURE

Sentinel decouples engine orchestration from simulation metrics and user interface components.

```
                      ┌────────────────────────────────────────┐
                      │        Next.js Frontend Client         │
                      │   (Timeline, Diff Viewer, Postmortems) │
                      └───────────────────▲────────────────────┘
                                          │  REST / WebSockets
┌───────────────────────┐     ┌───────────▼────────────┐     ┌───────────────────────┐
│  Simulation Sandbox  │     │   Sentinel Core App   │     │ External Integrations │
│ (Toy Repo, Fake load, │────>│    (FastAPI / State    │────>│ (Slack Webhooks,      │
│  Mock Alert Engine)   │     │  Machine Orchestrator) │     │  Claude Sonnet API)   │
└───────────────────────┘     └───────────▲────────────┘     └───────────────────────┘
                                          │
                                          ▼
                              ┌───────────────────────┐
                              │  PostgreSQL + Chroma  │
                              │ (Timelines & Vector   │
                              │   Runbook Storage)    │
                              └───────────────────────┘

```

### 1. Sentinel-core (Python Engine)

* **FastAPI Endpoint Server:** Exposes hooks for incoming alerts and communication layers for the frontend client.
* **State Machine Orchestrator:** Manages internal execution state without bloated abstractions. Coordinates timeline assembly.
* **Context Extraction Pipeline:** Intersects git history with log timestamps to extract candidate diff windows.
* **Vector Runbook Engine:** Employs Chroma DB or `pgvector` locally to handle fast cos-sim matches of alerts to markdown markdown-based runbooks.

### 2. simulation-sandbox (Local Testing Framework)

* **Toy Target App:** Simple application featuring functional endpoints alongside modular toggleable bugs (e.g., memory leak, unhandled database exception).
* **Chaos Engine / Load Generator:** Script driving automated traffic profiles and triggering systematic code regressions.

### 3. Sentinel-dashboard (Next.js Application)

* Real-time incident response screen illustrating active triage metrics.
* Comparative git diff explorer emphasizing suspect commits ranked by the LLM analysis layer.
* Clean markdown preview and editor workspace for generated incident postmortems.

---

## THE CORE PIPELINE JSON CONTRACT

Communication across state machines utilizes strict, structured schemas. The state model ensures auditability at every hop.

### Pipeline Payload Contract:

```json
{
  "incident_id": "inc_2026_0703_a",
  "status": "triaging",
  "trigger": {
    "source": "mock_sentry",
    "alert_name": "HTTP_500_Internal_Server_Error",
    "timestamp": "2026-07-03T11:29:04Z",
    "error_signature": "OperationalError: connection to server at '127.0.0.1' failed: Connection refused"
  },
  "diagnostics": {
    "suspect_commits": [
      {
        "commit_hash": "a1b2c3d",
        "author": "jdoe@company.com",
        "timestamp": "2026-07-03T11:25:10Z",
        "rationale": "Modified connection pooling logic in db/pool.py. Introduced configuration parameter that defaults to string instead of integer.",
        "confidence_score": 0.92
      }
    ],
    "matched_runbooks": [
      {
        "id": "rb_db_04",
        "title": "Database Connection Pool Exhaustion",
        "similarity_score": 0.88,
        "primary_action": "Verify maximum pool limits and check target connection strings in environment configurations."
      }
    ],
    "impact_assessment": {
      "error_rate_delta_pct": 340.5,
      "estimated_affected_users": 142
    }
  },
  "postmortem_draft_url": null
}

```

---

## REPOSITORY STRUCTURE

```
Sentinel/
├── README.md
├── CLAUDE.md
├── contract/
│   └── pipeline_schema.json
│
├── core/                              # Sentinel-core (Python Backend)
│   ├── pyproject.toml
│   ├── main.py
│   ├── orchestrator.py
│   ├── services/
│   │   ├── git_client.py
│   │   ├── llm_analyzer.py
│   │   └─- vector_store.py
│   └── tests/
│       ├── test_orchestrator.py
│       └── test_llm_logic.py
│
├── sandbox/                           # Target Environment Simulator
│   ├── app/                           # The Toy Application
│   ├── load_generator.py
│   ├── chaos_cli.py
│   └── runbooks/                      # Vector DB Ingestion Source
│       ├── db_failures.md
│       └── memory_leaks.md
│
└── dashboard/                         # Next.js Operations Panel
    ├── package.json
    ├── src/
    │   ├── app/
    │   │   ├── page.tsx               # Active Incident Feed
    │   │   └── incidents/
    │   │       └── [id]/page.tsx      # Diagnostic Timeline Drilldown
    │   └── components/
    │       ├── DiffViewer.tsx
    │       └── PostmortemEditor.tsx

```

---

## IMPLEMENTATION PHASES

---

### PHASE 1: SIMULATION & CORE ORCHESTRATOR

**Duration:** 2 Weeks.
**Exit Criterion:** Running `python -m sandbox.chaos_cli trigger-bug` successfully injects code, catches an exception, spins the internal python backend orchestrator, and saves a blank structural incident state inside the Postgres DB.

* **Step 1A:** Implement the target toy web app with pre-packaged functional regressions.
* **Step 1B:** Construct the local load-generator script modeling fluctuating transaction flows.
* **Step 1C:** Wire up FastAPI server to intercept simulation log streams and store them cleanly inside PostgreSQL.

---

### PHASE 2: CONTEXT EXTRACTION & LLM LAYER

**Duration:** 2 Weeks.
**Exit Criterion:** Given a generated alert time, the backend runs an isolated git-log parsing sweep, maps target diff data to Claude Sonnet using strict JSON schemas, and retrieves an accurately scored array of suspect commits.

* **Step 2A:** Design git log wrapper to slice localized repository commit trees cleanly based on target query frames.
* **Step 2B:** Setup local Chroma/pgvector schemas. Ingest mock markdown runbook directories using text embeddings.
* **Step 2C:** Implement structured JSON schemas inside Claude Tool Calls to force predictable parser pipelines.

---

### PHASE 3: INTEGRATION & SLACK BRIEFING

**Duration:** 1 Week.
**Exit Criterion:** Triggering an exception fires an asynchronous runtime chain that pushes a highly professional, well-formatted operational diagnostic card directly into a physical Discord or Slack channel webhook.

* **Step 3A:** Implement target Incoming Slack Webhook template formatting structures.
* **Step 3B:** Write automated completion hooks that auto-generate structural markdown postmortems upon resolution events.

---

### PHASE 4: NEXT.JS INCIDENT DASHBOARD

**Duration:** 2 Weeks.
**Exit Criterion:** Next.js operation view rendering incident states in real time, tracking live triage progressions, rendering highlighted code diff files alongside the postmortem workspace.

* **Step 4A:** Build API bridges between FastAPI timelines and Next.js view containers using standard polling or server-sent events.
* **Step 4B:** Implement full interactive Markdown workspace for manipulating generated postmortem states directly from UI interfaces.

---

## DANGER ZONES — TRAPS TO AVOID

1. **Framework Over-indexing:** Do not spend time parsing or setting up massive orchestration wrappers (LangChain/CrewAI). Use pure, explicit state loops with clean Python functions. It is substantially cleaner, easier to debug, and more interview-defensible.
2. **Mocking Blindly:** Ensure data transitions look highly realistic. The simulated log lines should explicitly match production-level output profiles.
3. **Leaking Secrets:** Ensure API keys for Claude or database strings are firmly bound to explicit system environments variables, isolated safely from repository tracks.

---

## ENGINEERING GUIDELINES

* **Principal Engineering Mindset:** Write code focused heavily on visibility and structured error telemetry.
* **Contract Isolation:** Changes impacting tracking variables or communication boundaries between backend runtimes and frontend clients must instantly map back to modifications inside `contract/pipeline_schema.json`.
* **Strict No-Fake Rules:** The dashboard must never render fabricated diagnostic insights. Every markdown file or ranked layout calculation must flow naturally as an output calculation executed directly by your engine pipelines.