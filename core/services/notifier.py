import os
import httpx
from dotenv import load_dotenv

load_dotenv()
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL")


def _fmt_commit(c: dict) -> str:
    return f"*{c['commit_hash']}* ({c['confidence_score']:.0%}) — {c['rationale']}"


def _fmt_runbook(r: dict) -> str:
    return f"*{r['title']}* — {r['primary_action']}"


def build_incident_card(incident: dict) -> dict:
    """incident is a db row: {id, status, trigger_data, diagnostics, ...}"""
    trigger = incident["trigger_data"]
    diagnostics = incident.get("diagnostics") or {}
    commits = diagnostics.get("suspect_commits") or []
    runbooks = diagnostics.get("matched_runbooks") or []

    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": f"🚨 {trigger['alert_name']}"}},
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Incident:*\n{incident['id']}"},
                {"type": "mrkdwn", "text": f"*Status:*\n{incident['status']}"},
            ],
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Error:*\n```{trigger['error_signature']}```"},
        },
    ]
    if diagnostics.get("degraded"):
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": ":warning: *"
                    + diagnostics.get(
                        "degraded_reason", "Diagnostic unavailable — manual investigation required"
                    )
                    + "*",
                },
            }
        )
    if commits:
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "*Top suspect commit:*\n" + _fmt_commit(commits[0])},
            }
        )
    if runbooks:
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "*Matched runbook:*\n" + _fmt_runbook(runbooks[0])},
            }
        )
    blocks.append(
        {"type": "context", "elements": [{"type": "mrkdwn", "text": f"Triggered at {trigger['timestamp']}"}]}
    )
    return {"blocks": blocks}


def post_incident_to_slack(incident: dict) -> bool:
    if not SLACK_WEBHOOK_URL:
        print("[notifier] SLACK_WEBHOOK_URL not set — skipping")
        return False
    resp = httpx.post(SLACK_WEBHOOK_URL, json=build_incident_card(incident), timeout=5.0)
    resp.raise_for_status()
    return True
