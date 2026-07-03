# ponytail: mocks httpx/anthropic so tests run without live webhook or API key
from unittest.mock import patch, MagicMock
from core.services.notifier import build_incident_card, post_incident_to_slack
from core.services.postmortem import generate_postmortem

_INCIDENT = {
    "id": "inc_2026_0703_a",
    "status": "triaging",
    "trigger_data": {
        "alert_name": "HTTP_500_Internal_Server_Error",
        "timestamp": "2026-07-03T11:29:04Z",
        "error_signature": "OperationalError: connection refused",
    },
    "diagnostics": {
        "suspect_commits": [
            {"commit_hash": "a1b2c3d", "confidence_score": 0.92, "rationale": "Broke db pool config."}
        ],
        "matched_runbooks": [
            {"title": "Database Connection Pool Exhaustion", "primary_action": "Check pool limits."}
        ],
        "impact_assessment": {"error_rate_delta_pct": 340.5, "estimated_affected_users": 142},
    },
}

def test_build_incident_card_includes_error_and_top_suspect():
    card = build_incident_card(_INCIDENT)
    text = str(card)
    assert "OperationalError" in text
    assert "a1b2c3d" in text
    assert "Database Connection Pool Exhaustion" in text

def test_post_incident_to_slack_skips_without_webhook_url():
    with patch("core.services.notifier.SLACK_WEBHOOK_URL", None):
        assert post_incident_to_slack(_INCIDENT) is False

def test_post_incident_to_slack_posts_when_configured():
    with patch("core.services.notifier.SLACK_WEBHOOK_URL", "https://hooks.slack.com/x"), \
         patch("core.services.notifier.httpx.post") as mock_post:
        mock_post.return_value = MagicMock(raise_for_status=lambda: None)
        assert post_incident_to_slack(_INCIDENT) is True
        mock_post.assert_called_once()

def test_generate_postmortem_returns_llm_text():
    fake_block = MagicMock(type="text", text="## Summary\nDB pool misconfigured.")
    fake_response = MagicMock(content=[fake_block])
    with patch("core.services.postmortem._client") as mock_client:
        mock_client.messages.create.return_value = fake_response
        result = generate_postmortem(_INCIDENT)
    assert "Summary" in result

if __name__ == "__main__":
    test_build_incident_card_includes_error_and_top_suspect()
    test_post_incident_to_slack_skips_without_webhook_url()
    test_post_incident_to_slack_posts_when_configured()
    test_generate_postmortem_returns_llm_text()
    print("✓ phase3 tests passed")
