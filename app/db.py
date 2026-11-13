"""SQLite storage: conversations, messages, appointments and leads."""
import sqlite3
import time
from contextlib import closing

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel TEXT NOT NULL,
    user_ref TEXT NOT NULL,
    needs_human INTEGER NOT NULL DEFAULT 0,
    handoff_reason TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    UNIQUE(channel, user_ref)
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL,
    role TEXT NOT NULL,              -- user, assistant, tool
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS appointments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL,
    conversation_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    phone TEXT NOT NULL,
    service TEXT NOT NULL,
    date TEXT NOT NULL,
    time TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(date, time)               -- the database itself refuses double bookings
);
CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    contact TEXT NOT NULL,
    note TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def stamp() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def connect() -> sqlite3.Connection:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DATA_DIR / "chatbot.db")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def get_or_create_conversation(channel: str, user_ref: str) -> int:
    with closing(connect()) as conn, conn:
        conn.execute(
            "INSERT OR IGNORE INTO conversations (channel, user_ref, created_at) VALUES (?,?,?)",
            (channel, user_ref, stamp()),
        )
        row = conn.execute(
            "SELECT id FROM conversations WHERE channel=? AND user_ref=?", (channel, user_ref)
        ).fetchone()
        return row["id"]


def add_message(conversation_id: int, role: str, content: str) -> None:
    with closing(connect()) as conn, conn:
        conn.execute(
            "INSERT INTO messages (conversation_id, role, content, created_at) VALUES (?,?,?,?)",
            (conversation_id, role, content, stamp()),
        )


def history(conversation_id: int, limit: int) -> list[dict]:
    """Last `limit` customer/assistant messages, oldest first. Tool notes are left out."""
    with closing(connect()) as conn:
        rows = conn.execute(
            "SELECT role, content FROM messages WHERE conversation_id=? AND role IN ('user','assistant')"
            " ORDER BY id DESC LIMIT ?",
            (conversation_id, limit),
        ).fetchall()
    return [dict(r) for r in reversed(rows)]


def set_needs_human(conversation_id: int, reason: str) -> None:
    with closing(connect()) as conn, conn:
        conn.execute(
            "UPDATE conversations SET needs_human=1, handoff_reason=? WHERE id=?",
            (reason[:300], conversation_id),
        )


def needs_human(conversation_id: int) -> bool:
    with closing(connect()) as conn:
        row = conn.execute("SELECT needs_human FROM conversations WHERE id=?", (conversation_id,)).fetchone()
    return bool(row and row["needs_human"])


def booked_times(date: str) -> set[str]:
    with closing(connect()) as conn:
        return {r["time"] for r in conn.execute("SELECT time FROM appointments WHERE date=?", (date,))}


def insert_appointment(code, conversation_id, name, phone, service, date, time_) -> bool:
    """Returns False if the slot was taken in the meantime."""
    try:
        with closing(connect()) as conn, conn:
            conn.execute(
                "INSERT INTO appointments (code, conversation_id, name, phone, service, date, time, created_at)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (code, conversation_id, name, phone, service, date, time_, stamp()),
            )
        return True
    except sqlite3.IntegrityError:
        return False


def insert_lead(conversation_id, name, contact, note) -> None:
    with closing(connect()) as conn, conn:
        conn.execute(
            "INSERT INTO leads (conversation_id, name, contact, note, created_at) VALUES (?,?,?,?,?)",
            (conversation_id, name, contact, note, stamp()),
        )


def overview() -> dict:
    with closing(connect()) as conn:
        conversations = conn.execute(
            """SELECT c.id, c.channel, c.user_ref, c.needs_human, c.handoff_reason, c.created_at,
                      (SELECT COUNT(*) FROM messages m WHERE m.conversation_id=c.id AND m.role!='tool') AS messages,
                      (SELECT content FROM messages m WHERE m.conversation_id=c.id AND m.role='user'
                       ORDER BY m.id DESC LIMIT 1) AS last_user_message
               FROM conversations c ORDER BY c.needs_human DESC, c.id DESC LIMIT 100"""
        ).fetchall()
        appointments = conn.execute("SELECT * FROM appointments ORDER BY date, time LIMIT 200").fetchall()
        leads = conn.execute("SELECT * FROM leads ORDER BY id DESC LIMIT 200").fetchall()
    return {
        "conversations": [dict(r) for r in conversations],
        "appointments": [dict(r) for r in appointments],
        "leads": [dict(r) for r in leads],
    }


def transcript(conversation_id: int) -> list[dict]:
    with closing(connect()) as conn:
        rows = conn.execute(
            "SELECT role, content, created_at FROM messages WHERE conversation_id=? ORDER BY id",
            (conversation_id,),
        ).fetchall()
    return [dict(r) for r in rows]
