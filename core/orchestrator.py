from datetime import datetime, timezone
from . import db

def handle_alert(alert_data: dict) -> dict:
    ts = datetime.now(timezone.utc).strftime("%Y_%m%d_%H%M%S")
    incident = {
        "incident_id": f"inc_{ts}",
        "status": "triggered",
        "trigger": alert_data,
        "diagnostics": None,
        "postmortem_draft_url": None,
    }
    db.save_incident(incident)
    print(f"[orchestrator] {incident['incident_id']} created → status=triggered")
    return incident
