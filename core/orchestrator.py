import os
import time
from collections import defaultdict
from datetime import datetime, timezone
from . import db
from .services import git_client, llm_analyzer, vector_store, notifier, postmortem

REPO_PATH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # Sentinel root
RUNBOOKS_DIR = os.path.join(REPO_PATH, "sandbox", "runbooks")

# Open-incident dedup lives in Postgres (a partial unique index on signature). Only the optional burst
# threshold is in memory. ponytail: per-worker, resets on restart; it is off at the default threshold of 1.
_DEDUP_WINDOW_S = float(os.getenv("SENTINEL_DEDUP_WINDOW_S", "300"))
_DEDUP_THRESHOLD = int(os.getenv("SENTINEL_DEDUP_THRESHOLD", "1"))  # Nth hit in window fires
_recent_alerts: dict[str, list[float]] = defaultdict(list)  # signature -> hit times
# Pass matched runbook text into commit ranking. Off: Phase 9 A/B found no measurable benefit (ADR-7).
_RAG_RANKING = os.getenv("SENTINEL_RAG_RANKING", "0") == "1"
# Triage takes ~15s; an open incident with no diagnostics this old was orphaned by a dead process.
STUCK_AFTER_S = float(os.getenv("SENTINEL_STUCK_AFTER_S", "300"))


def _below_burst_threshold(signature: str) -> bool:
    now = time.monotonic()
    hits = _recent_alerts[signature]
    hits[:] = [t for t in hits if t >= now - _DEDUP_WINDOW_S]
    hits.append(now)
    return len(hits) < _DEDUP_THRESHOLD


def handle_alert(alert_data: dict) -> dict:
    signature = alert_data.get("error_signature", "")
    if _below_burst_threshold(signature):
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
    incident_id, created = db.open_incident(incident, signature)
    if not created:
        print(f"[dedup] alert folded into active incident {incident_id}")
        return {"incident_id": incident_id, "status": "duplicate", "suppressed": True}
    print(f"[orchestrator] {incident_id} created -> triggered")
    return incident


def recover_stuck_incidents() -> list[str]:
    """Re-run triage for incidents orphaned mid-triage (crash, restart). Call once at startup."""
    stuck = db.stuck_incidents(STUCK_AFTER_S)
    for inc in stuck:
        print(f"[orchestrator] {inc['id']} orphaned mid-triage -> re-running diagnostics")
        run_diagnostics(inc["id"], inc["trigger_data"])
    return [inc["id"] for inc in stuck]


def run_diagnostics(incident_id: str, alert_data: dict):
    """Runs in a background task after the alert response is sent."""
    print(f"[orchestrator] {incident_id} -> triaging")
    db.update_status(incident_id, "triaging")

    try:
        diffs = git_client.get_recent_diffs(REPO_PATH, alert_data["timestamp"])
        print(f"[orchestrator] {incident_id} -- {len(diffs)} commits in window")

        try:
            runbooks = vector_store.find_matching_runbooks(
                alert_data.get("error_signature", ""), include_content=_RAG_RANKING
            )
            print(f"[orchestrator] {incident_id} -- {len(runbooks)} runbooks matched")
        except Exception as e:  # retrieval is optional context; never a reason to abort triage
            runbooks = []
            print(f"[orchestrator] {incident_id} -- runbook retrieval failed, ranking without: {e}")

        degraded_reason = None
        try:
            rank_runbooks = runbooks if _RAG_RANKING else None
            ranked = (
                llm_analyzer.rank_suspect_commits(diffs, alert_data, runbooks=rank_runbooks) if diffs else []
            )
            print(f"[orchestrator] {incident_id} -- LLM ranked {len(ranked)} suspects")
        except llm_analyzer.LLMUnavailable as e:
            ranked, degraded_reason = [], str(e)
            print(f"[orchestrator] {incident_id} -- LLM unavailable, degrading: {e}")

        diagnostics = {
            "suspect_commits": ranked,
            # runbook text is prompt-only; never persisted or sent to Slack
            "matched_runbooks": [{k: v for k, v in r.items() if k != "content"} for r in runbooks],
            # no affected-user estimate: nothing upstream reports user ids, and the dashboard
            # renders no fabricated figures
            "impact_assessment": {"error_rate_delta_pct": alert_data.get("error_rate_pct")},
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
            db.update_status(incident_id, "degraded")  # terminal: leaves the open set, new alerts open anew
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
        try:  # terminal and visible, rather than an incident left open with nothing in it
            reason = f"Diagnostics failed — manual investigation required ({e})"
            db.update_diagnostics(
                incident_id,
                {"suspect_commits": [], "matched_runbooks": [], "degraded": True, "degraded_reason": reason},
            )
            db.update_status(incident_id, "degraded")
        except Exception as e2:  # db down too: the row stays open and empty; startup recovery retries it
            print(f"[orchestrator] {incident_id} could not record the failure ({e2}); left for recovery")


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
    db.update_postmortem(incident_id, draft)  # status -> resolved: leaves the open set
    print(f"[orchestrator] {incident_id} -> resolved, postmortem generated")
    print(f"[metrics] {incident_id} resolve_to_postmortem_s={time.monotonic() - t0:.1f}")
    return db.get_incident(incident_id)
