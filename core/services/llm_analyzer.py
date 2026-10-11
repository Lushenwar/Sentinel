import os
import re

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


# ponytail: keep the newest frames only; recursion traces run to thousands of lines
_TRACEBACK_MAX_CHARS = 4000


def _traceback_block(traceback: str | None) -> str:
    """'' without a traceback, so an alert that carries none ranks with the baseline prompt."""
    if not traceback:
        return ""
    return (
        "STACK TRACE (from the alert; frames show where the error surfaced, which is not necessarily "
        "where it was introduced):\n"
        f"<traceback>\n{traceback[-_TRACEBACK_MAX_CHARS:]}\n</traceback>\n\n"
    )


def files_in_traceback(commit_files: list[str], traceback: str | None) -> list[str]:
    """Commit files that appear as a frame in the traceback. Frames carry deploy paths
    (/srv/app/x.py), commits carry repo paths (x.py), so match on a path-segment suffix."""
    frames = {p.replace("\\", "/") for p in re.findall(r'File "([^"]+)", line \d+', traceback or "")}
    return [f for f in commit_files if any(p == f or p.endswith("/" + f) for p in frames)]


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

    traceback = alert.get("traceback")

    def _overlap_line(c: dict) -> str:
        hits = files_in_traceback(c.get("files", []), traceback)
        return f"Touches files in the stack trace: {', '.join(hits)}\n" if hits else ""

    commits_block = "\n\n".join(
        f"COMMIT {c['commit_hash']} | {c['author']} | {c['timestamp']}\n"
        f"Subject: {c['subject']}\n"
        f"{_overlap_line(c)}"
        f"Diff:\n{c['diff']}"
        for c in diffs
    )

    prompt = (
        f"You are an incident triage engine.\n\n"
        f"ALERT:\n"
        f"  name: {alert['alert_name']}\n"
        f"  error: {alert['error_signature']}\n"
        f"  time: {alert['timestamp']}\n\n"
        f"{_traceback_block(traceback)}"
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
