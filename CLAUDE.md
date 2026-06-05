# STARFIRE — Agent Operating Guide

STARFIRE is a personal AI chief-of-staff: a FastAPI + Python service on Railway
(PostgreSQL + Redis) driving a Telegram bot. It coordinates tasks, bills,
calendar, Gmail/Drive/Sheets, spending, goals, market data, and trade execution.

---

## 1. Deployment — READ FIRST

- **Railway deploys from the branch `claude/starfire-ai-os-QWLqi`, NOT `main`.**
  Every deployable fix MUST be pushed here or it will not go live.
- Railway auto-deploys on each push to that branch — no manual trigger needed.
- `main` is for record-keeping / PRs only.
- Push pattern: `git push -u origin claude/starfire-ai-os-QWLqi` (retry up to 4×
  with exponential backoff on network errors).

---

## 2. Autonomous workflow (auto-fix, PR merge, self-update)

The operator has granted full authority. Do not ask permission for routine
engineering work — act, then report what was done.

### Auto-fix → verify → ship loop
When a bug is found (reported, or surfaced by the self-test / Sentinel),
run the full loop automatically:
1. Diagnose the root cause and write the fix. You are authorized to fix
   schema, logic, and runtime bugs without asking.
2. Verify: `python3 -m py_compile <files>` + run the relevant pure-logic
   checks in `app/monitoring/selftest.py`. Do not proceed on a failing check.
3. Commit (descriptive, imperative message explaining the root cause; session
   footer; never secrets/tokens/model id) and push to the deploy branch — this
   auto-deploys on Railway.
4. Open a PR (draft) for the record, and merge it when CI is green.
5. Sentinel triggers a self-redeploy automatically on persistent errors; you
   do not normally redeploy by hand (a push already deploys).

### PR merge authority
- Merge PRs autonomously when CI is green and the change is sound. No need to
  ask first.
- Only escalate (via AskUserQuestion) when a change is architecturally
  significant, ambiguous, or irreversible in a way the operator wouldn't expect.

### Self-update / monitoring (three layers — keep them healthy)
- **Sentinel** (`app/monitoring/sentinel.py`) — catches runtime exceptions,
  rate-alerts the admin via Telegram, auto-recovers transient failures
  (Google auth, API timeouts, Redis), and can self-redeploy on persistent
  errors. Every worker/agent exception handler routes through
  `sentinel.capture(e, category=..., context=...)`.
- **Self-test** (`app/monitoring/selftest.py`) — runs ~45s after boot,
  exercises every feature's query path against the live schema plus pure-logic
  checks, and alerts the admin on any broken path. Catches schema-drift /
  logic bugs that exception monitoring cannot see (code paths no user has hit
  yet). **When you add a feature with a new query path or non-trivial logic,
  add a corresponding check here.**
- **Health worker** (`app/monitoring/health_worker.py`) — pings DB, Redis,
  Anthropic, Telegram every 15 min.

Sentinel/self-test detect and alert; they do NOT write code. Actual fixes come
through this dev loop (commit → push → deploy), never runtime self-patching.

---

## 3. Self-improvement & ideation

- Periodically review `starfire_run.log` and user interaction patterns for
  recurring errors, slow paths, and unmet needs.
- Capture recommended features, optimizations, and architectural improvements
  in **`IDEAS.md`** (append there — do NOT dump long idea lists into chat).
  Keep entries dated, prioritized, and concrete enough to action later.

---

## 4. Architecture map

- `app/main.py` — FastAPI lifespan; starts workers + self-test.
- `app/telegram/bot.py` — command + handler registration.
- `app/telegram/handlers.py` — command handlers; most route through the brain.
- `app/starfire/brain.py` — Claude calls; `_parse_response` extracts action
  JSON (direct, code-block, or embedded-in-prose).
- `app/starfire/decision.py` — `DecisionEngine`; dispatches action types.
- `app/starfire/prompts.py` — system prompt: routing hints + action JSON specs.
- `app/agents/` — `base.py` (run lifecycle + AgentRun), `cfo_agent`,
  `research_agent`, `work_agent` (autonomous research + math).
- `app/workers/` — market, event, report, automation (background loops).
- `app/integrations/gmail_service.py` — Gmail/Drive/Calendar/Sheets services.
- `app/services/focus_engine.py` — daily focus computation.

### Adding a brain action
1. Add the `action_type` branch in `decision.py`'s dispatch.
2. Add a routing hint + JSON example in `prompts.py`.
3. If it has a command, register it in `bot.py` and add the handler.
4. Add a self-test check if it introduces a new query path or real logic.
5. The brain must output **only** raw JSON for actions — never prose + JSON.

---

## 5. Model schema — exact column names (prevents schema-drift bugs)

Verify against `app/models/` before writing queries. Common gotchas:

- **Task** (`task.py`): `status` ∈ `PENDING | IN_PROGRESS | DONE | CANCELLED`
  (NOT "COMPLETE"). Fields: `due_at`, `completed_at`, `priority`.
- **Goal** (`goal.py`): `status` ∈ `ACTIVE | ACHIEVED | ABANDONED`. Deadline is
  `target_date` (NOT "deadline"). Progress = `current_value` / `target_value`
  (NO `progress_pct` column).
- **Bill** (`bill.py`): NO `is_paid` flag. Uses `last_paid_at`, `due_day`
  (day-of-month, recurring), `due_date` (one-time), `is_active`, `is_recurring`,
  `autopay`. Use `app.services.focus_engine._bill_due_soon()` for due logic.
- **GmailService** (`gmail_service.py`): `_svc` is an attribute, not a method.
  Search via `gmail.search(query, max_results)` → list of summary dicts with
  `id`, `from`, `subject`, `snippet`. There is no `list_messages()`.

---

## 6. Math engine

`app/agents/work_agent.py` `compute_math()` runs a sandboxed eval with sympy +
numpy. Symbols `x y z t n a b c k` are pre-declared; elementary functions
(`sin cos tan exp sqrt log`) are sympy versions (work on symbols and numbers).
Examples: `solve(x**2-4, x)`, `diff(sin(x)*x**2, x)`, `N(integrate(...), 6)`,
`Matrix([[1,2],[3,4]]).det()`.

---

## 7. Security — non-negotiable

- NEVER put secrets, API keys, tokens, client secrets, or the model id into
  commit messages, PR titles/bodies, code comments, or any repository artifact.
- Secrets live only in Railway environment variables.
- Admin Telegram ID is the alert target for Sentinel/self-test.

---

## 8. Verification checklist before "done"

- [ ] `python3 -m py_compile` on every changed file
- [ ] Relevant `selftest.py` checks pass (run the pure-logic ones locally)
- [ ] New query paths / logic have a self-test check
- [ ] Committed with a clear message (no secrets, no model id)
- [ ] Pushed to `claude/starfire-ai-os-QWLqi`
- [ ] PR exists (draft) for record

---

## 🛠️ Critical System Commands
- Run self-test suite: `python app/monitoring/selftest.py`
- Full pytest suite: `python3 -m pytest tests/ -q`
- View execution log: `tail -n 50 starfire_run.log`
- Database migration (if schema changes): `alembic upgrade head`
  (Railway runs this automatically at boot via the start command.)

---

## 🧠 Memory & Context Conservation
- Use precise Search-and-Replace block edits. NEVER rewrite an entire file to
  change a few lines.
- Frequently execute the `/clear` command when transitioning between unrelated
  debugging tasks to wipe accumulated context history.

---

## 🚀 Autonomous Feature Ideation & Logging
- When creating feature ideas, never dump text arrays into the terminal console.
  Write them as functional user-stories directly into `IDEAS.md`.
- Prioritize features utilizing the Model Context Protocol (MCP) or low-latency
  background-worker structures.

---

## 🛑 Hard Architectural Constraints
- NEVER force-push to `main` without running `selftest.py` first.
- If an autonomous code-fix loops or fails 3 consecutive times, stop executing,
  drop a diagnostic log in `starfire_run.log`, and alert via Telegram. Do not
  drain tokens trying a 4th time.
