"""
Deterministic security patterns.

Cheap, fast first-pass scan for secrets and dangerous code patterns.
Runs before the LLM review so we catch the obvious stuff without spending
tokens and can surface it distinctly ("the scanner found X" vs "the LLM
thinks Y").

Patterns are deliberately conservative — false positives here annoy devs
and train them to ignore the bot. If a pattern fires > 10% false positive
rate on your codebase, drop it or tighten it.

Sources: trufflehog, gitleaks, OWASP cheatsheet, CWE top 25.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Pattern:
    name: str
    severity: str  # "high" | "medium" | "low"
    regex: re.Pattern[str]
    description: str


# -- Secrets -------------------------------------------------------------------

SECRET_PATTERNS: list[Pattern] = [
    Pattern(
        "aws_access_key",
        "high",
        re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
        "AWS access key ID",
    ),
    Pattern(
        "aws_secret_key",
        "high",
        re.compile(r"aws[_\-]?secret[_\-]?access[_\-]?key['\"]?\s*[:=]\s*['\"][A-Za-z0-9/+=]{40}['\"]", re.IGNORECASE),
        "AWS secret access key",
    ),
    Pattern(
        "github_pat_classic",
        "high",
        re.compile(r"\bghp_[A-Za-z0-9]{36}\b"),
        "GitHub personal access token (classic)",
    ),
    Pattern(
        "github_pat_fine",
        "high",
        re.compile(r"\bgithub_pat_[A-Za-z0-9_]{82}\b"),
        "GitHub fine-grained personal access token",
    ),
    Pattern(
        "slack_token",
        "high",
        re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b"),
        "Slack token",
    ),
    Pattern(
        "google_api_key",
        "high",
        re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
        "Google API key",
    ),
    Pattern(
        "stripe_secret_key",
        "high",
        re.compile(r"\bsk_live_[0-9a-zA-Z]{24,}\b"),
        "Stripe secret key (live)",
    ),
    Pattern(
        "private_key_block",
        "high",
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----"),
        "Private key block",
    ),
    Pattern(
        "jwt",
        "medium",
        re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
        "JWT token — verify it's not a real session/credential",
    ),
    Pattern(
        "hardcoded_password",
        "medium",
        re.compile(r"""(?ix)
            \b(password|passwd|pwd)\s*[:=]\s*['"]([^'"\s]{6,})['"]
        """),
        "Hardcoded password assignment",
    ),
    Pattern(
        "generic_api_key",
        "medium",
        re.compile(r"""(?ix)
            \b(api[_-]?key|apikey|secret)\s*[:=]\s*['"]([A-Za-z0-9_\-]{24,})['"]
        """),
        "Possible hardcoded API key or secret",
    ),
]


# -- Dangerous code patterns ---------------------------------------------------

CODE_PATTERNS: list[Pattern] = [
    Pattern(
        "python_eval",
        "high",
        re.compile(r"\beval\s*\("),
        "eval() call — never safe with untrusted input",
    ),
    Pattern(
        "python_exec",
        "high",
        re.compile(r"\bexec\s*\("),
        "exec() call — never safe with untrusted input",
    ),
    Pattern(
        "pickle_loads",
        "high",
        re.compile(r"\bpickle\.loads?\s*\("),
        "pickle.load(s) — RCE risk on untrusted data",
    ),
    Pattern(
        "subprocess_shell_true",
        "high",
        re.compile(r"subprocess\.[^(]+\([^)]*shell\s*=\s*True"),
        "subprocess with shell=True — command injection risk",
    ),
    Pattern(
        "os_system",
        "medium",
        re.compile(r"\bos\.system\s*\("),
        "os.system() — prefer subprocess.run with a list",
    ),
    Pattern(
        "md5_for_security",
        "medium",
        re.compile(r"\b(?:hashlib\.md5|MessageDigest\.getInstance\(\s*['\"]MD5['\"])"),
        "MD5 is broken — not acceptable for security/passwords",
    ),
    Pattern(
        "sha1_for_security",
        "low",
        re.compile(r"\b(?:hashlib\.sha1|MessageDigest\.getInstance\(\s*['\"]SHA-?1['\"])"),
        "SHA1 is weak — avoid for security/password hashing",
    ),
    Pattern(
        "sql_string_concat",
        "medium",
        re.compile(r"""(?ix)
            (execute|query|cursor\.execute)\s*\(\s*['"][^'"]*\s\+\s
        """),
        "Possible SQL string concatenation — use parameterised queries",
    ),
    Pattern(
        "verify_false",
        "medium",
        re.compile(r"verify\s*=\s*False"),
        "TLS verification disabled (verify=False)",
    ),
    Pattern(
        "java_runtime_exec",
        "high",
        re.compile(r"Runtime\.getRuntime\(\)\.exec\s*\("),
        "Runtime.exec() — command injection risk",
    ),
    Pattern(
        "dotnet_sql_concat",
        "medium",
        re.compile(r"""(?ix)
            new\s+SqlCommand\s*\(\s*(?:"|\$")[^"]*\+\s*
        """),
        "SqlCommand built by string concatenation — use parameters",
    ),
]


ALL_PATTERNS: list[Pattern] = SECRET_PATTERNS + CODE_PATTERNS
