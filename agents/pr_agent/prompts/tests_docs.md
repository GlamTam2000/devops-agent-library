A pull request has changed the following files:

**Code files changed:**
{{code_files}}

**Test files changed:**
{{test_files}}

**Docs changed:**
{{docs_files}}

**Per-file diff summary:**

```
{{diff_summary}}
```

Answer two questions, succinctly:

1. **Test coverage:** Did non-trivial code changes ship without corresponding tests?
   Be pragmatic — renames, pure refactors, and config edits don't need new tests.
   New logic, new branches, new error paths do. List specific files that look under-tested.

2. **Docs:** Did public API or behaviour changes ship without README/doc updates?
   Internal refactors don't need doc updates. Changed public signatures, new CLI flags,
   changed config, or new env vars do.

**Output format:** markdown, 2–6 bullets total. If coverage is adequate, say so in one line
and stop. No preamble.
