import os
import time
from datetime import datetime, timezone
from . import db
from .services import git_client, llm_analyzer, vector_store, notifier, postmortem

REPO_PATH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # Sentinel root
RUNBOOKS_DIR = os.path.join(REPO_PATH, "sandbox", "runbooks")


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
    print(f"[orchestrator] {incident['incident_id']} created -> triggered")
    return incident


def run_diagnostics(incident_id: str, alert_data: dict):
    """Runs in a background task after the alert response is sent."""
    print(f"[orchestrator] {incident_id} -> triaging")
    db.update_status(incident_id, "triaging")

    try:
        diffs = git_client.get_recent_diffs(REPO_PATH, alert_data["timestamp"])
        print(f"[orchestrator] {incident_id} -- {len(diffs)} commits in window")

        runbooks = vector_store.find_matching_runbooks(alert_data.get("error_signature", ""))
        print(f"[orchestrator] {incident_id} -- {len(runbooks)} runbooks matched")

        degraded_reason = None
        try:
            ranked = llm_analyzer.rank_suspect_commits(diffs, alert_data) if diffs else []
            print(f"[orchestrator] {incident_id} -- LLM ranked {len(ranked)} suspects")
        except llm_analyzer.LLMUnavailable as e:
            ranked, degraded_reason = [], str(e)
            print(f"[orchestrator] {incident_id} -- LLM unavailable, degrading: {e}")

        diagnostics = {
            "suspect_commits": ranked,
            "matched_runbooks": runbooks,
            "impact_assessment": {
                "error_rate_delta_pct": alert_data.get("error_rate_pct"),
                "estimated_affected_users": None,
            },
        }
        if degraded_reason:
            diagnostics["degraded"] = True
            diagnostics["degraded_reason"] = (
                f"Diagnostic unavailable — manual investigation required ({degraded_reason})"
            )
            # raw material for the manual investigation the flag asks for
            diagnostics["raw_commits"] = diffs

        db.update_diagnostics(incident_id, diagnostics)
        if degraded_reason:
            db.update_status(incident_id, "degraded")
            print(f"[orchestrator] {incident_id} -> degraded (terminal)")
        else:
            alert_dt = datetime.fromisoformat(alert_data["timestamp"].replace("Z", "+00:00"))
            elapsed = (datetime.now(timezone.utc) - alert_dt).total_seconds()
            print(f"[orchestrator] {incident_id} -> diagnostics saved")
            print(f"[metrics] {incident_id} alert_to_suspects_s={elapsed:.1f}")

        try:
            notifier.post_incident_to_slack(db.get_incident(incident_id))
        except Exception as e:
            print(f"[orchestrator] {incident_id} slack notify failed: {e}")

    except Exception as e:
        print(f"[orchestrator] {incident_id} diagnostics failed: {e}")
        db.update_status(incident_id, "triggered")  # revert so it can be retried


def resolve_incident(incident_id: str) -> dict:
    """Runs in a background task once an incident is marked resolved."""
    t0 = time.monotonic()
    incident = db.get_incident(incident_id)
    try:
        draft = postmortem.generate_postmortem(incident)
    except llm_analyzer.LLMUnavailable as e:
        draft = (
            "# Postmortem unavailable\n\n"
            f"Automatic generation failed ({e}). Manual write-up required — "
            "trigger and diagnostics data remain on the incident record."
        )
        print(f"[orchestrator] {incident_id} -- postmortem LLM unavailable, degrading: {e}")
    db.update_postmortem(incident_id, draft)
    print(f"[orchestrator] {incident_id} -> resolved, postmortem generated")
    print(f"[metrics] {incident_id} resolve_to_postmortem_s={time.monotonic() - t0:.1f}")
    return db.get_incident(incident_id)
