"""
STARFIRE Sentinel — self-healing error monitor.

Responsibilities:
- Capture exceptions with full context
- Rate-track errors per category and alert via Telegram when threshold hit
- Attempt auto-recovery for known transient failures
- Run periodic health checks across all subsystems
"""

import time
import asyncio
import traceback
import structlog
from collections import defaultdict, deque
from typing import Optional, Callable, Awaitable

logger = structlog.get_logger(__name__)

# How many errors of the same category in WINDOW seconds before alerting
_ERROR_THRESHOLD = 3
_WINDOW_SECONDS = 300       # 5 minutes
_ALERT_COOLDOWN = 1800      # 30 minutes between repeated alerts for same category


class Sentinel:
    def __init__(self):
        self._counts: dict[str, deque] = defaultdict(deque)
        self._last_alert: dict[str, float] = {}
        self._sentry_enabled = False
        self._admin_telegram_id: Optional[int] = None
        self._initialized = False

    def init(self, sentry_dsn: str = "", admin_telegram_id: int = None):
        """Call once at startup."""
        self._admin_telegram_id = admin_telegram_id

        if sentry_dsn:
            try:
                import sentry_sdk
                sentry_sdk.init(
                    dsn=sentry_dsn,
                    traces_sample_rate=0.05,
                    environment="production",
                )
                self._sentry_enabled = True
                logger.info("sentinel_sentry_enabled")
            except ImportError:
                logger.warning("sentinel_sentry_missing", note="pip install sentry-sdk")

        self._initialized = True
        logger.info("sentinel_initialized", sentry=self._sentry_enabled, admin_id=admin_telegram_id)

    # ── Error capture ────────────────────────────────────────────────────────

    async def capture(
        self,
        error: Exception,
        category: str,
        context: dict = None,
        user_telegram_id: int = None,
    ) -> None:
        """Record an error, send Sentry event, and Telegram-alert if rate exceeded."""
        ctx = context or {}
        logger.error(
            "sentinel_error",
            category=category,
            error=repr(error),
            **{k: v for k, v in ctx.items() if isinstance(v, (str, int, float, bool))},
        )

        # Forward to Sentry
        if self._sentry_enabled:
            try:
                import sentry_sdk
                with sentry_sdk.push_scope() as scope:
                    scope.set_tag("category", category)
                    for k, v in ctx.items():
                        scope.set_extra(k, v)
                    sentry_sdk.capture_exception(error)
            except Exception:
                pass

        # Rate tracking
        now = time.monotonic()
        bucket = self._counts[category]
        bucket.append(now)
        # Evict events outside the window
        while bucket and bucket[0] < now - _WINDOW_SECONDS:
            bucket.popleft()

        count = len(bucket)
        last = self._last_alert.get(category, 0)
        if count >= _ERROR_THRESHOLD and (now - last) > _ALERT_COOLDOWN:
            self._last_alert[category] = now
            tb = "".join(traceback.format_exception(type(error), error, error.__traceback__))[-800:]
            msg = (
                f"⚠️ <b>STARFIRE Sentinel Alert</b>\n"
                f"Category: <code>{category}</code>\n"
                f"Errors in last 5 min: {count}\n\n"
                f"<pre>{tb}</pre>"
            )
            await self._alert(msg, user_telegram_id)

        # Auto-redeploy at double the threshold — escalate beyond in-process recovery
        if count >= _ERROR_THRESHOLD * 2 and (now - last) > _ALERT_COOLDOWN:
            asyncio.create_task(
                self.self_redeploy(reason=f"{count} {category} errors in 5 min")
            )

    # ── Auto-recovery ────────────────────────────────────────────────────────

    async def try_recover(self, error: Exception, category: str) -> bool:
        """
        Attempt recovery for known transient failures.
        Returns True if recovery was attempted (caller should retry).
        """
        err_str = str(error).lower()
        err_type = type(error).__name__

        # Google auth token expired — force a refresh on next request
        if "invalid_grant" in err_str or "token has been expired" in err_str or "credentials" in err_str:
            logger.info("sentinel_recover_google_auth")
            return True  # caller retries; google SDK auto-refreshes credentials

        # Anthropic rate limit / timeout
        if "anthropic" in err_type.lower() or "overloaded" in err_str or "timeout" in err_str.lower():
            logger.info("sentinel_recover_api_backoff", wait=5)
            await asyncio.sleep(5)
            return True

        # Redis connection error — nothing to do at app level, will reconnect
        if "redis" in err_type.lower() or "connection refused" in err_str:
            logger.info("sentinel_recover_redis")
            await asyncio.sleep(2)
            return True

        return False

    # ── Health check ─────────────────────────────────────────────────────────

    async def health_check(self) -> dict:
        """
        Check all subsystems. Returns status dict.
        Sends Telegram alert for any degraded component.
        """
        from app.config import settings

        results: dict[str, str] = {}

        # Database
        try:
            from app.database import AsyncSessionLocal
            from sqlalchemy import text
            async with AsyncSessionLocal() as s:
                await s.execute(text("SELECT 1"))
            results["database"] = "ok"
        except Exception as e:
            results["database"] = f"ERROR: {e}"

        # Redis
        try:
            import redis.asyncio as aioredis
            r = aioredis.from_url(settings.redis_url, socket_connect_timeout=3)
            await r.ping()
            await r.aclose()
            results["redis"] = "ok"
        except Exception as e:
            results["redis"] = f"ERROR: {e}"

        # Anthropic API reachability
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get("https://api.anthropic.com")
            results["anthropic"] = "ok" if resp.status_code < 500 else f"HTTP {resp.status_code}"
        except Exception as e:
            results["anthropic"] = f"ERROR: {e}"

        # Telegram bot
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(
                    f"https://api.telegram.org/bot{settings.telegram_bot_token}/getMe"
                )
            results["telegram"] = "ok" if resp.json().get("ok") else "ERROR: bot unreachable"
        except Exception as e:
            results["telegram"] = f"ERROR: {e}"

        degraded = {k: v for k, v in results.items() if v != "ok"}
        if degraded:
            msg = (
                "🔴 <b>STARFIRE Health Check — Degraded</b>\n\n"
                + "\n".join(f"• <b>{k}</b>: <code>{v}</code>" for k, v in degraded.items())
            )
            await self._alert(msg)
        else:
            logger.info("sentinel_health_ok", results=results)

        return results

    # ── Self-redeploy ────────────────────────────────────────────────────────

    async def self_redeploy(self, reason: str = "") -> bool:
        """
        Trigger a Railway redeploy of this service.
        Called by the sentinel when persistent errors can't be recovered in-process.
        Returns True if redeploy was successfully triggered.
        """
        from app.config import settings
        token = settings.railway_token
        service_id = settings.railway_service_id
        env_id = settings.railway_environment_id

        if not all([token, service_id, env_id]):
            logger.warning("sentinel_redeploy_skipped", reason="Railway env vars not set")
            return False

        try:
            import httpx
            mutation = {
                "query": (
                    f'mutation {{ serviceInstanceRedeploy('
                    f'serviceId: "{service_id}", '
                    f'environmentId: "{env_id}") }}'
                )
            }
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    "https://backboard.railway.app/graphql/v2",
                    json=mutation,
                    headers={"Authorization": f"Bearer {token}"},
                )
            data = resp.json()
            if "errors" in data:
                logger.error("sentinel_redeploy_error", errors=data["errors"])
                return False
            logger.info("sentinel_redeploy_triggered", reason=reason)
            await self._alert(
                f"🔄 <b>STARFIRE Sentinel — Auto-Redeploy</b>\n"
                f"Triggered Railway redeploy.\nReason: {reason or 'persistent errors'}"
            )
            return True
        except Exception as e:
            logger.error("sentinel_redeploy_exception", error=str(e))
            return False

    # ── Internal ─────────────────────────────────────────────────────────────

    async def _alert(self, message: str, user_telegram_id: int = None) -> None:
        """Send Telegram message to admin or the active user."""
        target = user_telegram_id or self._admin_telegram_id
        if not target:
            logger.warning("sentinel_no_alert_target", message=message[:100])
            return
        try:
            from app.telegram.bot import send_notification
            await send_notification(int(target), message)
        except Exception as e:
            logger.error("sentinel_alert_failed", error=str(e))


# Global singleton
sentinel = Sentinel()
