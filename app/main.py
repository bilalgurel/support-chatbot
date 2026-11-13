"""Web channel: the chat API used by the website widget, the demo page and the admin page."""
import hmac

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from . import agent, config, db, limits

app = FastAPI(title="Support Chatbot")
app.add_middleware(
    CORSMiddleware, allow_origins=config.ALLOWED_ORIGINS, allow_methods=["POST", "GET"], allow_headers=["*"]
)
STATIC_DIR = config.BASE_DIR / "static"


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    message: str = Field(min_length=1, max_length=1000)


@app.post("/api/chat")
def chat(req: ChatRequest):
    if not config.LLM_MODEL:
        raise HTTPException(500, "LLM_MODEL is not set. Add it to your .env file.")
    if not limits.allow(f"web:{req.session_id}"):
        raise HTTPException(429, "You're sending messages very quickly. Please wait a moment.")
    conversation_id = db.get_or_create_conversation("web", req.session_id)
    result = agent.respond(conversation_id, req.message.strip())
    return {"reply": result["reply"], "needs_human": result["needs_human"]}


@app.get("/")
def demo_page():
    return FileResponse(STATIC_DIR / "demo.html")


@app.get("/widget.js")
def widget():
    return FileResponse(STATIC_DIR / "widget.js", media_type="application/javascript")


def require_admin(token: str | None) -> None:
    if not config.ADMIN_TOKEN:
        raise HTTPException(503, "ADMIN_TOKEN is not set. Add it to your .env file.")
    if not token or not hmac.compare_digest(token, config.ADMIN_TOKEN):
        raise HTTPException(401, "Invalid admin token.")


@app.get("/admin")
def admin_page():
    return FileResponse(STATIC_DIR / "admin.html")


@app.get("/admin/api/overview")
def admin_overview(x_admin_token: str | None = Header(default=None)):
    require_admin(x_admin_token)
    return db.overview()


@app.get("/admin/api/conversations/{conversation_id}")
def admin_transcript(conversation_id: int, x_admin_token: str | None = Header(default=None)):
    require_admin(x_admin_token)
    return {"messages": db.transcript(conversation_id)}
