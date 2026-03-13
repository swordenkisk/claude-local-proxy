"""
server.py — FastAPI application for claude-local-proxy.

Endpoints
---------
GET  /                         → Chat UI (HTML)
GET  /health                   → Health check JSON
POST /v1/chat                  → Chat completion (non-streaming)
POST /v1/chat/stream           → Chat completion (SSE streaming)
GET  /v1/conversations         → List conversations
POST /v1/conversations         → Create conversation
GET  /v1/conversations/{id}    → Get conversation details
PUT  /v1/conversations/{id}    → Update conversation title
DELETE /v1/conversations/{id}  → Delete conversation
GET  /v1/conversations/{id}/messages  → Get messages
POST /v1/conversations/{id}/messages  → Add message + get AI reply
GET  /v1/conversations/{id}/export    → Export as JSON
GET  /v1/models                → List available models

Usage:
    python -m src.server
    # or:
    uvicorn src.server:app --host 127.0.0.1 --port 8080
"""

import json
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import (
    Depends, FastAPI, HTTPException, Request,
    Response, Cookie,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import (
    HTMLResponse, JSONResponse, StreamingResponse,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from . import config, database as db
from .auth import check_api_auth, check_ui_auth
from .providers import get_provider


# ── Rate limiter (in-memory, per IP) ─────────────────────────────

_rate_counters: dict[str, list[float]] = defaultdict(list)


def _rate_ok(ip: str) -> bool:
    """Return True if the IP is within the rate limit."""
    limit = config.RATE_LIMIT_PER_MINUTE
    if limit <= 0:
        return True
    now  = time.monotonic()
    hits = _rate_counters[ip]
    # Remove hits older than 60 seconds
    hits[:] = [t for t in hits if now - t < 60.0]
    if len(hits) >= limit:
        return False
    hits.append(now)
    return True


# ── Lifespan ──────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(application: FastAPI):
    # Ensure DB + data dir exist on startup
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)

    warnings = config.validate()
    for w in warnings:
        print(f"[WARN] {w}")

    print(f"[INFO] claude-local-proxy starting on http://{config.BIND_ADDR}:{config.PORT}")
    print(f"[INFO] Provider: {config.API_PROVIDER}  |  Model: {config.DEFAULT_MODEL}")
    if config.UI_AUTH_TOKEN:
        print(f"[INFO] Auth enabled — append ?token=<your-token> to the URL")
    else:
        print(f"[INFO] Auth disabled (local-only mode)")

    yield


# ── App setup ─────────────────────────────────────────────────────

app = FastAPI(
    title       = "Claude Local Proxy",
    description = "Local web UI and API proxy for Anthropic Claude",
    version     = "1.0.0",
    lifespan    = lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins  = ["*"],
    allow_methods  = ["*"],
    allow_headers  = ["*"],
)

# Static files
if config.STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(config.STATIC_DIR)), name="static")

# Templates
templates = Jinja2Templates(directory=str(config.TEMPLATES_DIR))


# ── Pydantic models ───────────────────────────────────────────────

class MessageIn(BaseModel):
    role   : str = Field(..., pattern="^(user|assistant|system)$")
    content: str


class ChatRequest(BaseModel):
    messages      : list[MessageIn]
    model         : str  = ""
    max_tokens    : int  = 0    # 0 = use server default
    system_prompt : str  = ""
    stream        : bool = False
    conversation_id: Optional[str] = None


class ConversationCreate(BaseModel):
    title        : str = "New conversation"
    model        : str = ""
    system_prompt: str = ""


class ConversationUpdate(BaseModel):
    title: str


class SendMessage(BaseModel):
    content       : str
    model         : str  = ""
    max_tokens    : int  = 0
    stream        : bool = False


# ── Helpers ───────────────────────────────────────────────────────

def _max_tokens(requested: int) -> int:
    return requested if requested > 0 else config.MAX_TOKENS


def _ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    return (forwarded.split(",")[0] if forwarded
            else (request.client.host if request.client else "unknown"))


# ── UI route ─────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def ui(
    request  : Request,
    auth_token: Optional[str] = Depends(check_ui_auth),
):
    """Serve the single-page chat UI."""
    response = templates.TemplateResponse(
        "index.html",
        {
            "request"      : request,
            "default_model": config.DEFAULT_MODEL,
            "models"       : config.ANTHROPIC_MODELS,
            "provider"     : config.API_PROVIDER,
            "auth_enabled" : bool(config.UI_AUTH_TOKEN),
        },
    )
    if auth_token and config.UI_AUTH_TOKEN:
        response.set_cookie("claude_auth", auth_token, httponly=True, samesite="strict")
    return response


# ── Health ────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {
        "status"   : "ok",
        "provider" : config.API_PROVIDER,
        "model"    : config.DEFAULT_MODEL,
        "auth"     : bool(config.UI_AUTH_TOKEN),
    }


# ── Models ────────────────────────────────────────────────────────

@app.get("/v1/models", dependencies=[Depends(check_api_auth)])
async def list_models():
    return {"models": config.ANTHROPIC_MODELS}


# ── Chat (non-streaming) ──────────────────────────────────────────

@app.post("/v1/chat", dependencies=[Depends(check_api_auth)])
async def chat(req: ChatRequest, request: Request):
    ip = _ip(request)
    if not _rate_ok(ip):
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Try again in a moment.")

    try:
        provider = get_provider()
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e))

    messages = [m.model_dump() for m in req.messages]
    system   = req.system_prompt or config.SYSTEM_PROMPT

    try:
        result = await provider.chat(
            messages      = messages,
            model         = req.model or config.DEFAULT_MODEL,
            max_tokens    = _max_tokens(req.max_tokens),
            system_prompt = system,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Provider error: {e}")

    return result.to_dict()


# ── Chat (streaming SSE) ──────────────────────────────────────────

@app.post("/v1/chat/stream", dependencies=[Depends(check_api_auth)])
async def chat_stream(req: ChatRequest, request: Request):
    ip = _ip(request)
    if not _rate_ok(ip):
        raise HTTPException(status_code=429, detail="Rate limit exceeded.")

    try:
        provider = get_provider()
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e))

    messages = [m.model_dump() for m in req.messages]
    system   = req.system_prompt or config.SYSTEM_PROMPT

    async def event_generator():
        try:
            async for chunk in provider.stream(
                messages      = messages,
                model         = req.model or config.DEFAULT_MODEL,
                max_tokens    = _max_tokens(req.max_tokens),
                system_prompt = system,
            ):
                if chunk.startswith("[DONE]"):
                    yield f"data: {chunk}\n\n"
                else:
                    yield f"data: {json.dumps({'text': chunk})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control"   : "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ── Conversations ─────────────────────────────────────────────────

@app.get("/v1/conversations", dependencies=[Depends(check_api_auth)])
async def list_convs():
    return {"conversations": await db.list_conversations()}


@app.post("/v1/conversations", dependencies=[Depends(check_api_auth)])
async def create_conv(body: ConversationCreate):
    conv = await db.create_conversation(
        title         = body.title,
        model         = body.model,
        system_prompt = body.system_prompt,
    )
    return conv


@app.get("/v1/conversations/{conv_id}", dependencies=[Depends(check_api_auth)])
async def get_conv(conv_id: str):
    conv = await db.get_conversation(conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return conv


@app.put("/v1/conversations/{conv_id}", dependencies=[Depends(check_api_auth)])
async def update_conv(conv_id: str, body: ConversationUpdate):
    ok = await db.update_conversation_title(conv_id, body.title)
    if not ok:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return {"ok": True}


@app.delete("/v1/conversations/{conv_id}", dependencies=[Depends(check_api_auth)])
async def delete_conv(conv_id: str):
    ok = await db.delete_conversation(conv_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return {"ok": True}


@app.get("/v1/conversations/{conv_id}/messages", dependencies=[Depends(check_api_auth)])
async def get_msgs(conv_id: str):
    conv = await db.get_conversation(conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    msgs = await db.get_messages(conv_id)
    return {"messages": msgs}


@app.post("/v1/conversations/{conv_id}/messages", dependencies=[Depends(check_api_auth)])
async def send_message(conv_id: str, body: SendMessage, request: Request):
    """
    Add a user message and stream back the assistant reply.
    Saves both messages to the database.
    """
    ip = _ip(request)
    if not _rate_ok(ip):
        raise HTTPException(status_code=429, detail="Rate limit exceeded.")

    conv = await db.get_conversation(conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found.")

    # Save user message
    await db.add_message(conv_id, "user", body.content)

    # Build message history for the provider
    history = await db.get_messages(conv_id)
    messages = [
        {"role": m["role"], "content": m["content"]}
        for m in history
        if m["role"] in ("user", "assistant")
    ]

    model   = body.model or conv.get("model") or config.DEFAULT_MODEL
    system  = conv.get("system_prompt") or config.SYSTEM_PROMPT

    try:
        provider = get_provider()
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e))

    if body.stream:
        # Streaming: accumulate full response while streaming to client
        async def streamer():
            full_text = []
            async for chunk in provider.stream(
                messages      = messages,
                model         = model,
                max_tokens    = _max_tokens(body.max_tokens),
                system_prompt = system,
            ):
                if chunk.startswith("[DONE]"):
                    # Save assistant message once complete
                    await db.add_message(conv_id, "assistant", "".join(full_text))
                    yield f"data: {chunk}\n\n"
                else:
                    full_text.append(chunk)
                    yield f"data: {json.dumps({'text': chunk})}\n\n"

        return StreamingResponse(
            streamer(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    else:
        try:
            result = await provider.chat(
                messages      = messages,
                model         = model,
                max_tokens    = _max_tokens(body.max_tokens),
                system_prompt = system,
            )
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Provider error: {e}")

        # Save assistant reply
        assistant_msg = await db.add_message(
            conv_id, "assistant", result.content, result.output_tokens
        )
        return {**result.to_dict(), "message_id": assistant_msg["id"]}


@app.get("/v1/conversations/{conv_id}/export", dependencies=[Depends(check_api_auth)])
async def export_conv(conv_id: str):
    data = await db.export_conversation(conv_id)
    if not data:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return data


# ── Entry point ───────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "src.server:app",
        host   = config.BIND_ADDR,
        port   = config.PORT,
        reload = False,
    )
