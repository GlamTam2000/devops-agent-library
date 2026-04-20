"""Reviewer: correctness, error handling, performance. Skips nits."""

from __future__ import annotations

from core import LLMClient, PromptLoader

from .summarizer import _truncate_diff


class Reviewer:
    name = "review"

    def __init__(self, llm: LLMClient, prompts: PromptLoader) -> None:
        self.llm = llm
        self.prompts = prompts

    def run(self, *, diff: str, max_lines: int) -> tuple[str, object]:
        truncated_diff = _truncate_diff(diff, max_lines)
        user = self.prompts.load("review", diff=truncated_diff)
        system = (
            "You are a senior engineer reviewing a pull request. "
            "Be precise, cite file:line, and only flag material issues. "
            "Markdown only. No preamble."
        )
        resp = self.llm.chat(system=system, user=user, temperature=0.1, max_tokens=1500)
        return resp.content, resp
