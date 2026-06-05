"""
Worker heartbeat registry.

Each background worker records a timestamp every loop iteration. The health
worker checks the registry and alerts if a worker has gone silent for longer
than its expected interval — catching a crashed or hung loop, which otherwise
fails completely silently.

All workers run as asyncio tasks in a single process, so an in-process registry
is sufficient and avoids a Redis round-trip on every tick.
"""
import time
import structlog

logger = structlog.get_logger(__name__)

# name -> {"last": monotonic_ts, "interval": expected_seconds, "wall": epoch_ts}
_beats: dict[str, dict] = {}


def beat(name: str, interval_seconds: float) -> None:
    """Record that `name` just completed a loop iteration."""
    _beats[name] = {
        "last": time.monotonic(),
        "interval": interval_seconds,
        "wall": time.time(),
    }


def register(name: str, interval_seconds: float) -> None:
    """Register a worker before its first beat so absence is detectable."""
    if name not in _beats:
        _beats[name] = {"last": time.monotonic(), "interval": interval_seconds, "wall": time.time()}


def check(slack_factor: float = 2.5) -> dict[str, str]:
    """
    Return {name: status} for every registered worker.
    A worker is 'stale' if silent for > interval * slack_factor.
    """
    now = time.monotonic()
    results: dict[str, str] = {}
    for name, info in _beats.items():
        silent = now - info["last"]
        threshold = info["interval"] * slack_factor
        if silent > threshold:
            results[name] = f"STALE: silent {int(silent)}s (interval {int(info['interval'])}s)"
        else:
            results[name] = "ok"
    return results


def snapshot() -> dict[str, dict]:
    """Human-readable view of last-beat ages, for /health and diagnostics."""
    now = time.monotonic()
    return {
        name: {
            "seconds_since_beat": int(now - info["last"]),
            "interval": int(info["interval"]),
        }
        for name, info in _beats.items()
    }
