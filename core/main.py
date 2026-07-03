from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from . import db, orchestrator

@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_schema()
    yield

app = FastAPI(title="Sentinel Core", lifespan=lifespan)

@app.post("/alert")
def receive_alert(payload: dict) -> dict:
    return orchestrator.handle_alert(payload)

@app.get("/incidents")
def list_incidents() -> list:
    return db.list_incidents()

@app.get("/incidents/{incident_id}")
def get_incident(incident_id: str) -> dict:
    inc = db.get_incident(incident_id)
    if not inc:
        raise HTTPException(404, "incident not found")
    return inc
