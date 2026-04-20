"""
Base agent. Every agent (PR agent, README agent, future ones) inherits
from this so they share config, LLM client, GitHub client, and audit log.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from .audit_log import AuditLog
from .config import AgentConfig
from .github_client import GitHubClient
from .llm_client import LLMClient


class BaseAgent(ABC):
    name: str = "base"

    def __init__(self, config: AgentConfig | None = None) -> None:
        self.config = config or AgentConfig.load()
        self.llm = LLMClient(model=self.config.model, base_url=self.config.api_base_url)
        self.github = GitHubClient()
        self.audit = AuditLog(self.config.audit_log_path)

    @abstractmethod
    def run(self) -> int:
        """Run the agent. Return 0 on success, non-zero on failure."""
