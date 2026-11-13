"""Telegram channel. Run with:  python -m app.telegram_bot

Uses long polling, so it works from your own computer without a public URL.
The same assistant answers here and on the website.
"""
import logging
import time

import httpx

from . import agent, config, db, limits, tools

logger = logging.getLogger("support-chatbot.telegram")


def handle_update(update: dict, send) -> None:
    """Process one Telegram update. `send(chat_id, text)` delivers the reply."""
    message = update.get("message") or {}
    chat_id = (message.get("chat") or {}).get("id")
    text = (message.get("text") or "").strip()
    if not chat_id or not text:
        return
    if text.startswith("/start"):
        biz, _ = tools.load_business()
        send(chat_id, f"Hi! I'm the assistant for {biz['name']}. Ask me about our services, prices and opening hours, or book an appointment.")
        return
    if not limits.allow(f"telegram:{chat_id}"):
        send(chat_id, "You're sending messages very quickly. Please wait a moment.")
        return
    conversation_id = db.get_or_create_conversation("telegram", str(chat_id))
    result = agent.respond(conversation_id, text[:1000])
    send(chat_id, result["reply"])


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    if not config.TELEGRAM_BOT_TOKEN:
        raise SystemExit("TELEGRAM_BOT_TOKEN is not set. Add it to your .env file.")
    if not config.LLM_MODEL:
        raise SystemExit("LLM_MODEL is not set. Add it to your .env file.")
    base = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}"
    client = httpx.Client(timeout=40)

    def send(chat_id, text):
        client.post(f"{base}/sendMessage", json={"chat_id": chat_id, "text": text})

    offset = None
    print("Telegram bot is running. Press Ctrl+C to stop.")
    while True:
        try:
            params = {"timeout": 30, "allowed_updates": ["message"]}
            if offset is not None:
                params["offset"] = offset
            updates = client.get(f"{base}/getUpdates", params=params).json().get("result", [])
            for update in updates:
                offset = update["update_id"] + 1
                try:
                    handle_update(update, send)
                except Exception:
                    logger.exception("Failed to handle update")
        except httpx.HTTPError:
            logger.warning("Network problem, retrying in 5 seconds")
            time.sleep(5)


if __name__ == "__main__":
    main()
