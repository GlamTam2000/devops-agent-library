# DevOps Agents

A small, extensible library of AI-powered DevOps agents that run inside GitHub Actions using **GitHub Models** for inference. No external API keys, no separate auth, the workflow's built-in `GITHUB_TOKEN` is the only credential.

Starts with two agents:

1. **PR Agent**  summarises PRs, reviews code, checks test/doc coverage, and runs a two-layer security scan (regex + LLM)
2. **README Agent**  coming next; generates or audits repo READMEs

The code is deliberately set up to be copied into another GitHub org (e.g. a work environment) with minimal changes.

---

## Why this design

- **GitHub Models is OpenAI-compatible**, so the LLM client is a thin wrapper around the `openai` SDK pointed at `https://models.github.ai/inference`. Swap the model string in `.agentsrc.yml` to move between GPT, Claude, Gemini, Llama, etc.  no code changes.
- **`GITHUB_TOKEN` is the only credential**. Once the workflow declares `permissions: models: read`, GitHub issues a scoped token that authenticates the inference calls. No PATs, no stored secrets.
- **Prompts live as `.md` files**, not Python strings. Review, diff, and version prompts separately from logic. Easier for AI-governance sign-off.
- **Structured JSONL audit log** is written per run and uploaded as a workflow artifact. Every LLM call is logged with model, hashes, token counts, and timing enough to prove to Risk/InfoSec what was sent and received without leaking code.
- **Two-layer security**: a cheap deterministic regex scan runs first (21 patterns covering secrets + dangerous code), then an LLM review handles the subtler stuff. Findings from each layer are surfaced separately in the PR comment so reviewers know what's machine-precise vs. machine-judgement.

---

## Project layout

```
devops-agents/
├── core/                          shared building blocks (import from here)
│   ├── llm_client.py              OpenAI-compatible wrapper for GitHub Models
│   ├── github_client.py           PR/comment operations via requests
│   ├── base_agent.py              abstract base every agent inherits from
│   ├── config.py                  .agentsrc.yml loader + env overrides
│   ├── prompt_loader.py           loads .md prompts with {{var}} substitution
│   └── audit_log.py               JSONL structured log
├── agents/
│   └── pr_agent/
│       ├── main.py                CLI entrypoint, orchestration, comment builder
│       ├── analyzers/             summarise / review / tests_docs / security
│       └── prompts/               one .md prompt file per analyzer
├── .github/workflows/
│   └── pr-agent.yml               triggers on pull_request, declares models: read
├── .agentsrc.yml                  per-repo config (model, toggles, limits)
├── pyproject.toml
└── tests/
    └── test_smoke.py              no-network unit tests
```

---

## Running locally (before you trust it on a real PR)

You'll need a GitHub personal access token with `models:read` scope. Export it and dry-run against one of your own PRs:

```bash
# From the repo root
pip install -e .
export GITHUB_TOKEN=ghp_your_token_here
python -m agents.pr_agent.main --repo owner/repo --pr 42 --dry-run
```

`--dry-run` prints the comment to stdout instead of posting it. Always use this on the first run against any new repo.

To iterate quickly, run the smoke tests:

```bash
pip install -e ".[dev]"
pytest
```

The smoke tests don't hit the network or call the LLM — they verify imports, config parsing, prompt substitution, the security scanner, and the comment builder.

---

## Installing into a GitHub repo

1. Copy this whole directory into the repo (or make it a submodule / installed dependency).
2. Copy `.github/workflows/pr-agent.yml` into `.github/workflows/` of the target repo.
3. Copy `.agentsrc.yml` to the repo root and adjust `model:` to one your org allows.
4. Open a test PR and watch the Actions tab. The agent posts one consolidated comment and edits it in place on subsequent pushes (via the `<!-- devops-agents:pr-agent -->` marker).

No secrets to configure. The workflow's default `GITHUB_TOKEN` already has `models: read` once the `permissions:` block is set.

---

## Porting to Lloyds different LLM Models (or any enterprise GitHub)

Three scenarios:

| "We've enabled GPT-4.1 and a few others"      | Set `model: openai/gpt-4.1` — you're done                                    |
| "We've added Anthropic/Google keys via BYOK"  | Set `model: anthropic/claude-sonnet-4` (or similar) — still works unchanged  |
| "GitHub Models isn't enabled for our org"     | You'll get a 403 when the workflow tries to call the API. Raise a ticket.   |

If Lloyds uses **GitHub Enterprise Server** instead of `github.com`, also set:

```yaml
# .agentsrc.yml
api_base_url: https://github.lloyds.internal/api/models/inference
```

and the `github_client.py` will pick up `GITHUB_API_URL` from the Actions runner automatically (it's set by GHES).

### InfoSec

The audit log and this README are designed as evidence that:

- No code leaves the GitHub perimeter (GitHub Models runs inside GitHub's infrastructure).
- No third-party secrets are stored — the only credential is the per-run `GITHUB_TOKEN`.
- Every LLM call is logged with model, hashes, and token counts.
- Prompts are checked into the repo and version-controlled.
- A kill-switch exists (`dry_run: true` in config, or disable the workflow file).

---

## Configuration reference

Everything in `.agentsrc.yml` can also be set via environment variable (useful for per-workflow overrides):

| `.agentsrc.yml`   | Environment variable     | Default                                     |
| ----------------- | ------------------------ | ------------------------------------------- |
| `model`           | `AGENTS_MODEL`           | `openai/gpt-4.1`                            |
| `api_base_url`    | `AGENTS_API_BASE_URL`    | `https://models.github.ai/inference`        |
| `max_diff_lines`  | `AGENTS_MAX_DIFF_LINES`  | `2000`                                      |
| `dry_run`         | `AGENTS_DRY_RUN`         | `false`                                     |
| `analyzers.*`     | (config file only)       | all `true`                                  |
| `audit_log_path`  | (config file only)       | `agent-audit.jsonl`                         |

To disable a specific analyzer for one repo:

```yaml
analyzers:
  security: false   # e.g. for a docs-only repo
```

---

## Security scanner coverage

The deterministic layer catches these without any LLM call:

- **Secrets**: AWS keys (AKIA + secret), GitHub PATs (classic + fine-grained), Slack tokens, Google API keys, Stripe live keys, private key blocks, JWTs, hardcoded password/API-key assignments
- **Dangerous Python**: `eval`, `exec`, `pickle.load(s)`, `subprocess(..., shell=True)`, `os.system`
- **Weak crypto**: MD5 / SHA1 used for security, `verify=False` on TLS
- **Injection**: SQL string concatenation (Python + .NET heuristics), `Runtime.getRuntime().exec()` in Java

The LLM layer handles what regex can't: PII in log statements, auth/authz logic changes, home-rolled crypto, obfuscated secrets, risky dependency additions.

To add or tune a pattern, edit `agents/pr_agent/analyzers/patterns.py`. Each pattern is a `Pattern(name, severity, regex, description)` tuple — self-contained.

---

## Extending: adding a new agent

1. `mkdir agents/my_agent` with `main.py`, `__init__.py`, and a `prompts/` directory.
2. Subclass `core.BaseAgent` — you get `self.llm`, `self.github`, `self.audit`, `self.config` for free.
3. Add a workflow file in `.github/workflows/`.
4. Add a `pr-agent`-style CLI entry in `pyproject.toml` if you want a console script.

The shared `core/` is the whole point — each new agent should be ~100 lines plus prompts.

---

## Status

- ✅ Core library
- ✅ PR Agent (summarise, review, tests/docs, security)
- ⬜ README Agent (next)
- ⬜ Deployment notes agent (future)
- ⬜ Release notes agent (future)

Author: Tammy Ajadi
Date: 20/04/2026

