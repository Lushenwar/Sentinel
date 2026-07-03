from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from . import db, orchestrator
from .services import vector_store, git_client

@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_schema()
    n = vector_store.ingest_runbooks(orchestrator.RUNBOOKS_DIR)
    print(f"[core] runbooks ingested: {n}")
    yield

app = FastAPI(title="Sentinel Core", lifespan=lifespan)

# ponytail: dev-only origin; lock down to the deployed dashboard origin before shipping
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["*"],
)

@app.post("/alert")
def receive_alert(payload: dict, background_tasks: BackgroundTasks) -> dict:
    incident = orchestrator.handle_alert(payload)
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
