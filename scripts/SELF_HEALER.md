# Self-Healer Agent Rules

When the watchdog triggers you, follow these rules to save tokens and prevent
infinite loops.

## 1. Scoped Analysis
- Read `error_context.txt` first — it has the error class, log snippet, and retry count.
- Only read the file where the error occurred and its immediate imports.
- Do NOT explore unrelated files, refactor, or "improve" surrounding code.

## 2. Hypothesis First
- Before changing ANY code, print a 2-sentence Root Cause Analysis:
  - Sentence 1: What failed and where (file + line if possible).
  - Sentence 2: Why it failed (the actual bug, not the symptom).

## 3. Diffs Only
- Apply only the specific lines that fix the bug.
- No refactoring. No comment changes. No import reordering.
- If the fix requires more than ~20 lines changed, stop and report instead of fixing.

## 4. Safety Check
- If `error_context.txt` shows `retry_count >= 2`, this is the last attempt.
  If you cannot confidently fix it, do NOT change code — just report the diagnosis.
- Never attempt more than one fix strategy per invocation.
- If the smoke test fails after your fix, `git checkout .` to revert and report.

## 5. Deployment
- After fix passes smoke test: `git add`, `git commit`, `git push`.
- Commit message format: `fix: self-healing patch for <error_class>`
- Push to: `claude/starfire-ai-os-QWLqi` (the Railway deploy branch).
- Verify with: `railway status`

## 6. What NOT to fix
- **Billing errors** (credit balance too low) — report only, no code change.
- **Configuration errors** (missing env vars) — report only.
- **Schema migrations needed** — report only, never auto-generate migrations.
