from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, BackgroundTasks
from . import db, orchestrator
from .services import vector_store

@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_schema()
    n = vector_store.ingest_runbooks(orchestrator.RUNBOOKS_DIR)
    print(f"[core] runbooks ingested: {n}")
    yield

app = FastAPI(title="Sentinel Core", lifespan=lifespan)

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
