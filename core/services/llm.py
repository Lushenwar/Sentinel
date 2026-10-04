import os
from functools import cache

import anthropic
from dotenv import load_dotenv

load_dotenv()
MODEL = "claude-sonnet-5"


@cache
def _client() -> anthropic.Anthropic:
    # ANTHROPIC_API_KEY from env / .env; org-level keys also need the workspace header
    workspace = os.getenv("ANTHROPIC_WORKSPACE_ID")
    return anthropic.Anthropic(default_headers={"anthropic-workspace-id": workspace} if workspace else None)


def chat(
    messages: list[dict],
    tools: list[dict] | None = None,
    tool_choice: dict | None = None,
    max_tokens: int = 16000,
) -> anthropic.types.Message:
    """One Messages API call. Raises anthropic.APIError on transport or API failure."""
    extra = {"tools": tools, "tool_choice": tool_choice} if tools else {}
    return _client().messages.create(model=MODEL, max_tokens=max_tokens, messages=messages, **extra)
