"""The actions the assistant can take. Every rule is enforced here in code, not by the model."""
import json
import re
import secrets
from datetime import date as date_cls
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from . import config, db

WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
MAX_DAYS_AHEAD = 60


def load_business() -> tuple[dict, str]:
    biz = json.loads((config.BUSINESS_DIR / "business.json").read_text(encoding="utf-8"))
    knowledge = (config.BUSINESS_DIR / "knowledge.md").read_text(encoding="utf-8")
    return biz, knowledge


def business_now(biz: dict) -> datetime:
    return datetime.now(ZoneInfo(biz["timezone"])).replace(tzinfo=None)


def _parse_date(value) -> date_cls | None:
    try:
        return datetime.strptime(str(value).strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def _slots_for(biz: dict, day: date_cls, now: datetime) -> list[str]:
    hours = biz["hours"].get(WEEKDAYS[day.weekday()])
    if not hours:
        return []
    step = timedelta(minutes=int(biz["slot_minutes"]))
    current = datetime.combine(day, datetime.strptime(hours[0], "%H:%M").time())
    end = datetime.combine(day, datetime.strptime(hours[1], "%H:%M").time())
    taken = db.booked_times(day.isoformat())
    slots = []
    while current + step <= end:
        label = current.strftime("%H:%M")
        if current > now and label not in taken:
            slots.append(label)
        current += step
    return slots


def get_available_slots(biz: dict, args: dict, now: datetime) -> dict:
    day = _parse_date(args.get("date"))
    if not day:
        return {"ok": False, "error": "date must be in YYYY-MM-DD format."}
    if day < now.date():
        return {"ok": False, "error": "That date is in the past."}
    if day > now.date() + timedelta(days=MAX_DAYS_AHEAD):
        return {"ok": False, "error": f"Bookings are only open {MAX_DAYS_AHEAD} days ahead."}
    slots = _slots_for(biz, day, now)
    if not slots:
        return {"ok": True, "date": day.isoformat(), "slots": [], "note": "Closed or fully booked on this day."}
    return {"ok": True, "date": day.isoformat(), "weekday": day.strftime("%A"), "slots": slots}


def book_appointment(biz: dict, conversation_id: int, args: dict, now: datetime) -> dict:
    name = str(args.get("name", "")).strip()[:100]
    phone = str(args.get("phone", "")).strip()[:40]
    service = str(args.get("service", "")).strip()[:100]
    time_ = str(args.get("time", "")).strip()
    day = _parse_date(args.get("date"))

    missing = [k for k, v in (("name", name), ("phone", phone), ("service", service)) if not v]
    if missing:
        return {"ok": False, "error": f"Ask the customer for: {', '.join(missing)}."}
    if len(re.sub(r"\D", "", phone)) < 7:
        return {"ok": False, "error": "The phone number looks incomplete. Ask the customer to confirm it."}
    if not day or not re.fullmatch(r"\d{2}:\d{2}", time_):
        return {"ok": False, "error": "date must be YYYY-MM-DD and time must be HH:MM."}
    known = {s["name"].lower(): s["name"] for s in biz["services"]}
    if service.lower() not in known:
        return {"ok": False, "error": f"Unknown service. Available: {', '.join(known.values())}."}
    if day < now.date() or day > now.date() + timedelta(days=MAX_DAYS_AHEAD):
        return {"ok": False, "error": "That date is outside the bookable range."}
    free = _slots_for(biz, day, now)
    if time_ not in free:
        return {"ok": False, "error": "That time is not available.", "free_slots": free[:8]}

    code = "NW-" + secrets.token_hex(2).upper()
    if not db.insert_appointment(code, conversation_id, name, phone, known[service.lower()], day.isoformat(), time_):
        return {"ok": False, "error": "That slot was just taken. Offer another time."}
    return {
        "ok": True,
        "confirmation_code": code,
        "service": known[service.lower()],
        "date": day.isoformat(),
        "weekday": day.strftime("%A"),
        "time": time_,
        "name": name,
    }


def save_lead(conversation_id: int, args: dict) -> dict:
    name = str(args.get("name", "")).strip()[:100]
    contact = str(args.get("contact", "")).strip()[:120]
    note = str(args.get("note", "")).strip()[:500]
    if not name or not contact:
        return {"ok": False, "error": "A name and a phone number or email are required."}
    db.insert_lead(conversation_id, name, contact, note)
    return {"ok": True, "saved": True}


def handoff_to_human(conversation_id: int, args: dict) -> dict:
    db.set_needs_human(conversation_id, str(args.get("reason", "")).strip() or "Requested by the assistant")
    return {"ok": True, "note": "The team has been notified and will reply in this chat."}


TOOL_NAMES = {"get_available_slots", "book_appointment", "save_lead", "handoff_to_human"}


def run_tool(name: str, args: dict, biz: dict, conversation_id: int, now: datetime) -> dict:
    if not isinstance(args, dict):
        args = {}
    if name == "get_available_slots":
        return get_available_slots(biz, args, now)
    if name == "book_appointment":
        return book_appointment(biz, conversation_id, args, now)
    if name == "save_lead":
        return save_lead(conversation_id, args)
    if name == "handoff_to_human":
        return handoff_to_human(conversation_id, args)
    return {"ok": False, "error": f"Unknown tool '{name}'."}
