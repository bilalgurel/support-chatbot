"""Offline tests: the model is replaced by scripted answers, everything else is real."""
import json
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app import agent, config, db, limits, llm, main, telegram_bot, tools

MONDAY = datetime(2026, 11, 16, 8, 0)  # a Monday, before opening time


def say(text):
    return json.dumps({"tool": None, "args": {}, "reply": text})


def call(tool, **args):
    return json.dumps({"tool": tool, "args": args, "reply": ""})


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "LLM_MODEL", "test-model")
    monkeypatch.setattr(config, "ADMIN_TOKEN", "secret")
    monkeypatch.setattr(config, "RATE_LIMIT_PER_MINUTE", 50)
    limits.reset()


@pytest.fixture
def script(monkeypatch):
    """Queue model answers; records what the model was sent."""
    state = {"answers": [], "calls": []}

    def fake_complete(system, messages, model, max_tokens):
        state["calls"].append({"system": system, "messages": [dict(m) for m in messages]})
        return state["answers"].pop(0), {"input_tokens": 10, "output_tokens": 5}

    monkeypatch.setattr(llm, "complete", fake_complete)
    return state


def biz():
    return tools.load_business()[0]


def test_slots_follow_opening_hours_and_skip_booked_and_past_times():
    conv = db.get_or_create_conversation("web", "slots-test")
    monday = tools.get_available_slots(biz(), {"date": "2026-11-16"}, MONDAY)
    assert monday["slots"][0] == "09:00" and monday["slots"][-1] == "16:30"
    assert tools.get_available_slots(biz(), {"date": "2026-11-22"}, MONDAY)["slots"] == []  # Sunday
    assert tools.get_available_slots(biz(), {"date": "2026-11-15"}, MONDAY)["ok"] is False  # past
    assert tools.get_available_slots(biz(), {"date": "next monday"}, MONDAY)["ok"] is False

    db.insert_appointment("NW-TEST", conv, "A", "0700000000", "Check-up", "2026-11-16", "10:00")
    assert "10:00" not in tools.get_available_slots(biz(), {"date": "2026-11-16"}, MONDAY)["slots"]
    midday = tools.get_available_slots(biz(), {"date": "2026-11-16"}, datetime(2026, 11, 16, 12, 10))
    assert midday["slots"][0] == "12:30"


def test_booking_rules_are_enforced_in_code():
    conv = db.get_or_create_conversation("web", "rules-test")
    good = {"name": "Sam Lee", "phone": "07700 900123", "service": "check-up", "date": "2026-11-16", "time": "10:00"}
    assert "phone" in tools.book_appointment(biz(), conv, {**good, "phone": ""}, MONDAY)["error"]
    assert tools.book_appointment(biz(), conv, {**good, "phone": "123"}, MONDAY)["ok"] is False
    assert tools.book_appointment(biz(), conv, {**good, "service": "Brain surgery"}, MONDAY)["ok"] is False
    assert tools.book_appointment(biz(), conv, {**good, "time": "03:00"}, MONDAY)["ok"] is False   # closed
    assert tools.book_appointment(biz(), conv, {**good, "date": "2026-11-22"}, MONDAY)["ok"] is False  # Sunday

    first = tools.book_appointment(biz(), conv, good, MONDAY)
    assert first["ok"] and first["confirmation_code"].startswith("NW-") and first["service"] == "Check-up"
    second = tools.book_appointment(biz(), conv, good, MONDAY)
    assert second["ok"] is False  # same slot cannot be booked twice
    assert db.insert_appointment("NW-X", conv, "B", "0700000000", "Check-up", "2026-11-16", "10:00") is False


def test_full_booking_conversation_with_memory(script):
    conv = db.get_or_create_conversation("web", "booking-test")
    script["answers"] = [
        call("get_available_slots", date="2026-11-16"),
        say("We have 09:00, 09:30 and 10:00 on Monday. Which suits you, and can I take your name and phone number?"),
    ]
    first = agent.respond(conv, "Can I get a check-up on Monday?", MONDAY)
    assert "09:30" in first["reply"]
    # The tool result was passed back to the model before it answered.
    assert "TOOL RESULT for get_available_slots" in script["calls"][1]["messages"][-1]["content"]
    assert '"09:00"' in script["calls"][1]["messages"][-1]["content"]

    script["answers"] = [
        call("book_appointment", name="Sam Lee", phone="07700 900123", service="Check-up", date="2026-11-16", time="09:30"),
        say("You're booked for Monday at 09:30."),
    ]
    agent.respond(conv, "09:30 please. Sam Lee, 07700 900123", MONDAY)
    # The second turn saw the first turn: the assistant remembers the conversation.
    sent = [m["content"] for m in script["calls"][2]["messages"]]
    assert sent[0] == "Can I get a check-up on Monday?" and "09:30" in sent[1]

    appointments = db.overview()["appointments"]
    assert len(appointments) == 1 and appointments[0]["time"] == "09:30" and appointments[0]["name"] == "Sam Lee"
    assert "09:30" not in tools.get_available_slots(biz(), {"date": "2026-11-16"}, MONDAY)["slots"]
    assert "Monday 2026-11-16" in script["calls"][0]["system"]  # the model is told today's date


def test_tool_errors_go_back_to_the_model(script):
    conv = db.get_or_create_conversation("web", "error-test")
    script["answers"] = [
        call("book_appointment", name="Sam", phone="07700 900123", service="Check-up", date="2026-11-22", time="10:00"),
        say("Sorry, we're closed on Sundays. Would Monday work?"),
    ]
    result = agent.respond(conv, "Book me Sunday at 10", MONDAY)
    assert "closed" in result["reply"]
    assert '"ok": false' in script["calls"][1]["messages"][-1]["content"]
    assert db.overview()["appointments"] == []


def test_handoff_lead_and_runaway_tool_loop(script):
    conv = db.get_or_create_conversation("web", "handoff-test")
    script["answers"] = [call("handoff_to_human", reason="Wants to cancel"), say("I've asked the team to help you.")]
    result = agent.respond(conv, "I need to cancel my appointment", MONDAY)
    assert result["needs_human"] is True
    assert db.overview()["conversations"][0]["handoff_reason"] == "Wants to cancel"

    lead_conv = db.get_or_create_conversation("web", "lead-test")
    script["answers"] = [call("save_lead", name="Ana", contact="ana@example.com", note="Whitening"), say("Saved.")]
    agent.respond(lead_conv, "Please call me back about whitening", MONDAY)
    assert db.overview()["leads"][0]["contact"] == "ana@example.com"

    loop_conv = db.get_or_create_conversation("web", "loop-test")
    script["answers"] = [call("get_available_slots", date="2026-11-16")] * 10
    stuck = agent.respond(loop_conv, "hello", MONDAY)
    assert stuck["reply"] == agent.FALLBACK_REPLY and stuck["needs_human"] is True
    assert len(script["answers"]) == 10 - (config.MAX_TOOL_STEPS + 1)  # the loop is capped


def test_plain_text_and_fenced_answers_are_understood(script):
    assert agent.parse("Hello there")["reply"] == "Hello there"
    assert agent.parse('```json\n{"tool": null, "args": {}, "reply": "Hi"}\n```')["reply"] == "Hi"
    assert agent.parse('{"tool": "save_lead", "args": "oops"}') == {"tool": "save_lead", "args": {}, "reply": ""}
    conv = db.get_or_create_conversation("web", "unknown-tool")
    script["answers"] = [call("delete_everything"), say("I can't do that.")]
    agent.respond(conv, "hi", MONDAY)
    assert "Unknown tool" in script["calls"][1]["messages"][-1]["content"]


def test_model_failure_gives_a_polite_error(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("api down")

    monkeypatch.setattr(llm, "complete", boom)
    conv = db.get_or_create_conversation("web", "failure-test")
    assert agent.respond(conv, "hi", MONDAY)["reply"] == agent.ERROR_REPLY


def test_web_api_admin_and_rate_limit(script, monkeypatch):
    client = TestClient(main.app)
    script["answers"] = [say("We open at 9."), say("Yes, free parking.")]
    res = client.post("/api/chat", json={"session_id": "visitor-12345", "message": "When do you open?"})
    assert res.status_code == 200 and res.json() == {"reply": "We open at 9.", "needs_human": False}
    assert client.post("/api/chat", json={"session_id": "visitor-12345", "message": "Parking?"}).status_code == 200
    assert client.post("/api/chat", json={"session_id": "bad id!", "message": "x"}).status_code == 422
    assert client.get("/").status_code == 200 and client.get("/widget.js").status_code == 200

    assert client.get("/admin/api/overview").status_code == 401
    data = client.get("/admin/api/overview", headers={"X-Admin-Token": "secret"}).json()
    assert data["conversations"][0]["messages"] == 4
    transcript = client.get(f"/admin/api/conversations/{data['conversations'][0]['id']}", headers={"X-Admin-Token": "secret"}).json()
    assert [m["role"] for m in transcript["messages"]] == ["user", "assistant", "user", "assistant"]

    monkeypatch.setattr(config, "RATE_LIMIT_PER_MINUTE", 1)
    limits.reset()
    script["answers"] = [say("ok")]
    body = {"session_id": "visitor-99999", "message": "hi"}
    assert client.post("/api/chat", json=body).status_code == 200
    assert client.post("/api/chat", json=body).status_code == 429


def test_telegram_channel_uses_the_same_assistant(script):
    sent = []
    send = lambda chat_id, text: sent.append((chat_id, text))
    telegram_bot.handle_update({"message": {"chat": {"id": 42}, "text": "/start"}}, send)
    assert "Northwind Dental Clinic" in sent[0][1]
    script["answers"] = [say("A check-up costs £45.")]
    telegram_bot.handle_update({"message": {"chat": {"id": 42}, "text": "How much is a check-up?"}}, send)
    assert sent[1] == (42, "A check-up costs £45.")
    telegram_bot.handle_update({"message": {"chat": {"id": 42}}}, send)  # sticker etc: ignored
    assert len(sent) == 2
    assert db.overview()["conversations"][0]["channel"] == "telegram"
