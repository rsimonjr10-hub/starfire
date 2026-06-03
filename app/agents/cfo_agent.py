"""
CFO Agent — financial intelligence, forecasting, and wealth optimization.

Analyzes spending, investments, cash flow, and business revenue to produce
actionable financial recommendations.
"""
import json
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, func as sqlfunc
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import BaseAgent
from app.models.user import User
from app.models.spending import SpendingRecord
from app.models.goal import Goal
from app.models.bill import Bill
from app.models.net_worth_snapshot import NetWorthSnapshot
from app.models.business import Business, Invoice


class CFOAgent(BaseAgent):
    name = "cfo"
    description = "Financial intelligence — spending analysis, forecasting, wealth optimization"

    async def run(self, db: AsyncSession, user: User, input_data: dict) -> dict:
        ctx = await self._gather_financial_data(db, user)

        system = (
            "You are the CFO Agent for STARFIRE OS — a world-class financial intelligence system. "
            "Analyze the user's financial data and produce a CFO-level briefing with specific, "
            "actionable recommendations. Be quantitative. Identify opportunities and risks."
        )

        user_msg = f"""Analyze this financial snapshot and produce a CFO Report:

{json.dumps(ctx, indent=2, default=str)}

Produce:
1. **Cash Flow Summary** — income vs expenses, savings rate
2. **Spending Analysis** — top categories, anomalies, optimization opportunities
3. **Wealth Trajectory** — net worth trend, projection to goals
4. **Business Performance** — MRR, outstanding invoices (if applicable)
5. **Top 3 CFO Recommendations** — specific, numbered, actionable
6. **Risk Flags** — anything that needs immediate attention

Use numbers. Flag risks with ⚠️. Highlight wins with ✅."""

        report = await self._llm(system, user_msg, max_tokens=2000)
        return {"report_text": report, "financial_data": ctx}

    async def _gather_financial_data(self, db: AsyncSession, user: User) -> dict:
        now = datetime.now(timezone.utc)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        last_month = (month_start - timedelta(days=1)).replace(day=1)

        # Spending this month + last month
        spend_this = (await db.execute(
            select(SpendingRecord.category, sqlfunc.sum(SpendingRecord.amount).label("t"))
            .where(SpendingRecord.user_id == user.id, SpendingRecord.recorded_at >= month_start)
            .group_by(SpendingRecord.category).order_by(sqlfunc.sum(SpendingRecord.amount).desc())
        )).all()

        spend_last = (await db.execute(
            select(sqlfunc.sum(SpendingRecord.amount))
            .where(SpendingRecord.user_id == user.id,
                   SpendingRecord.recorded_at >= last_month,
                   SpendingRecord.recorded_at < month_start)
        )).scalar()

        # Bills
        bills = (await db.execute(
            select(Bill).where(Bill.user_id == user.id, Bill.is_active == True)
        )).scalars().all()

        # Goals
        goals = (await db.execute(
            select(Goal).where(Goal.user_id == user.id, Goal.status == "ACTIVE")
        )).scalars().all()

        # Net worth history (last 3 snapshots)
        nw_history = (await db.execute(
            select(NetWorthSnapshot)
            .where(NetWorthSnapshot.user_id == user.id)
            .order_by(NetWorthSnapshot.snapshot_date.desc())
            .limit(3)
        )).scalars().all()

        # Business
        businesses = (await db.execute(
            select(Business).where(Business.user_id == user.id)
        )).scalars().all()

        outstanding = (await db.execute(
            select(sqlfunc.sum(Invoice.amount))
            .where(Invoice.user_id == user.id, Invoice.status.in_(["sent", "overdue"]))
        )).scalar()

        return {
            "spending_this_month": [{"category": r.category, "total": float(r.t)} for r in spend_this],
            "total_spending_this_month": sum(float(r.t) for r in spend_this),
            "total_spending_last_month": float(spend_last or 0),
            "monthly_bills": sum(float(b.amount) for b in bills if b.is_recurring),
            "bills": [{"name": b.name, "amount": float(b.amount)} for b in bills],
            "active_goals": [
                {"title": g.title, "current": float(g.current_value or 0),
                 "target": float(g.target_value or 0), "unit": g.unit}
                for g in goals
            ],
            "net_worth_history": [
                {"date": str(n.snapshot_date), "net_worth": float(n.net_worth or 0),
                 "assets": float(n.total_assets or 0), "liabilities": float(n.total_liabilities or 0)}
                for n in nw_history
            ],
            "businesses": [
                {"name": b.name, "mrr": float(b.mrr or 0), "arr": float(b.arr or 0)}
                for b in businesses
            ],
            "outstanding_invoices_usd": float(outstanding or 0),
            "budget_json": user.budget_json or {},
        }
