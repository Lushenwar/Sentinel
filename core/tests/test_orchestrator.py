# ponytail: mocks db so test runs without a live postgres connection
from unittest.mock import patch
import core.orchestrator as orch
from core.orchestrator import handle_alert

_ALERT = {
    "source": "mock_sentry",
    "alert_name": "HTTP_500_Internal_Server_Error",
    "timestamp": "2026-07-03T00:00:00Z",
    "error_signature": "OperationalError: connection refused",
}


def _reset_dedup():
    orch._recent_alerts.clear()
    orch._open_signatures.clear()


def test_handle_alert():
    _reset_dedup()
    with patch("core.orchestrator.db.save_incident") as mock_save:
        result = handle_alert(_ALERT)
    assert result["status"] == "triggered"
    assert result["incident_id"].startswith("inc_")
    assert result["trigger"] == _ALERT
    assert result["diagnostics"] is None
    mock_save.assert_called_once()


def test_dedup_folds_repeat_alerts():
    """Second alert for a still-open signature must not open a new incident."""
    _reset_dedup()
    with patch("core.orchestrator.db.save_incident") as mock_save:
        first = handle_alert(_ALERT)
        second = handle_alert(_ALERT)
    assert first["status"] == "triggered"
    assert second["status"] == "duplicate"
    assert second["incident_id"] == first["incident_id"]
    mock_save.assert_called_once()  # only the first alert hit the DB

    # once the incident is cleared (resolved/degraded/failed), a new alert fires again
    orch._clear_signature(_ALERT["error_signature"])
    with patch("core.orchestrator.db.save_incident"):
        third = handle_alert(_ALERT)
    assert third["status"] == "triggered"
    assert third["incident_id"] != first["incident_id"]


def test_dedup_threshold_suppresses_below_burst():
    """With a threshold >1, alerts below the burst count are suppressed, not opened."""
    _reset_dedup()
    with patch.object(orch, "_DEDUP_THRESHOLD", 3), patch("core.orchestrator.db.save_incident") as mock_save:
        r1 = handle_alert(_ALERT)
        r2 = handle_alert(_ALERT)
        r3 = handle_alert(_ALERT)
    assert r1["status"] == "suppressed"
    assert r2["status"] == "suppressed"
    assert r3["status"] == "triggered"  # 3rd hit crosses the threshold
    mock_save.assert_called_once()


if __name__ == "__main__":
    test_handle_alert()
    test_dedup_folds_repeat_alerts()
    test_dedup_threshold_suppresses_below_burst()
    print("[ok] orchestrator + dedup tests passed")
