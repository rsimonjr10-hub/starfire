# STARFIRE — Ideas & Improvements

Proactive backlog of features, optimizations, and architectural improvements.
Append here (don't dump into chat). Keep entries dated, prioritized, concrete.

Priority: **P0** ship now · **P1** soon · **P2** nice-to-have

---

## 2026-06-05 — seeded from monitoring/self-heal work

### Reliability & self-healing
- **[P1] Wire `sentinel.capture()` into `handlers.py` command handlers.** Many
  Telegram command handlers still log-only or reply with an error string; a
  failing command never reaches the admin alert path. Mirror the worker/agent
  wiring done on this date.
- **[P1] Worker heartbeats.** The health worker pings DB/Redis/APIs but not the
  background workers themselves. Have each worker write a `last_tick` timestamp
  (Redis or DB); alert if a worker goes silent > 2× its interval (detects a
  crashed/hung loop, which currently fails silently).
- **[P1] Schedule the self-test, don't only run at boot.** Run `selftest.run()`
  every few hours so schema drift introduced by a migration is caught even
  without a redeploy.
- **[P2] Circuit breaker for external services** (Gmail, FMP/Lumiscapital,
  Anthropic). After N consecutive failures, open the breaker, fast-fail, and
  surface a degraded-mode message instead of hammering a down dependency.
- **[P2] Dead-letter handling for events.** Failed event-consumer handlers
  currently log and drop. Persist failures for replay.

### Testing / CI
- **[P0] Integration tests per brain action.** The schema-drift bugs fixed on
  this date (Bill.is_paid, Goal.deadline, Task "COMPLETE", gmail.list_messages)
  all reached production because no test exercised those paths. Add a test that
  dispatches each `action_type` against a seeded test DB.
- **[P1] Model/migration drift check in CI.** Assert every model column has a
  matching migration and vice-versa; fail the build on drift.

### Work agent / math
- **[P1] Populate `AgentRun.tokens_used` / `cost_usd`.** Fields exist but the
  work agent doesn't record them — no visibility into per-session cost.
- **[P1] Rate-limit `/work`.** Background sessions call the LLM multiple times;
  cap concurrent/daily sessions per user to bound cost and abuse.
- **[P2] Stronger web research.** The DuckDuckGo instant-answer API is thin.
  Add a real search provider (Brave/SerpAPI) behind an env flag for richer
  multi-source research.
- **[P2] Idempotency for `/work`.** Dedupe identical in-flight tasks so a
  double-tap doesn't spawn two sessions.

### Features
- **[P1] Configurable email-watch action.** When a watched email arrives, let
  the user pre-choose: notify / archive / label / auto-draft reply (the inbox
  screenshot hinted at find/archive/delete options).
- **[P2] Recurring digests of work-agent findings** into the knowledge base so
  research compounds over time.
- **[P2] `/undo`** for the last reversible action (task create, bill add, etc.).

### Performance
- **[P2] Batch `focus_engine` queries.** It issues several sequential queries
  per user; combine where possible for the 7am broadcast at scale.
