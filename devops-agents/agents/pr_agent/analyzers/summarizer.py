"""Summariser: TL;DR + bullets + risks, written for a reviewer in a hurry."""

from __future__ import annotations

from core import LLMClient, PromptLoader


class Summarizer:
    name = "summarize"

    def __init__(self, llm: LLMClient, prompts: PromptLoader) -> None:
        self.llm = llm
        self.prompts = prompts

    def run(self, *, title: str, body: str, diff: str, max_lines: int) -> tuple[str, object]:
        truncated_diff = _truncate_diff(diff, max_lines)
        user = self.prompts.load(
            "summarize",
            title=title,
            body=body or "(no body)",
            diff=truncated_diff,
            max_lines=max_lines,
        )
        system = "You are a concise code reviewer. Markdown only. No preamble."
        resp = self.llm.chat(system=system, user=user, temperature=0.2, max_tokens=800)
        return resp.content, resp


def _truncate_diff(diff: str, max_lines: int) -> str:
    lines = diff.splitlines()
    if len(lines) <= max_lines:
        return diff
    kept = lines[:max_lines]
    return "\n".join(kept) + f"\n\n[... diff truncated; showing first {max_lines} of {len(lines)} lines ...]"
