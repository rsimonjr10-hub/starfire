"""
STARFIRE Self-Test — boot-time smoke diagnostic.

Runs every feature's critical query path against the REAL database schema
shortly after startup. A query that references a missing column, a broken
join, or a renamed field raises immediately here — and is reported to the
admin via Telegram — instead of silently failing weeks later when a user
finally triggers that code path.

This is the layer that catches schema-drift / logic bugs that exception
monitoring (Sentinel) cannot see, because those bugs live in code paths
that have not executed yet.
"""
import asyncio
import structlog
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, func

from app.database import AsyncSessionLocal
from app.monitoring.sentinel import sentinel

logger = structlog.get_logger(__name__)

# Delay before running so the app, DB, and workers are fully up.
_STARTUP_DELAY_SECONDS = 45


class SelfTest:
    async def run_after_startup(self) -> None:
        await asyncio.sleep(_STARTUP_DELAY_SECONDS)
        try:
            await self.run()
        except Exception as e:
            logger.error("selftest_fatal", error=str(e))

    async def run(self) -> dict:
        checks = [
            ("model.task_query", self._check_task_query),
            ("model.goal_query", self._check_goal_query),
            ("model.bill_query", self._check_bill_query),
            ("model.spending_query", self._check_spending_query),
            ("model.email_watch_query", self._check_email_watch_query),
            ("model.agent_run_query", self._check_agent_run_query),
            ("service.focus_engine", self._check_focus_engine),
            ("service.bill_due_helper", self._check_bill_helper),
            ("logic.brain_json_parse", self._check_brain_parse),
            ("logic.math_engine", self._check_math_engine),
            ("logic.undo_recording", self._check_undo_recording),
            ("infra.worker_heartbeats", self._check_heartbeats),
        ]

        results: dict[str, str] = {}
        for name, fn in checks:
            try:
                await fn() if asyncio.iscoroutinefunction(fn) else fn()
                results[name] = "ok"
            except Exception as e:
                results[name] = f"FAIL: {type(e).__name__}: {e}"
                logger.error("selftest_check_failed", check=name, error=str(e))

        failures = {k: v for k, v in results.items() if v != "ok"}
        if failures:
            msg = (
                "🧪 <b>STARFIRE Self-Test — FAILURES</b>\n"
                f"{len(failures)}/{len(checks)} checks broken:\n\n"
                + "\n".join(f"• <b>{k}</b>\n  <code>{v[:200]}</code>" for k, v in failures.items())
                + "\n\nThese code paths will error when a user triggers them."
            )
            await sentinel._alert(msg)
            logger.error("selftest_failures", count=len(failures), failures=list(failures.keys()))
        else:
            logger.info("selftest_passed", checks=len(checks))

        return results

    # ── model query checks (validate columns exist against live schema) ───────

    async def _check_task_query(self):
        from app.models import Task
        async with AsyncSessionLocal() as s:
            now = datetime.now(timezone.utc)
            await s.execute(
                select(func.count(Task.id)).where(
                    Task.status == "DONE", Task.due_at < now,
                    Task.updated_at >= now - timedelta(days=7),
                )
            )

    async def _check_goal_query(self):
        from app.models import Goal
        async with AsyncSessionLocal() as s:
            now = datetime.now(timezone.utc)
            await s.execute(
                select(func.count(Goal.id)).where(
                    Goal.status == "ACTIVE",
                    Goal.target_date < now + timedelta(days=7),
                )
            )
            # progress fields used by work_agent
            await s.execute(select(Goal.current_value, Goal.target_value).limit(1))

    async def _check_bill_query(self):
        from app.models import Bill
        async with AsyncSessionLocal() as s:
            await s.execute(
                select(Bill.is_active, Bill.is_recurring, Bill.due_day,
                       Bill.due_date, Bill.last_paid_at, Bill.autopay,
                       Bill.amount).limit(1)
            )

    async def _check_spending_query(self):
        from app.models import SpendingRecord
        async with AsyncSessionLocal() as s:
            now = datetime.now(timezone.utc)
            await s.execute(
                select(func.sum(SpendingRecord.amount)).where(
                    SpendingRecord.recorded_at >= now - timedelta(days=7)
                )
            )

    async def _check_email_watch_query(self):
        from app.models.email_watch import EmailWatch
        async with AsyncSessionLocal() as s:
            await s.execute(
                select(EmailWatch.id, EmailWatch.query, EmailWatch.is_active,
                       EmailWatch.found_at, EmailWatch.matched_subject,
                       EmailWatch.on_match, EmailWatch.label_name).limit(1)
            )

    async def _check_agent_run_query(self):
        from app.models.agent_run import AgentRun
        async with AsyncSessionLocal() as s:
            await s.execute(
                select(AgentRun.id, AgentRun.agent_name, AgentRun.status,
                       AgentRun.input_data, AgentRun.report_text,
                       AgentRun.started_at, AgentRun.completed_at).limit(1)
            )

    # ── service-level checks ──────────────────────────────────────────────────

    async def _check_focus_engine(self):
        """Run the focus computation end-to-end for a real (or first) user."""
        from app.models import User
        from app.services.focus_engine import compute_daily_focus, format_daily_focus
        async with AsyncSessionLocal() as s:
            user = (await s.execute(select(User).limit(1))).scalar_one_or_none()
            if not user:
                return  # no users yet — nothing to validate
            focus = await compute_daily_focus(s, user.id)
            format_daily_focus(focus, user.first_name or "")

    def _check_bill_helper(self):
        """Validate the bill-due helper against synthetic bills (no DB)."""
        from app.services.focus_engine import _bill_due_soon

        class _B:
            def __init__(self, **kw):
                self.is_recurring = kw.get("is_recurring", True)
                self.due_day = kw.get("due_day")
                self.due_date = kw.get("due_date")
                self.last_paid_at = kw.get("last_paid_at")

        now = datetime.now(timezone.utc)
        # recurring bill due today, never paid → due soon
        assert _bill_due_soon(_B(due_day=now.day), now, window_days=1) is True
        # one-time bill far in the future → not due
        assert _bill_due_soon(
            _B(is_recurring=False, due_date=now + timedelta(days=30)), now
        ) is False

    # ── pure-logic checks (no DB/API) ─────────────────────────────────────────

    def _check_brain_parse(self):
        """The JSON-leak regression: prose + embedded action JSON must parse as action."""
        from app.starfire.brain import StarfireBrain
        brain = StarfireBrain.__new__(StarfireBrain)  # no API client needed
        mixed = 'Got it — let me pull those.\n\n{"action": "GET_EMAILS", "query": "from:x"}'
        parsed = brain._parse_response(mixed)
        assert parsed["type"] == "action", f"expected action, got {parsed['type']}"
        assert parsed["content"]["action"] == "GET_EMAILS"

    def _check_math_engine(self):
        from app.agents.work_agent import compute_math
        assert "2" in compute_math("solve(x**2 - 4, x)")  # roots include ±2
        assert compute_math("2 + 2") == "4"

    def _check_undo_recording(self):
        """_record_undo must stash a well-formed undo slot in user.preferences."""
        from app.starfire.decision import DecisionEngine

        class _U:
            id = 1
            preferences = {}

        eng = DecisionEngine.__new__(DecisionEngine)  # no DB needed for this call
        u = _U()
        eng._record_undo(u, "task", 99, "Test task")
        assert u.preferences["undo"]["kind"] == "task"
        assert u.preferences["undo"]["id"] == 99

    def _check_heartbeats(self):
        """Heartbeat registry must register and report a fresh beat as ok."""
        from app.monitoring import heartbeat
        heartbeat.beat("selftest_probe", 1.0)
        assert heartbeat.check().get("selftest_probe") == "ok"


selftest = SelfTest()
