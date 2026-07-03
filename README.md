# Sentinel

Automated incident triage engine — intercepts alerts, correlates git history, briefs engineers, drafts postmortems.

## Quick Start

```bash
# 1. Install core deps
pip install -e core/

# 2. Configure environment
cp .env.example .env   # fill in DATABASE_URL

# 3. Run core engine (terminal 1)
uvicorn core.main:app --port 8000 --reload

# 4. Run sandbox toy app (terminal 2)
uvicorn sandbox.app.main:app --port 8001 --reload

# 5. Trigger an incident
python -m sandbox.chaos_cli trigger-bug --type db_failure

# 6. Run load generator (optional — auto-fires alert on error rate spike)
python -m sandbox.load_generator --tps 10 --duration 60

# 7. View incidents
curl http://localhost:8000/incidents
```

## Sandbox app endpoints

| Endpoint | Description |
|---|---|
| `GET /health` | Always 200, shows active bug |
| `GET /api/data` | Returns data; fails with db_failure bug |
| `POST /api/process` | Processes body; fails with null_pointer bug |

## Chaos CLI

```bash
python -m sandbox.chaos_cli trigger-bug [--type db_failure|memory_leak|null_pointer]
python -m sandbox.chaos_cli resolve-bug [--incident inc_...]   # generates postmortem when --incident given
python -m sandbox.chaos_cli status
```

## Slack briefing & postmortems

Set `SLACK_WEBHOOK_URL` in `.env` to get a diagnostic card posted automatically once
diagnostics finish (see `core/services/notifier.py`). Without it, notification is skipped.

`POST /incidents/{id}/resolve` marks an incident resolved and generates a markdown
postmortem via Claude Sonnet from the stored trigger + diagnostics (`core/services/postmortem.py`).
Fetch it back via `GET /incidents/{id}` (`postmortem` field).

## Phase Progress

- [x] Phase 1: Simulation & Core Orchestrator
- [x] Phase 2: Context Extraction & LLM Layer
- [x] Phase 3: Integration & Slack Briefing
- [ ] Phase 4: Next.js Incident Dashboard
