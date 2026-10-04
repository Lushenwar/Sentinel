from functools import cache

import anthropic
from dotenv import load_dotenv

load_dotenv()
MODEL = "claude-sonnet-5"


@cache
def _client() -> anthropic.Anthropic:
    return anthropic.Anthropic()  # ANTHROPIC_API_KEY from env / .env


def chat(
    messages: list[dict],
    tools: list[dict] | None = None,
    tool_choice: dict | None = None,
    max_tokens: int = 16000,
) -> anthropic.types.Message:
    """One Messages API call. Raises anthropic.APIError on transport or API failure."""
    extra = {"tools": tools, "tool_choice": tool_choice} if tools else {}
    return _client().messages.create(model=MODEL, max_tokens=max_tokens, messages=messages, **extra)
