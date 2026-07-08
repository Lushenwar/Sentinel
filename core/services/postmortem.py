import httpx
from .openrouter import chat
from .llm_analyzer import LLMUnavailable


def generate_postmortem(incident: dict) -> str:
    """incident is a db row: {id, status, trigger_data, diagnostics, ...}"""
    trigger = incident["trigger_data"]
    diagnostics = incident.get("diagnostics") or {}

    prompt = (
        f"Write a concise incident postmortem in markdown for a peer engineering team.\n\n"
        f"INCIDENT: {incident['id']}\n"
        f"ALERT: {trigger['alert_name']}\n"
        f"ERROR: {trigger['error_signature']}\n"
        f"TRIGGERED AT: {trigger['timestamp']}\n\n"
        f"SUSPECT COMMITS (ranked):\n{diagnostics.get('suspect_commits')}\n\n"
        f"MATCHED RUNBOOKS:\n{diagnostics.get('matched_runbooks')}\n\n"
        f"IMPACT: {diagnostics.get('impact_assessment')}\n\n"
        f"Use these section headers: Summary, Root Cause, Impact, Resolution, Action Items. "
        f"Base every claim strictly on the data given above — do not invent details."
    )

    try:
        response = chat(messages=[{"role": "user", "content": prompt}], max_tokens=1024)
        content = response["choices"][0]["message"]["content"]
    except httpx.HTTPError as e:
        raise LLMUnavailable(f"LLM request failed: {e}") from e
    except (KeyError, IndexError, TypeError) as e:
        raise LLMUnavailable(f"unexpected LLM response shape: {e}") from e
    if not content:
        raise LLMUnavailable("empty or refused response: no postmortem content returned")
    return content
