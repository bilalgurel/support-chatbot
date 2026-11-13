# AI Customer Support Chatbot

A support assistant for a small business that answers customer questions, **books appointments**, collects contact details and **hands the chat to a person** when it should. The same assistant runs in a website chat widget and on Telegram.

The demo business is a fictional dental clinic. Everything about the business lives in two plain files, so adapting it to a salon, a restaurant or an agency takes minutes.

## What it does

- **Answers from the business's own information** (prices, hours, policies) and says so when it doesn't know, instead of guessing.
- **Remembers the conversation**, so customers don't have to repeat themselves.
- **Books appointments**: checks real availability, offers free times, books the slot and gives a confirmation code.
- **Collects leads** when someone wants a call back.
- **Hands off to a human** when the customer asks for a person, is upset, or wants something the bot is not allowed to do (cancellations, refunds, complaints).
- **Two channels, one brain**: an embeddable website widget and a Telegram bot. WhatsApp or Messenger can be added the same way.
- **Admin page**: conversations (flagged when a person is needed), full transcripts, appointments and leads.

## Built for reliability

- **Rules live in code, not in the prompt.** Opening hours, past dates, unknown services and incomplete phone numbers are all checked by the booking code. The model cannot book a slot that is not free.
- **No double bookings.** The database has a unique constraint on date and time.
- **Tool errors go back to the model**, so it can correct itself and offer another time.
- **Capped tool loop.** If the model keeps calling tools without answering, the chat is passed to a person.
- **Prompt-injection aware.** Customer messages are treated as data, and the model has no tool that can do damage.
- **Per-visitor rate limit** and message length limits.
- Works with **Google Gemini or Anthropic Claude**; no key or model name is hard-coded.

## Setup

Requires Python 3.10 or newer.

```bash
git clone <your-repo-url>
cd support-chatbot
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # Windows: copy .env.example .env
```

Open `.env` and fill in `LLM_MODEL`, your API key (`GEMINI_API_KEY` or `ANTHROPIC_API_KEY`) and `ADMIN_TOKEN`.

## Run the website channel

```bash
python -m uvicorn app.main:app --reload
```

- Demo site with the chat widget: http://localhost:8000
- Admin page: http://localhost:8000/admin

## Run the Telegram channel (optional)

1. In Telegram, open **@BotFather**, send `/newbot` and follow the steps. Copy the token it gives you.
2. Put it in `.env` as `TELEGRAM_BOT_TOKEN`.
3. In a second terminal:

```bash
python -m app.telegram_bot
```

Open your bot in Telegram and send `/start`. It uses long polling, so no public URL is needed.

## Try it

| Say this | What should happen |
|---|---|
| How much is a check-up? | Answers £45 from the business information |
| Do you take insurance? | Explains the receipt policy |
| Can I book a cleaning on Thursday afternoon? | Checks availability, offers real free times |
| (pick a time, give a name and phone) | Books it and gives a confirmation code |
| Do you offer braces? | Says it isn't sure and offers to ask the team |
| I want to cancel my appointment | Hands the chat to a person |
| I have a terrible toothache, what should I take? | No medical advice; suggests an emergency appointment |

Then open the admin page: the appointment, the flagged conversation and the transcript are all there. Book the same slot from a second browser (or Telegram) and the assistant will offer a different time.

## Add the widget to any website

```html
<script src="https://YOUR-SERVER/widget.js"
        data-title="Chat with us" data-color="#0f766e"
        data-greeting="Hi! How can I help?"></script>
```

Set `ALLOWED_ORIGINS` in `.env` to your website's address in production.

## Adapt it to another business

- `business/business.json`: name, time zone, opening hours, appointment length, bookable services.
- `business/knowledge.md`: everything the assistant should know, in plain text.

No code changes are needed.

## How it works

Each customer message goes through a short loop: the model either replies or asks for a tool (`get_available_slots`, `book_appointment`, `save_lead`, `handoff_to_human`). Tools run in Python, the result is given back to the model, and the loop continues until it replies. See `app/agent.py` and `app/tools.py`.

## Tests

```bash
pytest
```

The tests run offline with scripted model answers and cover availability rules, booking validation, double-booking protection, conversation memory, handoff, lead capture, the runaway-loop cap, both channels and admin access.

## Notes and limits

- This is a demo. In production, put the admin page behind real authentication and replace SQLite with your own database or calendar system.
- The whole knowledge file is sent to the model with every message, which suits a small business. For large document sets, use retrieval as in [doc-assistant](https://github.com/bilalgurel/doc-assistant).
- The rate limiter is in memory and resets when the server restarts.
