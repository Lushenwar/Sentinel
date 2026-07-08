import json
import httpx
from .openrouter import chat


class LLMUnavailable(Exception):
    """LLM output could not be produced: timeout/network, malformed JSON, or refusal."""


_RANK_TOOL = {
    "type": "function",
    "function": {
        "name": "rank_commits",
        "description": "Rank commits by likelihood of causing the incident. Include ALL commits, scored 0-1.",
        "parameters": {
            "type": "object",
            "required": ["ranked_commits"],
            "properties": {
                "ranked_commits": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["commit_hash", "author", "timestamp", "rationale", "confidence_score"],
                        "properties": {
                            "commit_hash": {"type": "string"},
                            "author": {"type": "string"},
                            "timestamp": {"type": "string"},
                            "rationale": {"type": "string"},
                            "confidence_score": {"type": "number", "minimum": 0, "maximum": 1},
                        },
                    },
                }
            },
        },
    },
}


def rank_suspect_commits(diffs: list[dict], alert: dict) -> list[dict]:
    if not diffs:
        return []

    commits_block = "\n\n".join(
        f"COMMIT {c['commit_hash']} | {c['author']} | {c['timestamp']}\n"
        f"Subject: {c['subject']}\n"
        f"Diff:\n{c['diff']}"
        for c in diffs
    )

    prompt = (
        f"You are an incident triage engine.\n\n"
        f"ALERT:\n"
        f"  name: {alert['alert_name']}\n"
        f"  error: {alert['error_signature']}\n"
        f"  time: {alert['timestamp']}\n\n"
        f"RECENT COMMITS:\n{commits_block}\n\n"
        f"Use rank_commits to return every commit with a confidence_score (0=unrelated, 1=certain cause) "
        f"and a one-sentence rationale."
    )

    try:
        response = chat(
            messages=[{"role": "user", "content": prompt}],
            tools=[_RANK_TOOL],
            tool_choice={"type": "function", "function": {"name": "rank_commits"}},
            max_tokens=1024,
        )
        message = response["choices"][0]["message"]
    except httpx.HTTPError as e:
        raise LLMUnavailable(f"LLM request failed: {e}") from e
    except (KeyError, IndexError, TypeError) as e:
        raise LLMUnavailable(f"unexpected LLM response shape: {e}") from e

    for call in message.get("tool_calls") or []:
        if call["function"]["name"] == "rank_commits":
            try:
                ranked = json.loads(call["function"]["arguments"])["ranked_commits"]
                for c in ranked:
                    if not 0 <= c["confidence_score"] <= 1:
                        raise ValueError(f"confidence_score out of range: {c['confidence_score']}")
                return sorted(ranked, key=lambda c: c["confidence_score"], reverse=True)
            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
                raise LLMUnavailable(f"malformed rank_commits output: {e}") from e

    raise LLMUnavailable("empty or refused response: no rank_commits tool call returned")
