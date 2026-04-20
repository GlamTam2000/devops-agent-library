"""
Structured audit log.

Writes one JSON object per line (JSONL) so it can be uploaded as a workflow
artifact and ingested by log platforms later (Splunk, Elastic, etc).

Prompts themselves are NOT written to the log — we write a hash and length.
If Lloyds Risk ever asks "was prompt X used on PR Y", the hash lets you prove
it without leaking code. If they want the full prompt, they have the repo.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class AuditLog:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def _write(self, event: dict[str, Any]) -> None:
        event = {"timestamp": datetime.now(timezone.utc).isoformat(), **event}
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

    def record_llm_call(
        self,
        *,
        agent: str,
        analyzer: str,
        model: str,
        system_prompt: str,
        user_prompt: str,
        response: str,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
    ) -> None:
        self._write(
            {
                "type": "llm_call",
                "agent": agent,
                "analyzer": analyzer,
                "model": model,
                "prompt_hash": _hash(system_prompt + "\n---\n" + user_prompt),
                "response_hash": _hash(response),
                "system_len": len(system_prompt),
                "user_len": len(user_prompt),
                "response_len": len(response),
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
            }
        )

    def record_event(self, agent: str, event_type: str, **fields: Any) -> None:
        self._write({"type": event_type, "agent": agent, **fields})


def _hash(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]
