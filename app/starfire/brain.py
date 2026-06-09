import asyncio
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

# Native tool-use entry point for actions. Calling this tool is the only way
# the model can act, which makes malformed action JSON and "fake success"
# replies (claiming an action ran without executing it) structurally
# impossible. Action names + fields are documented in the system prompt;
# legacy raw-JSON-in-text output is still parsed as a fallback.
EXECUTE_ACTION_TOOL = {
    "name": "execute_action",
    "description": (
        "Execute a STARFIRE action (Gmail, Calendar, tasks, bills, trading, "
        "watches, agents...). Use the exact action names and fields documented "
        "in the system prompt, e.g. {\"action\": \"CREATE_TASK\", \"title\": ...}. "
        "This tool is the ONLY way to actually do something — never state that "
        "an action was performed without calling it."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Action type in CAPS, e.g. GET_EMAILS, WATCH_EMAIL, BATCH",
            },
        },
        "required": ["action"],
        "additionalProperties": True,
    },
}


class StarfireBrain:
    def __init__(self):
        self.client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.model = "claude-opus-4-8"

    def _build_system(self, context: Optional[str] = None) -> list[dict]:
        """
        System prompt as content blocks, ordered for prompt caching:
        the large STATIC prompt comes first with a cache breakpoint, and all
        volatile content (timestamp, per-user context) comes after it.
        Putting the timestamp first would change the prefix every minute and
        guarantee zero cache hits on ~9k tokens per call.
        """
        now = datetime.now(ZoneInfo("America/New_York"))
        tz_label = now.strftime("%Z")  # EDT or EST depending on daylight saving
        date_block = (
            f"## Current Date & Time ({tz_label} — always exact, never guess)\n"
            f"Date: {now.strftime('%A, %B %d, %Y')}\n"
            f"Time: {now.strftime('%I:%M %p')} {tz_label}\n"
            f"ISO:  {now.strftime('%Y-%m-%dT%H:%M:%S')}{now.strftime('%z')}"
        )
        dynamic_parts = [date_block]
        if context:
            dynamic_parts.append(context)
        return [
            {
                "type": "text",
                "text": STARFIRE_SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            },
            {"type": "text", "text": "\n\n".join(dynamic_parts)},
        ]

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

        trimmed = self._trim_history(conversation_history)
        # If the history ends with a user message (because the previous assistant
        # turn failed and was never stored), drop that trailing user entry so we
        # don't send two consecutive user messages to the Anthropic API (which
        # causes a 400 and re-enters this failure loop on every subsequent call).
        if trimmed and trimmed[-1]["role"] == "user":
            trimmed = trimmed[:-1]
        messages = trimmed + [{"role": "user", "content": user_message}]

        last_exc: Optional[Exception] = None
        for attempt in range(2):
            try:
                response = await self.client.messages.create(
                    model=self.model,
                    max_tokens=4096,
                    system=system,
                    messages=messages,
                    tools=[EXECUTE_ACTION_TOOL],
                )
                return self._extract_from_blocks(response.content)
            except Exception as e:
                last_exc = e
                err_type = type(e).__name__
                err_str = str(e).lower()
                logger.error("starfire_brain_error", attempt=attempt + 1,
                             error=str(e), error_type=err_type)
                # Retry once on transient server/rate errors; fail fast on auth/bad-request
                _transient = (
                    "ratelimit" in err_type.lower() or "rate_limit" in err_str or
                    "overloaded" in err_str or "529" in str(e) or
                    "timeout" in err_type.lower() or "timeout" in err_str or
                    "serviceunavailable" in err_type.lower() or
                    "internalserver" in err_type.lower()
                )
                if _transient and attempt == 0:
                    logger.info("starfire_brain_retry", wait=8)
                    await asyncio.sleep(8)
                    continue
                break

        # Both attempts failed — route through Sentinel so it can alert + track
        try:
            from app.monitoring.sentinel import sentinel
            await sentinel.capture(
                last_exc,
                category="brain.think",   # critical category → alerts on first occurrence
                context={"msg": user_message[:200], "attempts": 2},
            )
        except Exception as alert_err:
            logger.error("sentinel_alert_failed", error=str(alert_err))
        return {
            "type": "chat",
            "content": "I encountered an issue processing that request. Please try again.",
            "raw": "",
        }

    @staticmethod
    def _repair_json(s: str) -> str:
        """Escape literal newlines/tabs inside JSON string values so json.loads won't choke."""
        result = []
        in_string = False
        i = 0
        while i < len(s):
            c = s[i]
            if c == '"' and (i == 0 or s[i - 1] != "\\"):
                in_string = not in_string
                result.append(c)
            elif in_string and c == "\n":
                result.append("\\n")
            elif in_string and c == "\r":
                result.append("\\r")
            elif in_string and c == "\t":
                result.append("\\t")
            else:
                result.append(c)
            i += 1
        return "".join(result)

    def _try_parse_json(self, s: str) -> Optional[dict]:
        """Try json.loads, then retry with repaired string. Return dict or None."""
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            pass
        try:
            return json.loads(self._repair_json(s))
        except json.JSONDecodeError:
            return None

    def _extract_from_blocks(self, blocks: list) -> dict:
        """
        Turn an API response (list of content blocks) into a chat/action dict.
        Preferred path: a tool_use block from execute_action — guaranteed-valid
        JSON straight from the API. Fallback: legacy raw-JSON-in-text parsing,
        so older prompt behaviour keeps working during the transition.
        """
        for b in blocks:
            if getattr(b, "type", None) == "tool_use" and getattr(b, "name", "") == "execute_action":
                data = dict(b.input or {})
                if "action" in data:
                    logger.info("brain_action_detected", action=data.get("action"),
                                parsed_via="tool_use")
                    return {"type": "action", "content": data, "raw": json.dumps(data)}
        text = "".join(
            getattr(b, "text", "") for b in blocks if getattr(b, "type", None) == "text"
        ).strip()
        return self._parse_response(text)

    def _parse_response(self, raw: str) -> dict:
        """Detect whether STARFIRE returned JSON action or plain chat text."""
        stripped = raw.strip()

        # 1. Direct JSON parse (response is pure JSON)
        if stripped.startswith("{"):
            data = self._try_parse_json(stripped)
            if data and "action" in data:
                logger.info("brain_action_detected", action=data.get("action"), parsed_via="direct_json")
                return {"type": "action", "content": data, "raw": raw}

        # 2. JSON inside a markdown code block
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, re.DOTALL)
        if match:
            data = self._try_parse_json(match.group(1))
            if data and "action" in data:
                logger.info("brain_action_detected", action=data.get("action"), parsed_via="code_block")
                return {"type": "action", "content": data, "raw": raw}

        # 3. JSON embedded in prose (Claude sometimes mixes narrative + action JSON)
        #    Walk every '{' in the response and try to extract a valid action object.
        for m in re.finditer(r"\{", stripped):
            start = m.start()
            depth = 0
            end = -1
            for i, ch in enumerate(stripped[start:], start):
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        end = i + 1
                        break
            if end == -1:
                continue
            candidate = stripped[start:end]
            if '"action"' not in candidate:
                continue
            data = self._try_parse_json(candidate)
            if data and "action" in data:
                logger.info("brain_action_detected", action=data.get("action"), parsed_via="embedded_json")
                return {"type": "action", "content": data, "raw": raw}

        logger.info("brain_chat_response", preview=stripped[:120])
        return {"type": "chat", "content": stripped, "raw": raw}

    def _trim_history(self, history: list[dict]) -> list[dict]:
        """
        Keep the last N messages as a VALID Anthropic message list:
        - drop any message with empty/whitespace content (the API 400s on these,
          which previously poisoned the whole conversation)
        - collapse consecutive same-role messages, keeping the latest
        - ensure the list starts with a user message
        """
        # 1. Keep only well-formed, non-empty messages
        clean: list[dict] = []
        for m in history:
            role = m.get("role")
            content = m.get("content")
            if role not in ("user", "assistant"):
                continue
            if not isinstance(content, str) or not content.strip():
                continue
            clean.append({"role": role, "content": content})

        # 2. Trim to the window
        if len(clean) > MAX_HISTORY_MESSAGES:
            clean = clean[-MAX_HISTORY_MESSAGES:]

        # 3. Enforce strict user/assistant alternation (Anthropic requirement)
        alternating: list[dict] = []
        for m in clean:
            if alternating and alternating[-1]["role"] == m["role"]:
                alternating[-1] = m  # replace with the newer same-role message
            else:
                alternating.append(m)

        # 4. Must start with a user message
        while alternating and alternating[0]["role"] != "user":
            alternating.pop(0)

        return alternating

    async def narrate(self, instruction: str, data: str) -> str:
        """
        Cheap one-shot narration over already-fetched data (email lists, market
        quotes, docs). Uses Haiku with a tiny system prompt instead of a second
        full-system Opus call — same UX at a fraction of the cost and latency.
        Returns "" on any failure; callers fall back to the formatted data.
        """
        try:
            response = await self.client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=1024,
                system=(
                    "You are STARFIRE, a concise personal chief of staff. "
                    "Comment on the provided data per the instruction. "
                    "Plain text only — no JSON, no markdown headers, max 3 short paragraphs."
                ),
                messages=[{"role": "user", "content": f"{instruction}\n\nData:\n{data[:4000]}"}],
            )
            return "".join(
                getattr(b, "text", "") for b in response.content
                if getattr(b, "type", None) == "text"
            ).strip()
        except Exception as e:
            logger.error("narrate_error", error=str(e))
            return ""

    async def extract_action_from_draft(self, draft_message: str) -> Optional[dict]:
        """Given a STEP 1 draft shown to the user, extract the action JSON via a targeted call."""
        prompt = (
            "The user just confirmed the following draft. "
            "Output ONLY the raw JSON action object — no prose, no markdown, no explanation.\n\n"
            f"Draft:\n{draft_message}"
        )
        try:
            response = await self.client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=1024,
                system=(
                    "You are a JSON extractor. Read the draft and output exactly one JSON object "
                    "with an 'action' field (e.g. SEND_EMAIL, ROUTE_TRADE). "
                    "Include all relevant fields (to, subject, body, etc.). "
                    "Output raw JSON only — no text before or after."
                ),
                messages=[{"role": "user", "content": prompt}],
            )
            raw = response.content[0].text.strip()
            logger.info("extract_action_raw", preview=raw[:120])
            return self._try_parse_json(raw)
        except Exception as e:
            logger.error("extract_action_error", error=str(e))
            return None

    def append_to_history(
        self, history: list[dict], user_msg: str, assistant_msg: str
    ) -> list[dict]:
        """
        Append a user/assistant exchange to conversation history.

        Never stores empty content — an empty assistant turn (e.g. from a failed
        think() that returns raw="") would 400 the Anthropic API on the next
        call and poison the whole conversation.
        """
        history = list(history)
        if user_msg and user_msg.strip():
            history.append({"role": "user", "content": user_msg})
        if assistant_msg and assistant_msg.strip():
            history.append({"role": "assistant", "content": assistant_msg})
        return history
