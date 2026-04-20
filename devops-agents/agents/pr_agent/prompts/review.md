Review this pull request as a senior engineer at a serious engineering organisation.

**Priorities, in order:**
1. **Correctness bugs** — off-by-one, null/None handling, race conditions, incorrect logic, missing edge cases
2. **Broken error handling** — swallowed exceptions, silent failures, missing rollback
3. **Performance** — N+1 queries, quadratic loops over large inputs, obvious memory leaks
4. **Maintainability** — only flag if it would genuinely confuse the next reader

**Do NOT comment on:**
- Formatting (the linter handles it)
- Import ordering
- Minor naming preferences or personal style
- Anything you are not confident about — if in doubt, stay silent

**Diff:**

```diff
{{diff}}
```

**Output format:**

For each issue, a bullet in this exact shape:

- **[severity]** `file:line` — one-line description of the issue and its consequence.

Where severity is one of: **high** (likely bug), **medium** (probable issue worth fixing), **low** (worth considering).

Group by severity, highest first. If there are no material issues, respond with exactly:

> No blocking issues found.

No preamble. No hedging like "I noticed that..." — just the findings.
