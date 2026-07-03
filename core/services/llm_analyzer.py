import os
import anthropic
from dotenv import load_dotenv

load_dotenv()
_client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

_RANK_TOOL = {
    "name": "rank_commits",
    "description": "Rank commits by likelihood of causing the incident. Include ALL commits, scored 0-1.",
    "input_schema": {
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

    response = _client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        tools=[_RANK_TOOL],
        tool_choice={"type": "tool", "name": "rank_commits"},
        messages=[{"role": "user", "content": prompt}],
    )

    for block in response.content:
        if block.type == "tool_use" and block.name == "rank_commits":
            ranked = block.input["ranked_commits"]
            return sorted(ranked, key=lambda c: c["confidence_score"], reverse=True)

    return []
