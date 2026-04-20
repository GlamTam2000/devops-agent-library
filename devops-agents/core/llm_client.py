"""
LLM client for GitHub Models.

GitHub Models exposes an OpenAI-compatible /chat/completions endpoint.
We use the official `openai` SDK pointed at GitHub's base URL, authenticated
with the GITHUB_TOKEN that GitHub Actions injects automatically when the
workflow declares `permissions: models: read`.

This makes the client trivially swappable: change the model string and
(optionally) the base_url, and the agent code doesn't care whether it's
talking to GPT, Claude, Gemini, Llama, or a self-hosted gateway.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from openai import OpenAI


DEFAULT_BASE_URL = "https://models.github.ai/inference"
DEFAULT_MODEL = "openai/gpt-4.1"


@dataclass
class LLMResponse:
    content: str
    model: str
    prompt_tokens: int | None
    completion_tokens: int | None


class LLMClient:
    """
    Thin wrapper so analyzers don't talk to OpenAI SDK directly.
    Keeps the surface we rely on small, which makes swapping providers easier.
    """

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        base_url: str = DEFAULT_BASE_URL,
        token: str | None = None,
    ) -> None:
        self.model = model
        resolved_token = token or os.environ.get("GITHUB_TOKEN")
        if not resolved_token:
            raise RuntimeError(
                "No auth token available. In GitHub Actions, set "
                "`permissions: models: read` on the workflow. Locally, "
                "export GITHUB_TOKEN with a PAT that has models:read."
            )
        self._client = OpenAI(base_url=base_url, api_key=resolved_token)

    def chat(
        self,
        system: str,
        user: str,
        *,
        temperature: float = 0.2,
        max_tokens: int = 1500,
    ) -> LLMResponse:
        """Single-turn chat. Low default temperature — we want reproducible reviews, not creative ones."""
        resp = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        choice = resp.choices[0]
        usage = resp.usage
        return LLMResponse(
            content=(choice.message.content or "").strip(),
            model=resp.model,
            prompt_tokens=getattr(usage, "prompt_tokens", None),
            completion_tokens=getattr(usage, "completion_tokens", None),
        )
