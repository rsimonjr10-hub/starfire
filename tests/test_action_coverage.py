"""
Action coverage + regression tests.

These catch the classes of bug that reached production this week:
  1. An action documented in prompts.py with no handler in decision.py
     (the model is told to emit it, but nothing executes it).
  2. The brain failing to extract action JSON when mixed with prose
     (raw JSON leaking into the chat).
  3. Pure-logic regressions in the math engine, bill-due helper, and the
     /undo recording shape.

They run without a database or network — safe in CI and the sandbox.
"""
import re
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PROMPTS = ROOT / "app" / "starfire" / "prompts.py"
DECISION = ROOT / "app" / "starfire" / "decision.py"


# ── 1. Documented actions must have a handler ────────────────────────────────

def _documented_actions() -> set[str]:
    """Every action referenced as a JSON example in prompts.py."""
    text = PROMPTS.read_text()
    return set(re.findall(r'"action":\s*"([A-Z_]+)"', text))


def _handled_actions() -> set[str]:
    """Every action_type the decision engine branches on."""
    text = DECISION.read_text()
    handled = set(re.findall(r'action_type\s*==\s*"([A-Z_]+)"', text))
    # also tuple membership: action_type in ("A", "B")
    for grp in re.findall(r'action_type\s+in\s+\(([^)]*)\)', text):
        handled |= set(re.findall(r'"([A-Z_]+)"', grp))
    return handled


def test_every_documented_action_has_a_handler():
    documented = _documented_actions()
    handled = _handled_actions()
    # Actions intentionally handled elsewhere (routed/relayed) or generic
    allowlist = {"NOTIFY", "IGNORE", "CHAT"}
    missing = documented - handled - allowlist
    assert not missing, (
        f"Actions documented in prompts.py but not dispatched in decision.py: "
        f"{sorted(missing)}"
    )


def test_new_features_are_wired():
    """Lock in this session's features so they can't silently regress."""
    handled = _handled_actions()
    for action in ("WATCH_EMAIL", "START_WORK", "COMPUTE_MATH", "UNDO",
                   "GET_DAILY_FOCUS", "ANALYZE_DECISION", "BATCH",
                   "DELETE_EMAILS", "ARCHIVE_EMAILS", "MOVE_EMAILS",
                   "LIST_FOLDERS", "GET_FOLDER"):
        assert action in handled, f"{action} lost its handler"


def test_email_actions_are_routed_to_google():
    """Bulk/folder email actions must be in GOOGLE_ACTIONS or they never run."""
    from app.starfire.decision import GOOGLE_ACTIONS
    for action in ("DELETE_EMAILS", "ARCHIVE_EMAILS", "MOVE_EMAILS",
                   "LIST_FOLDERS", "GET_FOLDER", "READ_FOLDER"):
        assert action in GOOGLE_ACTIONS, f"{action} not routed to Google handler"


# ── 2. Brain extracts action JSON even when mixed with prose ──────────────────

@pytest.fixture
def brain():
    from app.starfire.brain import StarfireBrain
    return StarfireBrain.__new__(StarfireBrain)  # no API client needed


def test_pure_json_action(brain):
    r = brain._parse_response('{"action": "CREATE_TASK", "title": "x"}')
    assert r["type"] == "action" and r["content"]["action"] == "CREATE_TASK"


def test_code_block_action(brain):
    r = brain._parse_response('Sure:\n```json\n{"action": "UNDO"}\n```')
    assert r["type"] == "action" and r["content"]["action"] == "UNDO"


def test_prose_plus_embedded_action(brain):
    # The exact bug from the screenshot: narrative then JSON.
    mixed = 'Got it — pulling those now.\n\n{"action": "GET_EMAILS", "query": "from:x"}'
    r = brain._parse_response(mixed)
    assert r["type"] == "action" and r["content"]["action"] == "GET_EMAILS"


def test_plain_chat_is_not_an_action(brain):
    r = brain._parse_response("Here's a summary of your week. Nothing urgent.")
    assert r["type"] == "chat"


def test_non_action_json_is_chat(brain):
    r = brain._parse_response('{"name": "John", "age": 30}')
    assert r["type"] == "chat"


# ── Tool-use extraction (native execute_action path) ─────────────────────────

class _Block:
    def __init__(self, type, **kw):
        self.type = type
        for k, v in kw.items():
            setattr(self, k, v)


def test_tool_use_block_becomes_action(brain):
    blocks = [_Block("tool_use", name="execute_action",
                     input={"action": "ARCHIVE_EMAILS", "query": "from:x"})]
    r = brain._extract_from_blocks(blocks)
    assert r["type"] == "action"
    assert r["content"]["action"] == "ARCHIVE_EMAILS"
    assert r["content"]["query"] == "from:x"


def test_tool_use_preferred_over_text(brain):
    blocks = [
        _Block("text", text="On it."),
        _Block("tool_use", name="execute_action", input={"action": "UNDO"}),
    ]
    r = brain._extract_from_blocks(blocks)
    assert r["type"] == "action" and r["content"]["action"] == "UNDO"


def test_text_only_blocks_fall_back_to_legacy_parsing(brain):
    # legacy raw-JSON-in-text must still work during the transition
    blocks = [_Block("text", text='{"action": "CREATE_TASK", "title": "x"}')]
    r = brain._extract_from_blocks(blocks)
    assert r["type"] == "action" and r["content"]["action"] == "CREATE_TASK"
    blocks = [_Block("text", text="All quiet today — nothing urgent.")]
    assert brain._extract_from_blocks(blocks)["type"] == "chat"


def test_tool_use_without_action_field_is_ignored(brain):
    blocks = [
        _Block("tool_use", name="execute_action", input={"query": "x"}),  # malformed
        _Block("text", text="Hmm."),
    ]
    assert brain._extract_from_blocks(blocks)["type"] == "chat"


def test_system_prompt_static_block_first_for_caching(brain):
    """Cache prefix rule: the big static prompt MUST be block 0 with
    cache_control; volatile date/context comes after."""
    system = brain._build_system("## ctx")
    assert system[0]["cache_control"] == {"type": "ephemeral"}
    assert "STARFIRE" in system[0]["text"]
    assert "Current Date & Time" in system[1]["text"]
    assert "cache_control" not in system[1]


# ── History sanitization (the poison-pill that broke "archive everything") ────

def test_trim_history_drops_empty_messages(brain):
    """An empty assistant turn must be stripped — it 400s the API otherwise."""
    history = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": ""},        # poison from a failed think()
        {"role": "user", "content": "archive everything"},
    ]
    clean = brain._trim_history(history)
    assert all(m["content"].strip() for m in clean), "empty content survived"
    assert clean[0]["role"] == "user"


def test_trim_history_collapses_consecutive_roles(brain):
    history = [
        {"role": "user", "content": "a"},
        {"role": "user", "content": "b"},           # two users in a row
        {"role": "assistant", "content": "c"},
    ]
    clean = brain._trim_history(history)
    roles = [m["role"] for m in clean]
    assert roles == ["user", "assistant"]
    assert clean[0]["content"] == "b"  # keeps the newer same-role message


def test_append_to_history_skips_empty_assistant(brain):
    out = brain.append_to_history([], "do the thing", "")
    assert all(m["content"].strip() for m in out)
    assert [m["role"] for m in out] == ["user"]


# ── 3. Pure-logic regressions ────────────────────────────────────────────────

def test_math_engine_algebra_and_calculus():
    from app.agents.work_agent import compute_math
    assert compute_math("solve(x**2 - 4, x)") == "[-2, 2]"
    assert compute_math("2 + 2") == "4"
    # symbolic derivative must not raise
    assert "cos(x)" in compute_math("diff(sin(x)*x**2, x)")


def test_bill_due_soon_today_and_future():
    from datetime import datetime, timezone, timedelta
    from app.services.focus_engine import _bill_due_soon

    class B:
        def __init__(self, **kw):
            self.is_recurring = kw.get("is_recurring", True)
            self.due_day = kw.get("due_day")
            self.due_date = kw.get("due_date")
            self.last_paid_at = kw.get("last_paid_at")

    now = datetime.now(timezone.utc)
    assert _bill_due_soon(B(due_day=now.day), now, window_days=1) is True
    assert _bill_due_soon(B(is_recurring=False, due_date=now + timedelta(days=30)), now) is False


# ── Billing-error detection (out-of-credits must not look like a code bug) ────

def test_billing_error_detected():
    from app.starfire.brain import _is_billing_error
    e = Exception(
        "Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', "
        "'message': 'Your credit balance is too low to access the Anthropic API. "
        "Go to Plans & Billing to upgrade or purchase credits.'}}"
    )
    assert _is_billing_error(e) is True
    assert _is_billing_error(Exception("overloaded_error: 529")) is False
    assert _is_billing_error(Exception("rate_limit_error")) is False


def test_billing_category_is_critical_and_never_redeploys():
    from app.monitoring.sentinel import _CRITICAL_CATEGORIES, _NO_REDEPLOY_CATEGORIES
    assert "brain.billing" in _CRITICAL_CATEGORIES
    assert "brain.billing" in _NO_REDEPLOY_CATEGORIES
