import json
from .openrouter import chat

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
                            "commit_hash":      {"type": "string"},
                            "author":           {"type": "string"},
                            "timestamp":        {"type": "string"},
                            "rationale":        {"type": "string"},
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

    response = chat(
        messages=[{"role": "user", "content": prompt}],
        tools=[_RANK_TOOL],
        tool_choice={"type": "function", "function": {"name": "rank_commits"}},
        max_tokens=1024,
    )

    message = response["choices"][0]["message"]
    for call in message.get("tool_calls") or []:
        if call["function"]["name"] == "rank_commits":
            ranked = json.loads(call["function"]["arguments"])["ranked_commits"]
            return sorted(ranked, key=lambda c: c["confidence_score"], reverse=True)

    return []
