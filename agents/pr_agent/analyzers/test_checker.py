"""
Tests & docs checker.

Uses heuristics to classify each changed file, then asks the LLM whether
the coverage looks adequate. The heuristics are deliberately simple; the
LLM adds the judgement about whether a change was non-trivial.
"""

from __future__ import annotations

from typing import Any

from core import LLMClient, PromptLoader


TEST_HINTS = ("test_", "_test.", "/tests/", "/test/", ".spec.", ".test.", "Tests.cs", "Test.java", "Spec.java")
DOC_HINTS = ("README", "readme", ".md", "/docs/", "/doc/", "CHANGELOG", "CONTRIBUTING")
CODE_EXTS = (".py", ".java", ".cs", ".ts", ".tsx", ".js", ".jsx", ".go", ".rb", ".kt", ".scala", ".cpp", ".c", ".h", ".hpp")


class TestsDocsChecker:
    name = "tests_docs"
    __test__ = False  # pytest: this is a domain class, not a test collection

    def __init__(self, llm: LLMClient, prompts: PromptLoader) -> None:
        self.llm = llm
        self.prompts = prompts

    def run(self, *, files: list[dict[str, Any]]) -> tuple[str, object | None]:
        buckets = _classify(files)

        # Fast path: if nothing code-ish changed, no LLM call needed
        if not buckets["code"]:
            return "No code files changed — test/doc review skipped.", None

        # Fast path: if tests OR docs were touched proportionally, skip LLM
        code_count = len(buckets["code"])
        if len(buckets["tests"]) >= max(1, code_count // 2):
            return f"Tests updated alongside code ({len(buckets['tests'])} test file(s) for {code_count} code file(s)). Looks adequate.", None

        user = self.prompts.load(
            "tests_docs",
            code_files="\n".join(f"- {f}" for f in buckets["code"]) or "(none)",
            test_files="\n".join(f"- {f}" for f in buckets["tests"]) or "(none)",
            docs_files="\n".join(f"- {f}" for f in buckets["docs"]) or "(none)",
            diff_summary=_diff_summary(files),
        )
        system = "You are a pragmatic tech lead. Markdown only. No preamble."
        resp = self.llm.chat(system=system, user=user, temperature=0.1, max_tokens=600)
        return resp.content, resp


def _classify(files: list[dict[str, Any]]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {"code": [], "tests": [], "docs": [], "other": []}
    for f in files:
        name = f.get("filename", "")
        if any(h in name for h in TEST_HINTS):
            out["tests"].append(name)
        elif any(name.endswith(h) or h in name for h in DOC_HINTS):
            out["docs"].append(name)
        elif name.endswith(CODE_EXTS):
            out["code"].append(name)
        else:
            out["other"].append(name)
    return out


def _diff_summary(files: list[dict[str, Any]]) -> str:
    """Per-file additions/deletions summary so the LLM can tell trivial from non-trivial."""
    lines = []
    for f in files[:50]:  # cap
        lines.append(
            f"{f.get('filename')}: +{f.get('additions', 0)} -{f.get('deletions', 0)} "
            f"({f.get('status', '?')})"
        )
    return "\n".join(lines)
