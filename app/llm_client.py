"""Client for the OpenAI-compatible llama.cpp server."""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_SYSTEM_PROMPT = (
    "You are a concise, helpful chat bot. Answer naturally and keep replies brief."
)


class LLMClientError(RuntimeError):
    """Raised when the LLM service cannot return a usable response."""


def _chat_completion(prompt: str) -> str:
    base_url = os.getenv("LLM_BASE_URL", "http://llm:8080").rstrip("/")
    timeout = float(os.getenv("LLM_TIMEOUT_SECONDS", "120"))
    model = os.getenv("LLM_MODEL", "local-model")
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": DEFAULT_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.7,
        "max_tokens": 256,
    }
    request = Request(
        f"{base_url}/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlopen(request, timeout=timeout) as response:
            data: dict[str, Any] = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise LLMClientError(f"LLM server returned HTTP {exc.code}: {detail}") from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise LLMClientError(f"Could not reach LLM server: {exc}") from exc

    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMClientError(f"Unexpected LLM response: {data}") from exc

    reply = str(content).strip()
    if not reply:
        raise LLMClientError("LLM server returned an empty response")
    return reply


async def generate_reply(prompt: str) -> str:
    return await asyncio.to_thread(_chat_completion, prompt)
