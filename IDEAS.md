# STARFIRE — Ideas & Improvements

Proactive backlog of features, optimizations, and architectural improvements.
Append here (don't dump into chat). Keep entries dated, prioritized, concrete.

Priority: **P0** ship now · **P1** soon · **P2** nice-to-have

---

## Shipped

- **2026-06-05 — Per-action test coverage.** `tests/test_action_coverage.py`:
  every documented action must have a handler, brain extracts action JSON from
  prose, math/bill/undo pure-logic regressions. Live-schema coverage stays in
  `app/monitoring/selftest.py`.
- **2026-06-05 — Worker heartbeats.** `app/monitoring/heartbeat.py`; workers
  beat each tick; health worker alerts on a stalled loop.
- **2026-06-05 — Configurable email-watch actions.** `on_match` =
  notify / archive / label / delete, executed when a watched email arrives.
- **2026-06-05 — `/undo`.** Reverses the last reversible action (task, bill,
  spending, memory, habit, knowledge, email-watch, task completion).

---

## 2026-06-05 — seeded from monitoring/self-heal work

### Reliability & self-healing
- **[P1] Wire `sentinel.capture()` into `handlers.py` command handlers.** Many
  Telegram command handlers still log-only or reply with an error string; a
  failing command never reaches the admin alert path. Mirror the worker/agent
  wiring done on this date.
- **[P1] Schedule the self-test, don't only run at boot.** Run `selftest.run()`
  every few hours so schema drift introduced by a migration is caught even
  without a redeploy.
- **[P2] Circuit breaker for external services** (Gmail, FMP/Lumiscapital,
  Anthropic). After N consecutive failures, open the breaker, fast-fail, and
  surface a degraded-mode message instead of hammering a down dependency.
- **[P2] Dead-letter handling for events.** Failed event-consumer handlers
  currently log and drop. Persist failures for replay.

### Testing / CI
- **[P1] Seeded-DB integration tests.** The static coverage test catches
  unhandled actions; add Postgres-backed tests that actually dispatch each
  DB-writing action end-to-end (sandbox lacks Postgres, so run in CI/Docker).
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
- **[P1] Auto-draft reply** as an email-watch `on_match` option (the basic
  notify/archive/label/delete actions shipped 2026-06-05).
- **[P2] Recurring digests of work-agent findings** into the knowledge base so
  research compounds over time.

### Performance
- **[P2] Batch `focus_engine` queries.** It issues several sequential queries
  per user; combine where possible for the 7am broadcast at scale.

## 2026-06-09 — Architecture review (critical audit)

### Reliability
- **[P0] Migrate brain from "emit raw JSON" to native Anthropic tool use.**
  Eliminates the entire _parse_response / _repair_json / brace-walking layer
  and the JSON-leak + fake-success bug class. Each action becomes a tool
  schema; unhandled actions become impossible at the API level.
- **[P0] Fix dead auto-redeploy in sentinel.capture().** The redeploy branch
  reuses `_last_alert`, which the alert branch just set — condition can never
  be true. Needs a separate `_last_redeploy` tracker.
- **[P1] Replace draft re-extraction with a stashed pending action.** Store
  the action dict in `user.preferences["pending_action"]` when a STEP-1 draft
  is shown; execute it directly on confirmation. Removes a fragile Haiku call.

### Cost / latency
- **[P0] Prompt caching.** Upgrade `anthropic` (0.28.0 → current), reorder
  system blocks so the static 9.3k-token prompt comes FIRST (date block last),
  add `cache_control`. ~90% input-token cut on the static prefix.
- **[P1] Narration discipline.** GET_EMAILS/READ_EMAIL/_fetch_and_analyze make
  a second full-system brain call to narrate results. Use Haiku with a tiny
  system prompt for narration, or skip when the formatted payload suffices.
- **[P2] Lazy context build.** `_build_context` runs ~8 queries on every
  message regardless of relevance.

### Maintainability
- **[P2] Dispatch registry.** Replace the 2,500-line if-elif chain in
  decision.py with an action→handler dict; coverage test derives from it.
