"""Chat model providers, beside the trading path (ADR-0005).

Groq (default, Llama 3.3 70B) and a local Ollama are both reached through
their OpenAI-compatible `/chat/completions` endpoints with tool calling, so
one client serves both. The stub needs no key, no network and no model — CI
and tests use it, and it's what the advisor falls back to when a real model
is slow, rate-limited or down: explanations degrade, trading never does.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Protocol

import httpx

from app.core.config import LLMProvider, Settings

Message = dict[str, Any]

_GROQ_BASE_URL = "https://api.groq.com/openai/v1"
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class ChatProviderError(RuntimeError):
    """The model couldn't be reached or answered unusably."""


class ChatProvider(Protocol):
    name: str
    # The model that answers, for display; "" when there is none (the stub).
    model: str

    async def complete(self, messages: list[Message], tools: list[Message]) -> Message:
        """The assistant's next message: text in `content`, and/or
        `tool_calls` it wants run before it answers."""
        ...


class OpenAICompatibleProvider:
    def __init__(
        self,
        *,
        name: str,
        base_url: str,
        model: str,
        api_key: str | None,
        timeout_seconds: float,
        max_retries: int,
    ) -> None:
        self.name = name
        self.model = model
        self._url = f"{base_url.rstrip('/')}/chat/completions"
        self._headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._timeout = timeout_seconds
        self._retries = max_retries

    async def complete(self, messages: list[Message], tools: list[Message]) -> Message:
        payload: Message = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": 600,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        last_error = "no response"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            for attempt in range(self._retries + 1):
                try:
                    response = await client.post(self._url, json=payload, headers=self._headers)
                except httpx.HTTPError as exc:
                    last_error = f"{type(exc).__name__}: {exc}"
                else:
                    if response.status_code == 200:
                        message: Message = response.json()["choices"][0]["message"]
                        return message
                    last_error = f"HTTP {response.status_code}: {response.text[:200]}"
                    if response.status_code not in _RETRYABLE_STATUS:
                        break
                if attempt < self._retries:
                    await asyncio.sleep(1.5 * (attempt + 1))
        raise ChatProviderError(f"{self.name} chat failed: {last_error}")


class StubProvider:
    """Deterministic stand-in: asks for the household's plan once, then
    answers by reading the tool results back plainly."""

    name = "stub"
    model = ""

    async def complete(self, messages: list[Message], tools: list[Message]) -> Message:
        tool_results = [m for m in messages if m.get("role") == "tool"]
        if tools and not tool_results:
            return {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "stub-call-1",
                        "type": "function",
                        "function": {"name": "get_my_plan", "arguments": "{}"},
                    }
                ],
            }
        if not tool_results:
            return {"role": "assistant", "content": "I don't have anything to go on yet."}
        try:
            plan = json.loads(tool_results[-1]["content"])
        except (json.JSONDecodeError, KeyError):
            plan = {}
        hours = plan.get("hours", []) if isinstance(plan, dict) else []
        if not hours:
            return {"role": "assistant", "content": "There's no planned session yet."}
        lines = [f"{h['hour']}: {h['plan']} {h.get('outcome', '')}".strip() for h in hours[:3]]
        return {
            "role": "assistant",
            "content": "Here's my plan for the first hours: " + " | ".join(lines),
        }


def get_provider(settings: Settings) -> ChatProvider:
    if settings.llm_provider is LLMProvider.GROQ and settings.groq_api_key:
        return OpenAICompatibleProvider(
            name="groq",
            base_url=_GROQ_BASE_URL,
            model=settings.groq_model,
            api_key=settings.groq_api_key,
            timeout_seconds=settings.llm_timeout_seconds,
            max_retries=settings.llm_max_retries,
        )
    if settings.llm_provider is LLMProvider.OLLAMA:
        return OpenAICompatibleProvider(
            name="ollama",
            base_url=f"{settings.ollama_base_url.rstrip('/')}/v1",
            model=settings.ollama_model,
            api_key=None,
            timeout_seconds=settings.llm_timeout_seconds,
            max_retries=settings.llm_max_retries,
        )
    return StubProvider()
