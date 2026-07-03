# ponytail: mocks db so test runs without a live postgres connection
from unittest.mock import patch
from core.orchestrator import handle_alert

_ALERT = {
    "source": "mock_sentry",
    "alert_name": "HTTP_500_Internal_Server_Error",
    "timestamp": "2026-07-03T00:00:00Z",
    "error_signature": "OperationalError: connection refused",
}

def test_handle_alert():
    with patch("core.orchestrator.db.save_incident") as mock_save:
        result = handle_alert(_ALERT)
    assert result["status"] == "triggered"
    assert result["incident_id"].startswith("inc_")
    assert result["trigger"] == _ALERT
    assert result["diagnostics"] is None
    mock_save.assert_called_once()

if __name__ == "__main__":
    test_handle_alert()
    print("✓ orchestrator test passed")
