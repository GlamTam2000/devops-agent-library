A reviewer has 30 seconds. Summarise this pull request for them.

**PR title:** {{title}}

**PR body:**
{{body}}

**Diff (up to {{max_lines}} lines):**

```diff
{{diff}}
```

Produce exactly this structure, in markdown:

### TL;DR
One sentence. What does this PR actually change, in plain terms?

### What changed
3–5 bullets covering the *material* changes. Skip:
- Formatting-only changes
- Import reorders
- Test additions that merely mirror new code (mention "tests added" in one bullet, not one per file)

### Watch for
Any specific risks a reviewer should eyeball. Examples: "auth middleware reordered",
"new dependency X", "DB migration adds a non-nullable column". If there's nothing
noteworthy, say "Nothing unusual — standard change."

No preamble. No "Sure, here's..." or "This PR...". Just the sections above.
