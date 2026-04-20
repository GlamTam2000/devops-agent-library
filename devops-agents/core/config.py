"""
Config loader.

Resolution order (later wins):
  1. dataclass defaults
  2. .agentsrc.yml in repo root
  3. environment variables prefixed AGENTS_

Env overrides are explicit and scoped so nothing magical happens.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


DEFAULT_ANALYZERS: dict[str, bool] = {
    "summarize": True,
    "review": True,
    "tests_docs": True,
    "security": True,
}


@dataclass
class AgentConfig:
    model: str = "openai/gpt-4.1"
    api_base_url: str = "https://models.github.ai/inference"
    max_diff_lines: int = 2000
    dry_run: bool = False
    analyzers: dict[str, bool] = field(default_factory=lambda: dict(DEFAULT_ANALYZERS))
    audit_log_path: str = "agent-audit.jsonl"

    @classmethod
    def load(cls, path: str | Path = ".agentsrc.yml") -> "AgentConfig":
        data: dict[str, Any] = {}
        p = Path(path)
        if p.exists():
            with open(p) as f:
                loaded = yaml.safe_load(f) or {}
                if not isinstance(loaded, dict):
                    raise ValueError(f"{p} must contain a YAML mapping")
                data = loaded

        # Environment overrides (explicit, narrow allow-list)
        if v := os.environ.get("AGENTS_MODEL"):
            data["model"] = v
        if v := os.environ.get("AGENTS_API_BASE_URL"):
            data["api_base_url"] = v
        if v := os.environ.get("AGENTS_DRY_RUN"):
            data["dry_run"] = v.lower() in ("1", "true", "yes", "on")
        if v := os.environ.get("AGENTS_MAX_DIFF_LINES"):
            data["max_diff_lines"] = int(v)

        # Merge analyzers dict carefully so partial YAML doesn't wipe defaults
        analyzers = dict(DEFAULT_ANALYZERS)
        analyzers.update(data.get("analyzers") or {})
        data["analyzers"] = analyzers

        # Drop any keys the dataclass doesn't know about (forward-compat)
        known = set(cls.__dataclass_fields__.keys())
        clean = {k: v for k, v in data.items() if k in known}
        return cls(**clean)
