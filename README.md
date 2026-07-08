# Sentinel

![CI](https://github.com/Lushenwar/Sentinel/actions/workflows/ci.yml/badge.svg)

<!-- DEMO GIF: record per docs/demo-script.md and replace this comment with:
![Sentinel demo](docs/demo.gif) -->

**Automated incident triage: from alert to ranked root-cause commit in ~13 seconds, postmortem drafted in ~14 (measured — see [METRICS.md](METRICS.md)).**

Sentinel intercepts an operational alert, pulls the git diffs around the alert
window, has Claude rank the suspect commits with structured JSON output, matches
the failure signature to runbooks by vector similarity, briefs the team in
Slack, and drafts the postmortem on resolution.

## Quickstart

```bash
git clone https://github.com/Lushenwar/Sentinel.git && cd Sentinel
cp .env.example .env        # set OPENROUTER_API_KEY (and optionally SLACK_WEBHOOK_URL)
docker-compose up           # dashboard :3000, core API :8000, sandbox app :8001, Postgres :5432

# trigger an incident (in another terminal)
docker-compose exec core python -m sandbox.chaos_cli trigger-bug --type db_failure
# watch it triage at http://localhost:3000, then resolve it:
docker-compose exec core python -m sandbox.chaos_cli resolve-bug --incident <incident_id>
```

<details>
<summary>Running without Docker</summary>

```bash
pip install -e core/
cp .env.example .env                        # fill in DATABASE_URL, OPENROUTER_API_KEY
uvicorn core.main:app --port 8000           # terminal 1: core engine
uvicorn sandbox.app.main:app --port 8001    # terminal 2: sandbox toy app
python -m sandbox.chaos_cli trigger-bug --type db_failure
python -m sandbox.load_generator --tps 10 --duration 60   # optional: auto-fires alert on error spike
cd dashboard && npm install && cp .env.local.example .env.local && npm run dev   # terminal 3
```
</details>

## Architecture

```
                      ┌────────────────────────────────────────┐
                      │        Next.js Frontend Client         │
                      │   (Timeline, Diff Viewer, Postmortems) │
                      └───────────────────▲────────────────────┘
                                          │  REST (3s polling)
┌───────────────────────┐     ┌───────────▼────────────┐     ┌───────────────────────┐
│  Simulation Sandbox   │     │   Sentinel Core App    │     │ External Integrations │
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

## How it works

1. **Trigger** — `sandbox/chaos_cli.py` commits a real faulty change to the repo
   and fires a mock-Sentry alert at `POST /alert` (or the load generator detects
   the error-rate spike and fires it for you).
2. **Diagnose** — the orchestrator slices the git history around the alert
   timestamp (`git_client`), sends the diffs to Claude through a strict
   tool-call schema that forces ranked, confidence-scored JSON
   (`llm_analyzer`), and matches the error signature against runbook embeddings
   in Chroma (`vector_store`).
3. **Communicate** — a Slack Block Kit diagnostic card posts to your channel:
   top suspect commit, confidence, rationale, matched runbook action
   (`notifier`).
4. **Document** — on `POST /incidents/{id}/resolve`, Claude drafts a structured
   markdown postmortem from the stored timeline, editable in the dashboard
   workspace (`postmortem`).

Every hop reads and writes one auditable incident row conforming to
[`contract/pipeline_schema.json`](contract/pipeline_schema.json).

## Docs

- [METRICS.md](METRICS.md) — measured end-to-end timings, methodology, and per-run results
- [ADR.md](ADR.md) — why explicit state loops over LangChain, polling over WebSockets, Chroma over Pinecone, FastAPI over Flask, tool-call JSON over free-form parsing, sandbox over live infra

## Sandbox reference

| Endpoint | Description |
|---|---|
| `GET /health` | Always 200, shows active bug |
| `GET /api/data` | Returns data; fails with db_failure bug |
| `POST /api/process` | Processes body; fails with null_pointer bug |

```bash
python -m sandbox.chaos_cli trigger-bug [--type db_failure|memory_leak|null_pointer]
python -m sandbox.chaos_cli resolve-bug [--incident inc_...]   # generates postmortem when --incident given
python -m sandbox.chaos_cli status
```
