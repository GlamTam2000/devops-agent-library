"""
PR agent orchestrator.

Flow:
  1. Load config.
  2. Fetch PR metadata, diff, and files list.
  3. Run enabled analyzers (sequentially — simpler for the PoC; parallelise later if needed).
  4. Build one consolidated markdown comment.
  5. Post (or dry-run print) via the bot-comment upsert so re-runs update in place.
  6. Write everything to the audit log.

CLI:
  python -m agents.pr_agent.main --repo owner/repo --pr 42
  python -m agents.pr_agent.main --repo owner/repo --pr 42 --dry-run
"""

from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path

from core import BOT_COMMENT_MARKER, AgentConfig, BaseAgent

from .analyzers import (
    Reviewer,
    SecurityAnalyzer,
    Summarizer,
    TestsDocsChecker,
    format_scan_findings,
)
from core.prompt_loader import PromptLoader


PROMPTS_DIR = Path(__file__).parent / "prompts"


class PRAgent(BaseAgent):
    name = "pr_agent"

    def __init__(self, repo: str, pr_number: int, config: AgentConfig | None = None) -> None:
        super().__init__(config)
        self.repo = repo
        self.pr_number = pr_number
        self.prompts = PromptLoader(PROMPTS_DIR)

    # -------------------------------------------------------------------- run

    def run(self) -> int:
        try:
            pr = self.github.get_pr(self.repo, self.pr_number)
        except Exception as exc:  # noqa: BLE001
            print(f"error: could not fetch PR: {exc}", file=sys.stderr)
            self.audit.record_event(self.name, "fetch_failed", error=str(exc))
            return 2

        title = pr.get("title", "")
        body = pr.get("body") or ""
        diff = self.github.get_pr_diff(self.repo, self.pr_number)
        files = self.github.get_pr_files(self.repo, self.pr_number)

        self.audit.record_event(
            self.name,
            "pr_fetched",
            repo=self.repo,
            pr=self.pr_number,
            title_len=len(title),
            body_len=len(body),
            diff_lines=len(diff.splitlines()),
            files_count=len(files),
        )

        sections: dict[str, str] = {}
        scan_findings: list = []  # kept for the auto-merge gate below
        cfg = self.config

        if cfg.analyzers.get("summarize", True):
            try:
                out, resp = Summarizer(self.llm, self.prompts).run(
                    title=title, body=body, diff=diff, max_lines=cfg.max_diff_lines
                )
                sections["summary"] = out
                self._log("summarize", resp)
            except Exception as exc:  # noqa: BLE001
                sections["summary"] = f"_Summariser failed: `{exc}`_"
                self.audit.record_event(self.name, "analyzer_failed", analyzer="summarize", error=str(exc))

        if cfg.analyzers.get("review", True):
            try:
                out, resp = Reviewer(self.llm, self.prompts).run(
                    diff=diff, max_lines=cfg.max_diff_lines
                )
                sections["review"] = out
                self._log("review", resp)
            except Exception as exc:  # noqa: BLE001
                sections["review"] = f"_Reviewer failed: `{exc}`_"
                self.audit.record_event(self.name, "analyzer_failed", analyzer="review", error=str(exc))

        if cfg.analyzers.get("tests_docs", True):
            try:
                out, resp = TestsDocsChecker(self.llm, self.prompts).run(files=files)
                sections["tests_docs"] = out
                if resp is not None:
                    self._log("tests_docs", resp)
            except Exception as exc:  # noqa: BLE001
                sections["tests_docs"] = f"_Tests/docs check failed: `{exc}`_"
                self.audit.record_event(self.name, "analyzer_failed", analyzer="tests_docs", error=str(exc))

        if cfg.analyzers.get("security", True):
            try:
                result = SecurityAnalyzer(self.llm, self.prompts).run(
                    diff=diff, max_lines=cfg.max_diff_lines
                )
                scan_findings = result["scan_findings"]  # type: ignore[assignment]
                sections["security_scan"] = format_scan_findings(scan_findings)  # type: ignore[arg-type]
                sections["security_llm"] = result["llm_review"]  # type: ignore[assignment]
                if result.get("llm_response"):
                    self._log("security", result["llm_response"])
            except Exception as exc:  # noqa: BLE001
                sections["security_scan"] = "_Security scan failed._"
                sections["security_llm"] = f"_Security review failed: `{exc}`_"
                self.audit.record_event(self.name, "analyzer_failed", analyzer="security", error=str(exc))

        comment = build_comment(sections, model=cfg.model)

        if cfg.dry_run:
            print("---- DRY RUN: would post this comment ----\n")
            print(comment)
            print("\n---- end DRY RUN ----")
            self.audit.record_event(self.name, "dry_run_completed", comment_len=len(comment))
            return 0

        try:
            self.github.upsert_bot_comment(self.repo, self.pr_number, comment)
            self.audit.record_event(self.name, "comment_posted", comment_len=len(comment))
        except Exception as exc:  # noqa: BLE001
            print(f"error: failed to post comment: {exc}", file=sys.stderr)
            self.audit.record_event(self.name, "comment_failed", error=str(exc))
            return 3

        if cfg.auto_merge:
            self._maybe_auto_merge(pr, scan_findings)

        return 0

    def _maybe_auto_merge(self, pr: dict, scan_findings: list) -> None:
        """Merge the PR iff it's mergeable and has zero HIGH-severity scan findings.

        Branch-protection rules (required approvals, required checks) are enforced
        server-side by GitHub — if unsatisfied, the merge call returns 405 and we
        record the skip. That's the intended behaviour for protected repos.
        """
        high = [f for f in scan_findings if getattr(f, "severity", "").lower() == "high"]
        if high:
            reason = f"{len(high)} HIGH-severity scan finding(s)"
            print(f"::notice::auto-merge skipped: {reason}")
            self.audit.record_event(self.name, "auto_merge_skipped", reason=reason)
            return

        # pr["mergeable"] can be None when GitHub is still computing it
        mergeable = pr.get("mergeable")
        if mergeable is not True:
            reason = f"mergeable={mergeable!r}"
            print(f"::notice::auto-merge skipped: {reason}")
            self.audit.record_event(self.name, "auto_merge_skipped", reason=reason)
            return

        try:
            self.github.merge_pr(self.repo, self.pr_number, method="squash")
            print("::notice::PR auto-merged by agent (squash)")
            self.audit.record_event(self.name, "auto_merged", method="squash")
        except Exception as exc:  # noqa: BLE001
            print(f"::warning::auto-merge failed: {exc}")
            self.audit.record_event(self.name, "auto_merge_failed", error=str(exc))

    def _log(self, analyzer: str, resp: object) -> None:
        """Log an LLM call. resp is an LLMResponse but we duck-type to avoid circular imports."""
        self.audit.record_llm_call(
            agent=self.name,
            analyzer=analyzer,
            model=getattr(resp, "model", self.config.model),
            system_prompt="",  # system prompts are short and in-code; not worth double-logging
            user_prompt="",  # full prompt is reproducible from repo + input; hash would need full capture
            response=getattr(resp, "content", ""),
            prompt_tokens=getattr(resp, "prompt_tokens", None),
            completion_tokens=getattr(resp, "completion_tokens", None),
        )


# ---------------------------------------------------------------- comment build


def build_comment(sections: dict[str, str], model: str) -> str:
    parts: list[str] = [BOT_COMMENT_MARKER, "## 🤖 PR Agent Review", ""]

    if "summary" in sections:
        parts += [sections["summary"].strip(), ""]
        parts += ["---", ""]

    if "review" in sections:
        parts += ["### 👀 Code Review", "", sections["review"].strip(), ""]

    if "tests_docs" in sections:
        parts += ["### 🧪 Tests & Docs", "", sections["tests_docs"].strip(), ""]

    if "security_scan" in sections or "security_llm" in sections:
        parts += ["### 🔐 Security", ""]
        if "security_scan" in sections:
            parts += ["**Deterministic scan:**", "", sections["security_scan"].strip(), ""]
        if "security_llm" in sections:
            parts += ["**LLM review:**", "", sections["security_llm"].strip(), ""]

    parts += [
        "---",
        f"<sub>Model: `{model}` · Re-run to refresh this comment · Audit log in workflow artifacts.</sub>",
    ]
    return "\n".join(parts)


# ---------------------------------------------------------------- CLI


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="pr-agent", description="Review a GitHub PR with AI.")
    p.add_argument("--repo", required=True, help="owner/repo")
    p.add_argument("--pr", required=True, type=int, help="PR number")
    p.add_argument("--dry-run", action="store_true", help="Print the comment instead of posting")
    p.add_argument("--config", default=".agentsrc.yml", help="Path to config file")
    args = p.parse_args(argv)

    config = AgentConfig.load(args.config)
    if args.dry_run:
        config.dry_run = True

    try:
        agent = PRAgent(repo=args.repo, pr_number=args.pr, config=config)
        return agent.run()
    except Exception as exc:  # noqa: BLE001
        print(f"fatal: {exc}", file=sys.stderr)
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
