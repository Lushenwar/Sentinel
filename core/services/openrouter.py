import os
import httpx
from dotenv import load_dotenv

load_dotenv()
API_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "anthropic/claude-sonnet-5"


def chat(
    messages: list[dict],
    tools: list[dict] | None = None,
    tool_choice: dict | None = None,
    max_tokens: int = 1024,
) -> dict:
    payload = {"model": MODEL, "messages": messages, "max_tokens": max_tokens}
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = tool_choice
    response = httpx.post(
        API_URL,
        headers={"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"},
        json=payload,
        timeout=60.0,
    )
    response.raise_for_status()
    return response.json()
