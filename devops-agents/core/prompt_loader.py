"""
Prompt loader.

Prompts live as .md files next to each agent. Keeping them out of Python
source means:
  - Governance teams can diff prompts without reading Python
  - Hot-swap a prompt without a code deploy
  - Prompts stay version-controlled alongside the code that uses them

Substitution uses a conservative {{name}} syntax (double braces) so single
braces in code examples inside prompts don't get mangled.
"""

from __future__ import annotations

import re
from pathlib import Path


class PromptLoader:
    _VAR = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")

    def __init__(self, prompts_dir: str | Path) -> None:
        self.prompts_dir = Path(prompts_dir)
        if not self.prompts_dir.is_dir():
            raise FileNotFoundError(f"Prompts dir does not exist: {self.prompts_dir}")

    def load(self, prompt_name: str, /, **variables: object) -> str:
        """Load and render a prompt. `prompt_name` is positional-only so callers
        can pass `name=` as a template variable without colliding."""
        path = self.prompts_dir / f"{prompt_name}.md"
        if not path.exists():
            raise FileNotFoundError(f"Prompt not found: {path}")
        template = path.read_text(encoding="utf-8")

        def replace(match: re.Match[str]) -> str:
            key = match.group(1)
            if key not in variables:
                raise KeyError(f"Prompt '{prompt_name}' needs variable '{key}' but none was provided")
            return str(variables[key])

        return self._VAR.sub(replace, template)
