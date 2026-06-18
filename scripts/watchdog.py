#!/usr/bin/env python3
"""
STARFIRE Watchdog — external self-healing pipeline.

Tails Railway logs in real time, detects errors via regex, saves context,
and invokes Claude Code to diagnose + fix. Runs OUTSIDE the Railway
container (on your local machine or a separate always-on instance) so it
works even when the app is fully crashed or stuck.

Usage:
    # Authenticate once (opens browser):
    railway login

    # Link to the starfire project (one-time, from repo root):
    railway link

    # Run the watchdog:
    python scripts/watchdog.py

Environment variables (optional overrides):
    WATCHDOG_COOLDOWN    — seconds between fix attempts for the same error class (default: 300)
    WATCHDOG_MAX_RETRIES — abort after N failed fixes for the same error (default: 3)
    WATCHDOG_SMOKE_CMD   — smoke-test command (default: python -m pytest tests/ -q)
    WATCHDOG_DRY_RUN     — set to "1" to log detections without invoking the fixer
"""
import os
import re
import sys
import json
import time
import subprocess
import logging
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [watchdog] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("watchdog")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ERROR_CONTEXT_FILE = PROJECT_ROOT / "error_context.txt"
FIX_LOG_FILE = PROJECT_ROOT / "watchdog_fixes.log"

COOLDOWN = int(os.environ.get("WATCHDOG_COOLDOWN", 300))
MAX_RETRIES = int(os.environ.get("WATCHDOG_MAX_RETRIES", 3))
SMOKE_CMD = os.environ.get("WATCHDOG_SMOKE_CMD", "python3 -m pytest tests/ -q")
DRY_RUN = os.environ.get("WATCHDOG_DRY_RUN", "") == "1"

# ── Error patterns ──────────────────────────────────────────────────────────
# Each tuple: (pattern_name, compiled_regex, severity)
# pattern_name is used as the error class for cooldown/retry tracking.

ERROR_PATTERNS = [
    ("http_500", re.compile(
        r"(HTTP/?\s*500|Internal Server Error|status[_\s]code[=:\s]*500)",
        re.IGNORECASE,
    ), "critical"),

    ("db_connection", re.compile(
        r"(OperationalError|connection\s+refused|could\s+not\s+connect\s+to\s+server"
        r"|connection\s+reset\s+by\s+peer|SSL\s+connection\s+has\s+been\s+closed"
        r"|asyncpg.*ConnectionDoesNotExistError)",
        re.IGNORECASE,
    ), "critical"),

    ("db_timeout", re.compile(
        r"(statement\s+timeout|canceling\s+statement\s+due\s+to\s+statement\s+timeout"
        r"|TimeoutError.*database)",
        re.IGNORECASE,
    ), "warning"),

    ("anthropic_error", re.compile(
        r"(anthropic\.\w*Error|credit\s+balance\s+is\s+too\s+low"
        r"|overloaded_error|rate_limit_error|invalid_request_error)",
        re.IGNORECASE,
    ), "critical"),

    ("redis_error", re.compile(
        r"(redis\.\w*Error|ConnectionError.*redis|WRONGPASS|NOAUTH)",
        re.IGNORECASE,
    ), "warning"),

    ("unhandled_exception", re.compile(
        r"(Traceback \(most recent call last\)|raise\s+\w+Error"
        r"|Unhandled\s+exception|FATAL|CRITICAL)",
        re.IGNORECASE,
    ), "critical"),

    ("oom_crash", re.compile(
        r"(Killed|OOMKilled|out\s+of\s+memory|MemoryError|Cannot\s+allocate\s+memory)",
        re.IGNORECASE,
    ), "critical"),

    ("import_error", re.compile(
        r"(ModuleNotFoundError|ImportError:\s+cannot\s+import)",
        re.IGNORECASE,
    ), "critical"),

    ("migration_error", re.compile(
        r"(alembic\.util\.exc\.\w+|FAILED.*alembic|Can't locate revision)",
        re.IGNORECASE,
    ), "critical"),
]

# Lines to ignore even if they match a pattern (noise from normal operation)
IGNORE_PATTERNS = [
    re.compile(r"selftest_check_failed", re.IGNORECASE),
    re.compile(r"sentinel_error.*category", re.IGNORECASE),
    re.compile(r"starfire_brain_retry", re.IGNORECASE),
]


# ── State tracking ──────────────────────────────────────────────────────────

class ErrorTracker:
    """Tracks per-error-class cooldowns and retry counts."""

    def __init__(self):
        self._last_triggered: dict[str, float] = {}
        self._retry_counts: dict[str, int] = defaultdict(int)
        self._aborted: set[str] = set()

    def should_act(self, error_class: str) -> bool:
        if error_class in self._aborted:
            return False
        now = time.monotonic()
        last = self._last_triggered.get(error_class, 0)
        return (now - last) >= COOLDOWN

    def record_attempt(self, error_class: str):
        self._last_triggered[error_class] = time.monotonic()
        self._retry_counts[error_class] += 1

    def record_success(self, error_class: str):
        self._retry_counts[error_class] = 0

    def check_abort(self, error_class: str) -> bool:
        if self._retry_counts[error_class] >= MAX_RETRIES:
            self._aborted.add(error_class)
            return True
        return False

    def reset(self, error_class: str):
        self._aborted.discard(error_class)
        self._retry_counts[error_class] = 0


tracker = ErrorTracker()


# ── Log buffer ──────────────────────────────────────────────────────────────

class LogBuffer:
    """Rolling window of recent log lines for error context."""

    def __init__(self, max_lines: int = 80):
        self._lines: list[str] = []
        self._max = max_lines

    def add(self, line: str):
        self._lines.append(line)
        if len(self._lines) > self._max:
            self._lines = self._lines[-self._max:]

    def context(self, around: int = 30) -> str:
        return "\n".join(self._lines[-around:])


log_buffer = LogBuffer()


# ── Core functions ──────────────────────────────────────────────────────────

def detect_error(line: str) -> tuple[str, str, str] | None:
    """Returns (error_class, severity, matched_text) or None."""
    for ignore in IGNORE_PATTERNS:
        if ignore.search(line):
            return None
    for name, pattern, severity in ERROR_PATTERNS:
        m = pattern.search(line)
        if m:
            return name, severity, m.group(0)
    return None


def save_error_context(error_class: str, severity: str, matched: str, context: str):
    """Write error context to error_context.txt for the fixer agent."""
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "error_class": error_class,
        "severity": severity,
        "matched_text": matched,
        "retry_count": tracker._retry_counts[error_class],
        "log_context": context,
    }
    ERROR_CONTEXT_FILE.write_text(json.dumps(payload, indent=2))
    log.info("Saved error context to %s", ERROR_CONTEXT_FILE)


def invoke_fixer(error_class: str) -> bool:
    """
    Invoke Claude Code in non-interactive mode to diagnose and fix the error.
    Returns True if the fix was applied and smoke tests passed.
    """
    prompt = f"""\
Read error_context.txt in the project root. It contains a Railway log error
that the watchdog detected (class: {error_class}).

Follow these rules strictly:

1. SCOPED ANALYSIS: Only read the file where the error occurred and its
   immediate imports/dependencies. Do not explore unrelated code.

2. HYPOTHESIS FIRST: Before changing any code, print a 2-sentence
   "Root Cause Analysis" explaining what went wrong and why.

3. DIFFS ONLY: Apply only the specific lines that fix the bug. Do not
   refactor, add comments, or change anything else.

4. VERIFY: After applying the fix, run: {SMOKE_CMD}
   If tests fail, revert your changes and report what went wrong.

5. If the fix passes, run these commands in sequence:
   git add -A
   git commit -m "fix: self-healing patch for {error_class}"
   git push -u origin claude/starfire-ai-os-QWLqi

6. After pushing, verify the deployment started:
   railway status

Do NOT attempt more than one fix strategy. If your first approach fails
the smoke test, revert and report — do not loop.
"""
    log.info("Invoking Claude Code for error class: %s", error_class)

    try:
        result = subprocess.run(
            ["claude", "-p", prompt, "--allowedTools",
             "Read,Edit,Write,Bash,Grep,Glob"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=300,
        )
        output = result.stdout + result.stderr
        success = result.returncode == 0 and "git push" in output.lower()

        with open(FIX_LOG_FILE, "a") as f:
            f.write(f"\n{'='*60}\n")
            f.write(f"[{datetime.now(timezone.utc).isoformat()}] {error_class}\n")
            f.write(f"exit_code={result.returncode} success={success}\n")
            f.write(output[-2000:] + "\n")

        if success:
            log.info("Fix applied and pushed for %s", error_class)
        else:
            log.warning("Fixer did not complete successfully for %s (exit %d)",
                        error_class, result.returncode)
        return success

    except subprocess.TimeoutExpired:
        log.error("Fixer timed out for %s", error_class)
        return False
    except FileNotFoundError:
        log.error("Claude Code CLI not found — install it or add to PATH")
        return False


def send_abort_alert(error_class: str):
    """Alert the operator that auto-fix has given up on this error class."""
    msg = (
        f"🛑 WATCHDOG ABORT: {error_class}\n"
        f"Failed {MAX_RETRIES} consecutive fix attempts.\n"
        f"Manual intervention required.\n"
        f"Context saved in: {ERROR_CONTEXT_FILE}"
    )
    log.critical(msg)

    # Try Telegram alert via the app's existing bot token
    try:
        import httpx
        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.environ.get("ADMIN_TELEGRAM_ID", "1001945255")
        if bot_token:
            httpx.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={"chat_id": chat_id, "text": msg, "parse_mode": "HTML"},
                timeout=10,
            )
    except Exception:
        pass


def handle_error(error_class: str, severity: str, matched: str):
    """Full error-handling pipeline: save context → invoke fixer → track."""
    if not tracker.should_act(error_class):
        return

    context = log_buffer.context()
    save_error_context(error_class, severity, matched, context)
    tracker.record_attempt(error_class)

    if tracker.check_abort(error_class):
        send_abort_alert(error_class)
        return

    if DRY_RUN:
        log.info("[DRY RUN] Would invoke fixer for %s", error_class)
        return

    success = invoke_fixer(error_class)
    if success:
        tracker.record_success(error_class)
    elif tracker.check_abort(error_class):
        send_abort_alert(error_class)


# ── Main loop ───────────────────────────────────────────────────────────────

def tail_railway_logs():
    """Stream Railway logs and process each line."""
    log.info("Starting Railway log tail (cooldown=%ds, max_retries=%d, dry_run=%s)",
             COOLDOWN, MAX_RETRIES, DRY_RUN)

    cmd = ["railway", "logs", "--tail"]
    while True:
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=str(PROJECT_ROOT),
            )
            log.info("Connected to Railway log stream (pid=%d)", proc.pid)

            for line in proc.stdout:
                line = line.rstrip("\n")
                if not line:
                    continue
                log_buffer.add(line)

                detection = detect_error(line)
                if detection:
                    error_class, severity, matched = detection
                    log.warning("Detected [%s] %s: %s",
                                severity.upper(), error_class, matched[:120])
                    handle_error(error_class, severity, matched)

            proc.wait()
            log.warning("Railway log stream ended (exit %d), reconnecting in 5s...",
                        proc.returncode)

        except KeyboardInterrupt:
            log.info("Shutting down watchdog")
            if proc and proc.poll() is None:
                proc.terminate()
            break
        except Exception as e:
            log.error("Log stream error: %s — retrying in 10s", e)

        time.sleep(10)


if __name__ == "__main__":
    tail_railway_logs()
