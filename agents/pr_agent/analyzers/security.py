"""
Security analyzer — two layers:

1. Deterministic pattern scan over the diff (fast, zero tokens).
2. LLM review over the same diff for subtler issues (PII logging,
   auth changes, crypto mistakes, insecure deserialisation patterns
   the regex missed).

Findings are returned separately so the PR comment can show them
distinctly. Readers should be able to tell "the scanner caught this"
from "the LLM thinks this".
"""

from __future__ import annotations

from dataclasses import dataclass

from core import LLMClient, PromptLoader

from .patterns import ALL_PATTERNS
from .summarizer import _truncate_diff


@dataclass(frozen=True)
class ScanFinding:
    pattern: str
    severity: str
    description: str
    file: str
    line: int
    snippet: str


class SecurityAnalyzer:
    name = "security"

    def __init__(self, llm: LLMClient, prompts: PromptLoader) -> None:
        self.llm = llm
        self.prompts = prompts

    def run(self, *, diff: str, max_lines: int) -> dict[str, object]:
        """Returns dict with 'scan_findings' (list), 'llm_review' (str), and 'llm_response' (LLMResponse|None)."""
        scan_findings = scan_diff(diff)

        truncated_diff = _truncate_diff(diff, max_lines)
        user = self.prompts.load("security", diff=truncated_diff)
        system = (
            "You are a security engineer reviewing code for a regulated "
            "financial services environment. Be precise and avoid crying wolf."
        )
        resp = self.llm.chat(system=system, user=user, temperature=0.1, max_tokens=1200)

        return {
            "scan_findings": scan_findings,
            "llm_review": resp.content,
            "llm_response": resp,
        }


def scan_diff(diff: str) -> list[ScanFinding]:
    """Walk a unified diff and flag lines that match a dangerous pattern.

    Only scans ADDED lines (starting with '+'), not context or deletions —
    we don't want to flag stuff the PR is *removing*.
    """
    findings: list[ScanFinding] = []
    current_file = "?"
    line_in_new = 0

    for raw_line in diff.splitlines():
        # File header, e.g. "+++ b/path/to/file.py"
        if raw_line.startswith("+++ "):
            current_file = raw_line[4:].removeprefix("b/").strip()
            line_in_new = 0
            continue

        # Hunk header, e.g. "@@ -12,3 +34,5 @@"
        if raw_line.startswith("@@"):
            try:
                # Parse the +NEW,COUNT part
                new_part = raw_line.split("+", 1)[1].split(" ", 1)[0]
                line_in_new = int(new_part.split(",", 1)[0])
            except (IndexError, ValueError):
                line_in_new = 0
            continue

        # Diff body lines
        if raw_line.startswith("+") and not raw_line.startswith("+++"):
            content = raw_line[1:]
            for pattern in ALL_PATTERNS:
                if pattern.regex.search(content):
                    findings.append(
                        ScanFinding(
                            pattern=pattern.name,
                            severity=pattern.severity,
                            description=pattern.description,
                            file=current_file,
                            line=line_in_new,
                            snippet=content.strip()[:200],
                        )
                    )
            line_in_new += 1
        elif raw_line.startswith(" "):  # context line
            line_in_new += 1
        # '-' deletions don't advance new-file line count

    return findings


def format_scan_findings(findings: list[ScanFinding]) -> str:
    if not findings:
        return "_No secrets or known-dangerous patterns detected._"
    # Sort: high severity first, then by file/line
    order = {"high": 0, "medium": 1, "low": 2}
    findings = sorted(findings, key=lambda f: (order.get(f.severity, 9), f.file, f.line))

    lines = []
    for f in findings:
        emoji = {"high": "🔴", "medium": "🟠", "low": "🟡"}.get(f.severity, "⚪")
        snippet = f.snippet.replace("`", "ˋ")  # neutralise backticks
        lines.append(
            f"- {emoji} **{f.severity.upper()}** · `{f.file}:{f.line}` · {f.description}\n"
            f"  _Pattern_: `{f.pattern}` · _Snippet_: `{snippet}`"
        )
    return "\n".join(lines)
