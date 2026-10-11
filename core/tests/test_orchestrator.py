# ponytail: mocks db so test runs without a live postgres connection (the SQL itself: test_db_integration.py)
from unittest.mock import patch
import core.orchestrator as orch
from core.orchestrator import handle_alert

_ALERT = {
    "source": "mock_sentry",
    "alert_name": "HTTP_500_Internal_Server_Error",
    "timestamp": "2026-07-03T00:00:00Z",
    "error_signature": "OperationalError: connection refused",
}


def _created(incident, _signature):
    return incident["incident_id"], True


def test_handle_alert():
    orch._recent_alerts.clear()
    with patch("core.orchestrator.db.open_incident", side_effect=_created) as mock_open:
        result = handle_alert(_ALERT)
    assert result["status"] == "triggered"
    assert result["incident_id"].startswith("inc_")
    assert result["trigger"] == _ALERT
    assert result["diagnostics"] is None
    mock_open.assert_called_once_with(result, _ALERT["error_signature"])


def test_open_incident_conflict_folds_alert_into_it():
    orch._recent_alerts.clear()
    with patch("core.orchestrator.db.open_incident", return_value=("inc_existing", False)):
        result = handle_alert(_ALERT)
    assert result == {"incident_id": "inc_existing", "status": "duplicate", "suppressed": True}


def test_dedup_threshold_suppresses_below_burst():
    """With a threshold >1, alerts below the burst count are suppressed, not opened."""
    orch._recent_alerts.clear()
    with (
        patch.object(orch, "_DEDUP_THRESHOLD", 3),
        patch("core.orchestrator.db.open_incident", side_effect=_created) as mock_open,
    ):
        r1 = handle_alert(_ALERT)
        r2 = handle_alert(_ALERT)
        r3 = handle_alert(_ALERT)
    assert r1["status"] == "suppressed"
    assert r2["status"] == "suppressed"
    assert r3["status"] == "triggered"  # 3rd hit crosses the threshold
    mock_open.assert_called_once()


def test_failed_diagnostics_end_degraded_not_open():
    with (
        patch("core.orchestrator.db") as db,
        patch("core.orchestrator.git_client.get_recent_diffs", side_effect=OSError("git missing")),
    ):
        orch.run_diagnostics("inc_x", _ALERT)
    diag = db.update_diagnostics.call_args.args[1]
    assert diag["degraded"] and "git missing" in diag["degraded_reason"]
    assert db.update_status.call_args_list[-1].args == ("inc_x", "degraded")


def test_failure_with_db_down_leaves_row_for_recovery():
    with (
        patch("core.orchestrator.db") as db,
        patch("core.orchestrator.git_client.get_recent_diffs", side_effect=OSError("git missing")),
    ):
        db.update_diagnostics.side_effect = ConnectionError("db down")
        orch.run_diagnostics("inc_x", _ALERT)  # must not raise
    assert ("inc_x", "degraded") not in [c.args for c in db.update_status.call_args_list]


def test_recover_reruns_triage_for_each_stuck_incident():
    stuck = [{"id": "inc_a", "trigger_data": _ALERT}, {"id": "inc_b", "trigger_data": _ALERT}]
    with (
        patch("core.orchestrator.db.stuck_incidents", return_value=stuck) as q,
        patch.object(orch, "run_diagnostics") as run,
    ):
        assert orch.recover_stuck_incidents() == ["inc_a", "inc_b"]
    q.assert_called_once_with(orch.STUCK_AFTER_S)
    assert [c.args for c in run.call_args_list] == [("inc_a", _ALERT), ("inc_b", _ALERT)]
