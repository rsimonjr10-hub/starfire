import json
import re
import structlog
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from typing import Optional
from anthropic import AsyncAnthropic
from app.config import settings
from app.starfire.prompts import STARFIRE_SYSTEM_PROMPT

logger = structlog.get_logger(__name__)

MAX_HISTORY_MESSAGES = 20


class StarfireBrain:
    def __init__(self):
        self.client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.model = "claude-opus-4-8"

    def _build_system(self, context: Optional[str] = None) -> str:
        now = datetime.now(ZoneInfo("America/New_York"))
        tz_label = now.strftime("%Z")  # EDT or EST depending on daylight saving
        date_block = (
            f"## Current Date & Time ({tz_label} — always exact, never guess)\n"
            f"Date: {now.strftime('%A, %B %d, %Y')}\n"
            f"Time: {now.strftime('%I:%M %p')} {tz_label}\n"
            f"ISO:  {now.strftime('%Y-%m-%dT%H:%M:%S')}{now.strftime('%z')}"
        )
        parts = [date_block, STARFIRE_SYSTEM_PROMPT]
        if context:
            parts.append(context)
        return "\n\n".join(parts)

    async def think(
        self,
        user_message: str,
        conversation_history: list[dict],
        context: Optional[str] = None,
    ) -> dict:
        """
        Process a user message and return either a chat response or a structured action.

        Returns:
            {
                "type": "chat" | "action",
                "content": str | dict,
                "raw": str
            }
        """
        system = self._build_system(context)

        messages = self._trim_history(conversation_history) + [
            {"role": "user", "content": user_message}
        ]

        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=system,
                messages=messages,
            )
            raw = response.content[0].text.strip()
            return self._parse_response(raw)
        except Exception as e:
            logger.error("starfire_brain_error", error=str(e))
            return {
                "type": "chat",
                "content": "I encountered an issue processing that request. Please try again.",
                "raw": "",
            }

    def _parse_response(self, raw: str) -> dict:
        """Detect whether STARFIRE returned JSON action or plain chat text."""
        stripped = raw.strip()

        # Try direct JSON parse first
        if stripped.startswith("{"):
            try:
                data = json.loads(stripped)
                if "action" in data:
                    return {"type": "action", "content": data, "raw": raw}
            except json.JSONDecodeError:
                pass

        # Try extracting JSON from markdown code block
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(1))
                if "action" in data:
                    return {"type": "action", "content": data, "raw": raw}
            except json.JSONDecodeError:
                pass

        return {"type": "chat", "content": stripped, "raw": raw}

    def _trim_history(self, history: list[dict]) -> list[dict]:
        """Keep last N messages, always preserving role alternation."""
        if len(history) <= MAX_HISTORY_MESSAGES:
            return history
        trimmed = history[-MAX_HISTORY_MESSAGES:]
        # Ensure first message is from user
        while trimmed and trimmed[0]["role"] != "user":
            trimmed = trimmed[1:]
        return trimmed

    def append_to_history(
        self, history: list[dict], user_msg: str, assistant_msg: str
    ) -> list[dict]:
        """Append a user/assistant exchange to conversation history."""
        history = list(history)
        history.append({"role": "user", "content": user_msg})
        history.append({"role": "assistant", "content": assistant_msg})
        return history
