"""
WorkAgent — autonomous background research and analysis agent.

Capabilities:
  - Web research via DuckDuckGo + page fetch
  - Full math engine: arithmetic, algebra, calculus, statistics, finance (sympy + numpy)
  - User data: tasks, goals, bills, spending, memory
  - Knowledge base (RAG)

Runs as a detached asyncio task. Notifies via Telegram when done.
"""
import asyncio
import json
import re
import textwrap
from datetime import datetime, timezone
from typing import Optional

import httpx
import structlog
from sqlalchemy import select, func

from app.agents.base import BaseAgent
from app.database import AsyncSessionLocal
from app.models.user import User
from app.models.agent_run import AgentRun

logger = structlog.get_logger(__name__)

# ─── math sandbox ────────────────────────────────────────────────────────────

_SAFE_MATH_GLOBALS = {"__builtins__": {}}

def _build_math_ns() -> dict:
    import math, statistics
    ns = {
        # standard math
        "math": math, "pi": math.pi, "e": math.e, "inf": math.inf,
        "sqrt": math.sqrt, "log": math.log, "log10": math.log10,
        "sin": math.sin, "cos": math.cos, "tan": math.tan,
        "floor": math.floor, "ceil": math.ceil, "abs": abs,
        "round": round, "pow": pow, "min": min, "max": max, "sum": sum,
        # statistics
        "statistics": statistics,
        "mean": statistics.mean, "median": statistics.median,
        "stdev": statistics.stdev, "variance": statistics.variance,
    }
    try:
        import numpy as np
        ns["np"] = np
        ns["array"] = np.array
        ns["linspace"] = np.linspace
        ns["arange"] = np.arange
        ns["dot"] = np.dot
        ns["norm"] = np.linalg.norm
    except ImportError:
        pass
    try:
        import sympy as sp
        ns["sp"] = sp
        ns["symbols"] = sp.symbols
        ns["solve"] = sp.solve
        ns["diff"] = sp.diff
        ns["integrate"] = sp.integrate
        ns["simplify"] = sp.simplify
        ns["expand"] = sp.expand
        ns["factor"] = sp.factor
        ns["Rational"] = sp.Rational
        ns["oo"] = sp.oo
        ns["Matrix"] = sp.Matrix
        ns["N"] = sp.N          # numerical evaluation
        ns["latex"] = sp.latex  # pretty-print
    except ImportError:
        pass
    return ns

_MATH_NS = _build_math_ns()


def compute_math(expression: str) -> str:
    """
    Execute a Python math expression in a safe namespace.
    Supports sympy (algebra/calculus), numpy, and standard math.
    Returns stringified result or error message.
    """
    try:
        globs = {"__builtins__": {}}
        globs.update(_MATH_NS)
        result = eval(compile(expression, "<math>", "eval"), globs)
        if hasattr(result, "__class__") and "sympy" in type(result).__module__:
            try:
                import sympy as sp
                return f"{result}  ≈  {float(sp.N(result, 6))}"
            except Exception:
                return str(result)
        if hasattr(result, "tolist"):  # numpy array
            return str(result.tolist())
        return str(result)
    except Exception as e:
        return f"Math error: {e}"


# ─── web research ─────────────────────────────────────────────────────────────

_DDG_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; Starfire/1.0)"}


async def web_search(query: str, max_results: int = 5) -> list[dict]:
    """DuckDuckGo instant-answer API — no key needed."""
    try:
        url = "https://api.duckduckgo.com/"
        params = {"q": query, "format": "json", "no_html": "1", "skip_disambig": "1"}
        async with httpx.AsyncClient(timeout=15, headers=_DDG_HEADERS) as client:
            r = await client.get(url, params=params)
        data = r.json()
        results = []
        if data.get("AbstractText"):
            results.append({
                "title": data.get("Heading", query),
                "snippet": data["AbstractText"][:600],
                "url": data.get("AbstractURL", ""),
            })
        for item in (data.get("RelatedTopics") or [])[:max_results]:
            if isinstance(item, dict) and item.get("Text"):
                results.append({
                    "title": item.get("Text", "")[:80],
                    "snippet": item.get("Text", "")[:400],
                    "url": item.get("FirstURL", ""),
                })
        return results[:max_results]
    except Exception as e:
        logger.warning("web_search_error", query=query, error=str(e))
        return []


async def fetch_page(url: str, max_chars: int = 3000) -> str:
    """Fetch a URL and return plain text (strips HTML tags)."""
    try:
        async with httpx.AsyncClient(timeout=20, headers=_DDG_HEADERS,
                                     follow_redirects=True) as client:
            r = await client.get(url)
        html = r.text
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()
            text = soup.get_text(separator="\n", strip=True)
        except ImportError:
            text = re.sub(r"<[^>]+>", " ", html)
            text = re.sub(r"\s+", " ", text).strip()
        return text[:max_chars]
    except Exception as e:
        return f"[fetch error: {e}]"


# ─── WorkAgent ───────────────────────────────────────────────────────────────

_PLAN_SYSTEM = """You are the STARFIRE Work Agent planner. Given a task, output a JSON plan.

Rules:
- Break into 2-6 concrete steps
- Each step has: name, type (RESEARCH|COMPUTE|USER_DATA|KNOWLEDGE|ANALYZE|WRITE), and params
- RESEARCH: {"query": "search terms"} — web search
- COMPUTE: {"expression": "python math code using sympy/numpy"} — math computation
  Examples: "solve(x**2 - 4, x)", "diff(sin(x), x)", "N(integrate(x**2, (x,0,1)))", "np.array([1,2,3]).mean()"
- USER_DATA: {"what": "tasks|goals|spending|bills|memory"} — pull user's personal data
- KNOWLEDGE: {"query": "..."} — search user's knowledge base
- ANALYZE: {"question": "..."} — reason over accumulated context
- WRITE: {"format": "report|summary|bullets"} — synthesize final output

Output ONLY valid JSON:
{
  "plan_title": "...",
  "steps": [
    {"name": "...", "type": "...", "params": {...}}
  ]
}"""

_SYNTH_SYSTEM = """You are STARFIRE — a personal AI chief of staff.
You have just completed a multi-step research and analysis task.
Synthesize all findings into a clear, well-structured final report.
Be direct, specific, and useful. Use markdown formatting. Include any math results.
If you computed formulas, show the work and the final answer.
End with concrete next steps or recommendations."""


class WorkAgent(BaseAgent):
    name = "work"
    description = "Autonomous background research, math, and analysis agent"

    async def run(self, db, user: User, input_data: dict) -> dict:
        task = input_data.get("task", "")
        if not task:
            return {"report_text": "No task provided."}

        plan_raw = await self._llm(_PLAN_SYSTEM, f"Task: {task}", max_tokens=800)
        try:
            plan = json.loads(re.search(r"\{[\s\S]*\}", plan_raw).group())
        except Exception:
            plan = {"plan_title": task, "steps": [{"name": "Analyze", "type": "ANALYZE", "params": {"question": task}}]}

        steps = plan.get("steps", [])
        context_parts: list[str] = [f"Task: {task}\n"]

        for i, step in enumerate(steps):
            step_name = step.get("name", f"Step {i+1}")
            step_type = step.get("type", "ANALYZE")
            params = step.get("params", {})

            try:
                result = await self._execute_step(step_type, params, db, user)
            except Exception as e:
                result = f"[step error: {e}]"

            context_parts.append(f"[{step_name}]\n{result}\n")
            logger.info("work_step_done", task=task[:60], step=step_name, type=step_type)

        full_context = "\n".join(context_parts)
        report = await self._llm(_SYNTH_SYSTEM, full_context, max_tokens=3000)

        return {"report_text": report, "task": task, "steps_run": len(steps)}

    async def _execute_step(self, step_type: str, params: dict, db, user: User) -> str:
        if step_type == "RESEARCH":
            query = params.get("query", "")
            results = await web_search(query, max_results=4)
            if not results:
                return f"No web results for: {query}"
            parts = []
            for r in results:
                parts.append(f"**{r['title']}**\n{r['snippet']}")
                if r.get("url") and len(parts) == 1:
                    extra = await fetch_page(r["url"], max_chars=2000)
                    if extra and not extra.startswith("[fetch error"):
                        parts[-1] += f"\n\n{extra[:1500]}"
            return "\n\n---\n".join(parts)

        if step_type == "COMPUTE":
            expression = params.get("expression", "")
            return f"Expression: `{expression}`\nResult: {compute_math(expression)}"

        if step_type == "USER_DATA":
            return await self._pull_user_data(params.get("what", "all"), db, user)

        if step_type == "KNOWLEDGE":
            query = params.get("query", "")
            try:
                from app.services.rag import build_rag_context
                ctx = await build_rag_context(db, user.id, query, max_chars=3000)
                return ctx or "No relevant knowledge found."
            except Exception as e:
                return f"Knowledge base unavailable: {e}"

        if step_type in ("ANALYZE", "WRITE"):
            # Will be used in synthesis — just return the question as context
            return params.get("question", params.get("format", ""))

        return f"Unknown step type: {step_type}"

    async def _pull_user_data(self, what: str, db, user: User) -> str:
        from sqlalchemy import select
        from datetime import timedelta
        lines = []
        now = datetime.now(timezone.utc)

        if what in ("tasks", "all"):
            from app.models.task import Task
            result = await db.execute(
                select(Task).where(Task.user_id == user.id, Task.status == "PENDING")
                .order_by(Task.due_at.asc().nullslast()).limit(15)
            )
            tasks = result.scalars().all()
            if tasks:
                lines.append(f"**Open Tasks ({len(tasks)})**")
                for t in tasks:
                    due = f" (due {t.due_at.date()})" if t.due_at else ""
                    lines.append(f"- {t.title}{due}")

        if what in ("goals", "all"):
            from app.models.goal import Goal
            result = await db.execute(
                select(Goal).where(Goal.user_id == user.id, Goal.status == "ACTIVE").limit(10)
            )
            goals = result.scalars().all()
            if goals:
                lines.append(f"\n**Active Goals ({len(goals)})**")
                for g in goals:
                    pct = ""
                    if g.target_value and float(g.target_value) != 0:
                        ratio = float(g.current_value or 0) / float(g.target_value) * 100
                        pct = f" ({ratio:.0f}%)"
                    lines.append(f"- {g.title}{pct}")

        if what in ("spending", "all"):
            from app.models.spending import SpendingRecord
            from sqlalchemy import func
            start = now - timedelta(days=30)
            result = await db.execute(
                select(func.sum(SpendingRecord.amount), func.count())
                .where(SpendingRecord.user_id == user.id, SpendingRecord.recorded_at >= start)
            )
            row = result.one()
            if row[0]:
                lines.append(f"\n**Spending (last 30d):** ${float(row[0]):.2f} across {row[1]} transactions")

        if what in ("bills", "all"):
            from app.models.bill import Bill
            result = await db.execute(
                select(Bill).where(Bill.user_id == user.id, Bill.is_active == True)
            )
            bills = result.scalars().all()
            if bills:
                total = sum(float(b.amount) for b in bills)
                lines.append(f"\n**Bills:** {len(bills)} active, ~${total:.2f}/month total")

        if what in ("memory", "all"):
            from app.models.memory import UserMemory
            result = await db.execute(
                select(UserMemory).where(UserMemory.user_id == user.id, UserMemory.is_active == True)
                .order_by(UserMemory.importance.desc()).limit(10)
            )
            memories = result.scalars().all()
            if memories:
                lines.append(f"\n**Key Facts ({len(memories)})**")
                for m in memories:
                    lines.append(f"- {m.content}")

        return "\n".join(lines) if lines else "No data found."


# ─── background runner (called from decision.py) ──────────────────────────────

async def run_work_background(run_id: int, user_id: int, telegram_id: int, task: str) -> None:
    """
    Runs in a detached asyncio task. Opens its own DB session,
    executes the work, updates AgentRun, and notifies via Telegram.
    """
    from app.telegram.bot import send_notification

    try:
        async with AsyncSessionLocal() as db:
            user = (await db.execute(
                select(User).where(User.id == user_id)
            )).scalar_one_or_none()
            if not user:
                return

            agent = WorkAgent()
            result = await agent.run(db, user, {"task": task})

            run = (await db.execute(
                select(AgentRun).where(AgentRun.id == run_id)
            )).scalar_one_or_none()
            if run:
                run.status = "completed"
                run.report_text = result.get("report_text", "")
                run.completed_at = datetime.now(timezone.utc)
                await db.commit()

        report = result.get("report_text", "No output.")
        header = f"Work complete — *{task[:60]}{'...' if len(task)>60 else ''}*\n\n"
        # Telegram messages cap at 4096 chars; split if needed
        full = header + report
        for chunk in _split_message(full):
            await send_notification(telegram_id, chunk)
            await asyncio.sleep(0.3)

    except Exception as e:
        logger.error("work_agent_background_error", user_id=user_id, error=str(e))
        try:
            from app.telegram.bot import send_notification
            await send_notification(telegram_id, f"Work session failed: {e}")
        except Exception:
            pass


def _split_message(text: str, limit: int = 3800) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks = []
    while text:
        if len(text) <= limit:
            chunks.append(text)
            break
        split = text.rfind("\n", 0, limit)
        if split == -1:
            split = limit
        chunks.append(text[:split])
        text = text[split:].lstrip()
    return chunks
