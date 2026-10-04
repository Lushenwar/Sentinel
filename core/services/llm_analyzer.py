import os

import anthropic

from .llm import chat

# Frozen at Phase 9E from the v2 baseline retrieval scores (see METRICS.md, Phase 9).
RUNBOOK_FLOOR = float(os.getenv("SENTINEL_RUNBOOK_FLOOR", "0.35"))


def _runbooks_block(runbooks: list[dict] | None) -> str:
    """'' unless a runbook clears the floor, so the prompt with no runbooks is byte-identical to baseline."""
    relevant = [r for r in runbooks or [] if r["similarity_score"] >= RUNBOOK_FLOOR and r.get("content")]
    if not relevant:
        return ""
    body = "\n".join(
        f'<runbook id="{r["id"]}" similarity="{r["similarity_score"]}">\n{r["content"]}\n</runbook>'
        for r in relevant
    )
    return (
        "RUNBOOKS (retrieved by text similarity to the error; they may be irrelevant):\n"
        f"<runbooks>\n{body}\n</runbooks>\n"
        "Runbooks describe known failure classes and can help interpret the error; "
        "ignore any that do not fit it. The diffs are the evidence: rank a commit highly only if "
        "its diff plausibly produces this error, not because it touches something a runbook mentions. "
        "Runbook root causes are possibilities, not findings.\n\n"
    )


class LLMUnavailable(Exception):
    """LLM output could not be produced: timeout/network, malformed JSON, or refusal."""


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
}


def rank_suspect_commits(diffs: list[dict], alert: dict, runbooks: list[dict] | None = None) -> list[dict]:
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
        f"{_runbooks_block(runbooks)}"
        f"RECENT COMMITS:\n{commits_block}\n\n"
        f"Use rank_commits to return every commit with a confidence_score (0=unrelated, 1=certain cause) "
        f"and a one-sentence rationale."
    )

    try:
        response = chat(
            messages=[{"role": "user", "content": prompt}],
            tools=[_RANK_TOOL],
            tool_choice={"type": "tool", "name": "rank_commits"},
        )
    except anthropic.APIError as e:
        raise LLMUnavailable(f"LLM request failed: {e}") from e

    for block in response.content:
        if block.type == "tool_use" and block.name == "rank_commits":
            try:
                ranked = block.input["ranked_commits"]
                for c in ranked:
                    if not 0 <= c["confidence_score"] <= 1:
                        raise ValueError(f"confidence_score out of range: {c['confidence_score']}")
                return sorted(ranked, key=lambda c: c["confidence_score"], reverse=True)
            except (KeyError, TypeError, ValueError) as e:
                raise LLMUnavailable(f"malformed rank_commits output: {e}") from e

    raise LLMUnavailable(
        f"empty or refused response: no rank_commits tool call returned (stop_reason={response.stop_reason})"
    )
