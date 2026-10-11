import hashlib
import hmac
import json
import os
import threading
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from starlette.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from . import db, orchestrator
from .services import vector_store, git_client

# Shared secret for alert senders. Unset = unsigned alerts accepted, with a startup warning (local dev).
_ALERT_SECRET = os.getenv("SENTINEL_ALERT_SECRET", "")


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_schema()
    n = vector_store.ingest_runbooks(orchestrator.RUNBOOKS_DIR)
    print(f"[core] runbooks ingested: {n}")
    if not _ALERT_SECRET:
        print("[core] WARNING: SENTINEL_ALERT_SECRET unset, /alert accepts unsigned alerts (dev only)")
    # off the startup path: re-triage can take ~15s per orphaned incident
    threading.Thread(target=orchestrator.recover_stuck_incidents, daemon=True).start()
    yield


app = FastAPI(title="Sentinel Core", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    # set-but-empty (as in .env.example) must not mean "no origins"
    allow_origins=(os.getenv("SENTINEL_CORS_ORIGINS") or "http://localhost:3000").split(","),
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["*"],
)


def signature_ok(body: bytes, header: str | None, secret: str) -> bool:
    """X-Sentinel-Signature: sha256=<hex HMAC-SHA256 of the raw body>, the scheme GitHub and Sentry use."""
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header or "")


@app.post("/alert")
async def receive_alert(request: Request, background_tasks: BackgroundTasks) -> dict:
    body = await request.body()
    if _ALERT_SECRET and not signature_ok(body, request.headers.get("x-sentinel-signature"), _ALERT_SECRET):
        raise HTTPException(401, "bad or missing X-Sentinel-Signature")
    try:
        payload = json.loads(body)
    except ValueError:
        raise HTTPException(400, "body must be JSON")
    if not isinstance(payload, dict):
        raise HTTPException(400, "body must be a JSON object")
    incident = await run_in_threadpool(orchestrator.handle_alert, payload)  # blocking DB call
    if not incident.get("suppressed"):
        background_tasks.add_task(orchestrator.run_diagnostics, incident["incident_id"], payload)
    return incident


@app.get("/incidents")
def list_incidents() -> list:
    return db.list_incidents()


@app.get("/incidents/{incident_id}")
def get_incident(incident_id: str) -> dict:
    inc = db.get_incident(incident_id)
    if not inc:
        raise HTTPException(404, "incident not found")
    return inc


@app.post("/incidents/{incident_id}/resolve")
def resolve_incident(incident_id: str, background_tasks: BackgroundTasks) -> dict:
    inc = db.get_incident(incident_id)
    if not inc:
        raise HTTPException(404, "incident not found")
    background_tasks.add_task(orchestrator.resolve_incident, incident_id)
    return {**inc, "status": "resolving"}


@app.patch("/incidents/{incident_id}/postmortem")
def save_postmortem(incident_id: str, payload: dict) -> dict:
    if "postmortem" not in payload:
        raise HTTPException(400, "postmortem field required")
    inc = db.get_incident(incident_id)
    if not inc:
        raise HTTPException(404, "incident not found")
    db.update_postmortem(incident_id, payload["postmortem"])
    return db.get_incident(incident_id)


@app.get("/incidents/{incident_id}/commits/{commit_hash}/diff")
def get_commit_diff(incident_id: str, commit_hash: str) -> dict:
    diff = git_client.get_commit_diff(orchestrator.REPO_PATH, commit_hash)
    if not diff:
        raise HTTPException(404, "commit not found")
    return {"commit_hash": commit_hash, "diff": diff}
