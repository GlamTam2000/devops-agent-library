"""
Smoke tests. Deliberately don't exercise the LLM or network.

Goal: catch the obvious breakage (imports, pattern regexes, comment
assembly, config parsing) in a few milliseconds locally and in CI.
"""

from __future__ import annotations

from pathlib import Path

import pytest


# ---------------------------------------------------------------- imports


def test_core_imports():
    from core import (  # noqa: F401
        AgentConfig,
        AuditLog,
        BaseAgent,
        BOT_COMMENT_MARKER,
        GitHubClient,
        LLMClient,
        PromptLoader,
    )


def test_pr_agent_imports():
    from agents.pr_agent.main import PRAgent, build_comment  # noqa: F401
    from agents.pr_agent.analyzers import (  # noqa: F401
        Reviewer,
        SecurityAnalyzer,
        Summarizer,
        TestsDocsChecker,
        scan_diff,
        format_scan_findings,
    )


# ---------------------------------------------------------------- config


def test_config_defaults():
    from core import AgentConfig

    cfg = AgentConfig.load("nonexistent-file.yml")
    assert cfg.model.startswith("openai/")
    assert cfg.max_diff_lines > 0
    assert cfg.analyzers["summarize"] is True
    assert cfg.analyzers["security"] is True
    assert cfg.dry_run is False


def test_config_env_override(monkeypatch):
    from core import AgentConfig

    monkeypatch.setenv("AGENTS_MODEL", "anthropic/claude-sonnet-4")
    monkeypatch.setenv("AGENTS_DRY_RUN", "true")
    cfg = AgentConfig.load("nonexistent-file.yml")
    assert cfg.model == "anthropic/claude-sonnet-4"
    assert cfg.dry_run is True


def test_config_yaml(tmp_path):
    from core import AgentConfig

    p = tmp_path / "agentsrc.yml"
    p.write_text(
        "model: meta/llama-3.3-70b-instruct\nmax_diff_lines: 500\nanalyzers:\n  security: false\n"
    )
    cfg = AgentConfig.load(p)
    assert cfg.model == "meta/llama-3.3-70b-instruct"
    assert cfg.max_diff_lines == 500
    assert cfg.analyzers["security"] is False
    # Other analyzers keep defaults
    assert cfg.analyzers["review"] is True


# ---------------------------------------------------------------- prompts


def test_prompt_loader_substitutes(tmp_path):
    from core import PromptLoader

    (tmp_path / "greet.md").write_text("Hello {{name}}, you are {{age}}.")
    p = PromptLoader(tmp_path)
    assert p.load("greet", name="Tammy", age=42) == "Hello Tammy, you are 42."


def test_prompt_loader_missing_var(tmp_path):
    from core import PromptLoader

    (tmp_path / "x.md").write_text("Hello {{who}}")
    p = PromptLoader(tmp_path)
    with pytest.raises(KeyError):
        p.load("x")


def test_pr_agent_prompts_exist():
    prompts_dir = Path(__file__).parent.parent / "agents" / "pr_agent" / "prompts"
    for name in ("summarize", "review", "tests_docs", "security"):
        assert (prompts_dir / f"{name}.md").exists(), f"Missing prompt: {name}.md"


# ---------------------------------------------------------------- security patterns


def test_scan_catches_aws_key():
    from agents.pr_agent.analyzers import scan_diff

    diff = """\
diff --git a/config.py b/config.py
--- a/config.py
+++ b/config.py
@@ -1,1 +1,2 @@
 # config
+AWS_KEY = "AKIAIOSFODNN7EXAMPLE"
"""
    findings = scan_diff(diff)
    names = [f.pattern for f in findings]
    assert "aws_access_key" in names


def test_scan_catches_eval():
    from agents.pr_agent.analyzers import scan_diff

    diff = """\
diff --git a/x.py b/x.py
--- a/x.py
+++ b/x.py
@@ -1,1 +1,2 @@
 x = 1
+result = eval(user_input)
"""
    findings = scan_diff(diff)
    assert any(f.pattern == "python_eval" for f in findings)


def test_scan_ignores_removed_lines():
    """Regex hits on '-' lines (removals) should NOT be flagged — the PR is removing them."""
    from agents.pr_agent.analyzers import scan_diff

    diff = """\
diff --git a/x.py b/x.py
--- a/x.py
+++ b/x.py
@@ -1,2 +1,1 @@
-result = eval(user_input)
 x = 1
"""
    findings = scan_diff(diff)
    assert not any(f.pattern == "python_eval" for f in findings)


def test_scan_captures_file_and_line():
    from agents.pr_agent.analyzers import scan_diff

    diff = """\
diff --git a/src/app.py b/src/app.py
--- a/src/app.py
+++ b/src/app.py
@@ -10,2 +10,3 @@
 def foo():
     pass
+    subprocess.run(cmd, shell=True)
"""
    findings = scan_diff(diff)
    shell_findings = [f for f in findings if f.pattern == "subprocess_shell_true"]
    assert len(shell_findings) == 1
    assert shell_findings[0].file == "src/app.py"
    assert shell_findings[0].line == 12


def test_scan_no_findings_on_clean_diff():
    from agents.pr_agent.analyzers import scan_diff

    diff = """\
diff --git a/README.md b/README.md
--- a/README.md
+++ b/README.md
@@ -1,1 +1,2 @@
 # Hello
+Nothing dangerous here.
"""
    assert scan_diff(diff) == []


# ---------------------------------------------------------------- comment assembly


def test_build_comment_includes_marker_and_sections():
    from core import BOT_COMMENT_MARKER
    from agents.pr_agent.main import build_comment

    sections = {
        "summary": "### TL;DR\nAdds a thing.",
        "review": "- **low** `x.py:1` — nit",
        "tests_docs": "Looks adequate.",
        "security_scan": "_No secrets found._",
        "security_llm": "> No LLM-flagged security concerns.",
    }
    out = build_comment(sections, model="openai/gpt-4.1")
    assert BOT_COMMENT_MARKER in out
    assert "PR Agent Review" in out
    assert "Adds a thing" in out
    assert "openai/gpt-4.1" in out
    # Order: summary first, then review, tests, security
    assert out.find("TL;DR") < out.find("Code Review")
    assert out.find("Code Review") < out.find("Tests & Docs")
    assert out.find("Tests & Docs") < out.find("Security")


def test_build_comment_skips_missing_sections():
    from agents.pr_agent.main import build_comment

    out = build_comment({"summary": "Tiny PR."}, model="openai/gpt-4.1")
    assert "Tiny PR" in out
    assert "Code Review" not in out
    assert "Security" not in out
