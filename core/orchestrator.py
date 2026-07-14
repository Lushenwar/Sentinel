import os
import time
from collections import defaultdict
from datetime import datetime, timezone
from . import db
from .services import git_client, llm_analyzer, vector_store, notifier, postmortem

REPO_PATH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # Sentinel root
RUNBOOKS_DIR = os.path.join(REPO_PATH, "sandbox", "runbooks")

# ponytail: in-process sliding-window dedup; per-worker, resets on restart.
# Move to Postgres/Redis if you run multiple workers or need durability.
_DEDUP_WINDOW_S = float(os.getenv("SENTINEL_DEDUP_WINDOW_S", "300"))
_DEDUP_THRESHOLD = int(os.getenv("SENTINEL_DEDUP_THRESHOLD", "1"))  # Nth hit in window fires
_recent_alerts: dict[str, list[float]] = defaultdict(list)  # signature -> hit times
_open_signatures: dict[str, str] = {}  # signature -> live incident_id


def _dedup_gate(signature: str) -> tuple[str, str | None]:
    """'fire' (open a new incident), 'duplicate' (fold into an active one),
    or 'suppress' (below the burst threshold)."""
    now = time.monotonic()
    hits = _recent_alerts[signature]
    hits[:] = [t for t in hits if t >= now - _DEDUP_WINDOW_S]
    hits.append(now)

    if signature in _open_signatures:
        return "duplicate", _open_signatures[signature]
    if len(hits) < _DEDUP_THRESHOLD:
        return "suppress", None
    return "fire", None


def _clear_signature(signature: str):
    _open_signatures.pop(signature, None)


def handle_alert(alert_data: dict) -> dict:
    signature = alert_data.get("error_signature", "")
    decision, existing_id = _dedup_gate(signature)
    if decision == "duplicate":
        print(f"[dedup] alert folded into active incident {existing_id}")
        return {"incident_id": existing_id, "status": "duplicate", "suppressed": True}
    if decision == "suppress":
        seen = len(_recent_alerts[signature])
        print(f"[dedup] alert suppressed ({seen}/{_DEDUP_THRESHOLD} in {int(_DEDUP_WINDOW_S)}s window)")
        return {"incident_id": None, "status": "suppressed", "suppressed": True}

    ts = datetime.now(timezone.utc).strftime("%Y_%m%d_%H%M%S")
    incident = {
        "incident_id": f"inc_{ts}_{os.urandom(2).hex()}",  # suffix: same-second alerts must not collide on PK
        "status": "triggered",
        "trigger": alert_data,
        "diagnostics": None,
        "postmortem_draft_url": None,
    }
    db.save_incident(incident)
    _open_signatures[signature] = incident["incident_id"]
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
            _clear_signature(alert_data.get("error_signature", ""))  # terminal: stop folding new alerts
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
        _clear_signature(alert_data.get("error_signature", ""))  # allow a retry alert through


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
    _clear_signature(
        (incident.get("trigger_data") or {}).get("error_signature", "")
    )  # resolved: reopen to new alerts
    print(f"[orchestrator] {incident_id} -> resolved, postmortem generated")
    print(f"[metrics] {incident_id} resolve_to_postmortem_s={time.monotonic() - t0:.1f}")
    return db.get_incident(incident_id)
