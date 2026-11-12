"""The optional model provider, and the promise that it stays optional.

ECHO works with no model at all: answers are quoted from the user's own memories and
captures are extracted with rules. A provider is an upgrade, never a dependency, so this
module is written around three rules:

1. **Nothing here is required.** With no key, `build_llm()` returns `None` and every
   caller takes its deterministic path. There is no half-configured state where a
   request waits on a network call that was never set up.
2. **Every call is bounded.** A hard timeout, one retry-free attempt, and a token cap.
   A slow or broken provider costs a request a second, not a hung worker.
3. **Failures are values, not pages.** A provider error raises `LLMError`, which callers
   translate into the no-model path. The user gets cited quotations instead of a 500.

Only the OpenAI wire protocol is implemented, because that is what OpenAI, Azure-style
gateways, vLLM, LM Studio and Ollama all speak: pointing `ECHO_OPENAI_BASE_URL` at
`http://localhost:11434/v1` is the whole "local model" story, with no second code path.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from app.core.config import Settings, settings

logger = logging.getLogger("echo.llm")

DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_TIMEOUT = 20.0
MAX_TOKENS = 700


class LLMError(RuntimeError):
    """The provider could not answer. Callers fall back; they never propagate this."""


@dataclass(frozen=True)
class LLMClient:
    """What the rest of the app needs from a model: one bounded completion."""

    api_key: str
    model: str = DEFAULT_MODEL
    base_url: str = DEFAULT_BASE_URL
    timeout: float = DEFAULT_TIMEOUT
    transport: httpx.BaseTransport | None = None

    # ------------------------------------------------------------------ request
    def _post(self, payload: dict) -> dict:
        url = f"{self.base_url.rstrip('/')}/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        try:
            with httpx.Client(timeout=self.timeout, transport=self.transport) as client:
                response = client.post(url, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            # Deliberately does not include the request: the header carries the key.
            raise LLMError(f"model request failed ({type(exc).__name__})") from exc

        if response.status_code >= 400:
            raise LLMError(f"model returned HTTP {response.status_code}")
        try:
            return response.json()
        except ValueError as exc:
            raise LLMError("model returned a non-JSON body") from exc

    def complete(
        self,
        *,
        system: str,
        user: str,
        json_mode: bool = False,
        max_tokens: int = MAX_TOKENS,
        temperature: float = 0.0,
    ) -> str:
        payload: dict = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        body = self._post(payload)
        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError("model response had no message content") from exc
        if not isinstance(content, str) or not content.strip():
            raise LLMError("model returned an empty answer")
        return content.strip()


def build_llm(config: Settings | None = None, *, transport: httpx.BaseTransport | None = None) -> LLMClient | None:
    """The provider for this configuration, or `None` when there is not one.

    `transport` exists only so tests can answer a request without a network call; it
    changes nothing about what is sent.
    """
    cfg = config or settings
    if not cfg.llm_enabled:
        return None
    return LLMClient(
        api_key=cfg.openai_api_key or "",
        model=cfg.llm_model or DEFAULT_MODEL,
        base_url=cfg.openai_base_url or DEFAULT_BASE_URL,
        timeout=cfg.llm_timeout_seconds or DEFAULT_TIMEOUT,
        transport=transport,
    )


def describe(config: Settings | None = None) -> str:
    """One line for the startup log, without the key."""
    cfg = config or settings
    if not cfg.llm_enabled:
        return "model provider: none (extractive answers, rule-based extraction)"
    return f"model provider: openai/{cfg.llm_model} at {cfg.openai_base_url}"
