import os
import httpx
from dotenv import load_dotenv

load_dotenv()
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL")
# Raw confidence barely separates right from wrong #1 picks (AUC 0.60 on 144 eval trials); the gap to #2
# does (AUC 0.86). ponytail: 0.1 was picked on those same trials (13 wrong picks), re-check as data grows.
CLOSE_CALL_MARGIN = 0.1


def is_close_call(commits: list[dict]) -> bool:
    """Top two suspects within CLOSE_CALL_MARGIN: the #1 pick is not trustworthy on its own."""
    if len(commits) < 2:
        return False
    return round(commits[0]["confidence_score"] - commits[1]["confidence_score"], 2) <= CLOSE_CALL_MARGIN


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
    if commits and is_close_call(commits):
        text = ":scales: *Close call: check both suspects.*\n" + "\n".join(
            f"{i}. " + _fmt_commit(c) for i, c in enumerate(commits[:2], 1)
        )
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": text}})
    elif commits:
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
