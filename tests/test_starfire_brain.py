import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.starfire.brain import StarfireBrain


@pytest.fixture
def brain():
    return StarfireBrain()


def test_parse_chat_response(brain):
    result = brain._parse_response("Hello! How can I help you today?")
    assert result["type"] == "chat"
    assert "Hello" in result["content"]


def test_parse_action_response_direct_json(brain):
    json_str = '{"action": "CREATE_TASK", "message": "Task created", "title": "Buy groceries"}'
    result = brain._parse_response(json_str)
    assert result["type"] == "action"
    assert result["content"]["action"] == "CREATE_TASK"


def test_parse_action_response_in_markdown(brain):
    response = 'Sure! Here it is:\n```json\n{"action": "TRADE", "symbol": "AAPL", "side": "BUY", "size_pct": 5.0, "message": "Buying AAPL"}\n```'
    result = brain._parse_response(response)
    assert result["type"] == "action"
    assert result["content"]["action"] == "TRADE"


def test_parse_non_action_json_is_chat(brain):
    json_str = '{"name": "John", "age": 30}'
    result = brain._parse_response(json_str)
    assert result["type"] == "chat"


def test_trim_history_within_limit(brain):
    history = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]
    trimmed = brain._trim_history(history)
    assert trimmed == history


def test_trim_history_over_limit(brain):
    history = []
    for i in range(25):
        history.append({"role": "user", "content": f"msg {i}"})
        history.append({"role": "assistant", "content": f"reply {i}"})

    trimmed = brain._trim_history(history)
    assert len(trimmed) <= 20
    assert trimmed[0]["role"] == "user"


def test_append_to_history(brain):
    history = []
    updated = brain.append_to_history(history, "Hello", "Hi there!")
    assert len(updated) == 2
    assert updated[0]["role"] == "user"
    assert updated[1]["role"] == "assistant"


def test_append_preserves_original(brain):
    original = [{"role": "user", "content": "first"}]
    brain.append_to_history(original, "second", "reply")
    assert len(original) == 1  # original not mutated
