"""Base agent interface for all STARFIRE sub-agents."""
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

import structlog
from anthropic import AsyncAnthropic
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.agent_run import AgentRun
from app.models.user import User

logger = structlog.get_logger(__name__)


class BaseAgent(ABC):
    name: str = "base"
    description: str = ""

    def __init__(self):
        self.client = AsyncAnthropic(api_key=settings.anthropic_api_key)

    @abstractmethod
    async def run(self, db: AsyncSession, user: User, input_data: dict) -> dict:
        """Execute the agent. Returns {report_text, data, ...}."""

    async def execute(
        self,
        db: AsyncSession,
        user: User,
        input_data: dict,
        trigger: str = "manual",
    ) -> AgentRun:
        """Wrapper that records the run and handles errors."""
        run = AgentRun(
            user_id=user.id,
            agent_name=self.name,
            trigger=trigger,
            input_data=input_data,
            status="running",
        )
        db.add(run)
        await db.flush()

        t0 = time.monotonic()
        try:
            result = await self.run(db, user, input_data)
            run.status = "completed"
            run.output_data = {k: v for k, v in result.items() if k != "report_text"}
            run.report_text = result.get("report_text", "")
        except Exception as e:
            logger.error("agent_run_failed", agent=self.name, error=str(e))
            run.status = "failed"
            run.error = str(e)
            result = {"report_text": f"Agent {self.name} failed: {e}"}
        finally:
            elapsed = int((time.monotonic() - t0) * 1000)
            run.duration_ms = elapsed
            run.completed_at = datetime.now(timezone.utc)
            await db.commit()

        return run

    async def _llm(self, system: str, user_msg: str, max_tokens: int = 1500) -> str:
        msg = await self.client.messages.create(
            model="claude-opus-4-8",
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user_msg}],
        )
        return msg.content[0].text
