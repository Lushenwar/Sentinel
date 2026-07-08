import json
import os
from datetime import datetime, timezone
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI(title="Sentinel Sandbox App")
CONFIG = os.path.join(os.path.dirname(__file__), "config.json")


def _bug() -> str | None:
    try:
        return json.load(open(CONFIG)).get("bug")
    except Exception:
        return None


@app.get("/health")
def health():
    return {"status": "ok", "bug": _bug(), "ts": datetime.now(timezone.utc).isoformat()}


@app.get("/api/data")
def get_data():
    bug = _bug()
    if bug == "db_failure":
        raise RuntimeError("OperationalError: connection to server at '127.0.0.1' failed: Connection refused")
    if bug == "memory_leak":
        _ = [0] * 10_000_000  # bloat that accumulates across requests
    return {"data": list(range(100)), "count": 100}


@app.post("/api/process")
def process(body: dict):
    if _bug() == "null_pointer":
        raise AttributeError("'NoneType' object has no attribute 'encode'")
    return {"processed": True, "input_keys": list(body.keys())}


@app.exception_handler(Exception)
async def catch_all(request: Request, exc: Exception):
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "level": "ERROR",
        "message": str(exc),
        "endpoint": request.url.path,
        "traceback": repr(exc),
    }
    print(json.dumps(entry))
    return JSONResponse(status_code=500, content={"error": str(exc)})
