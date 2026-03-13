"""
database.py -- SQLite conversation storage (async via run_in_executor)

Uses stdlib sqlite3 wrapped in asyncio.get_event_loop().run_in_executor()
for non-blocking operation without requiring aiosqlite.

Schema
------
conversations  : id, title, model, system_prompt, created_at, updated_at
messages       : id, conversation_id, role, content, created_at, tokens
"""

import asyncio
import sqlite3
import uuid
from datetime import datetime, timezone
from functools import partial
from pathlib import Path
from typing import Optional

from . import config

_DB_PATH = config.DB_PATH

_DDL = """
CREATE TABLE IF NOT EXISTS conversations (
    id            TEXT PRIMARY KEY,
    title         TEXT NOT NULL DEFAULT 'New conversation',
    model         TEXT NOT NULL DEFAULT '',
    system_prompt TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id              TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            TEXT NOT NULL,
    content         TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    tokens          INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_msg_conv ON messages(conversation_id, created_at);
"""


def _connect() -> sqlite3.Connection:
    Path(_DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(_DDL)
    conn.commit()
    return conn


def _run_sync(func, *args):
    """Run a sync DB function in the default executor."""
    loop = asyncio.get_event_loop()
    return loop.run_in_executor(None, partial(func, *args))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _uid() -> str:
    return str(uuid.uuid4())


# ── Sync helpers ──────────────────────────────────────────────────

def _sync_list_conversations():
    conn = _connect()
    try:
        rows = conn.execute("SELECT * FROM conversations ORDER BY updated_at DESC").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _sync_create_conversation(title, model, system_prompt):
    now  = _now()
    conv = {"id": _uid(), "title": title or "New conversation",
            "model": model or config.DEFAULT_MODEL,
            "system_prompt": system_prompt or config.SYSTEM_PROMPT,
            "created_at": now, "updated_at": now}
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO conversations VALUES(:id,:title,:model,:system_prompt,:created_at,:updated_at)", conv)
        conn.commit()
        return conv
    finally:
        conn.close()


def _sync_get_conversation(conv_id):
    conn = _connect()
    try:
        row = conn.execute("SELECT * FROM conversations WHERE id=?", (conv_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _sync_update_title(conv_id, title):
    conn = _connect()
    try:
        cur = conn.execute("UPDATE conversations SET title=?,updated_at=? WHERE id=?",
                           (title, _now(), conv_id))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def _sync_delete_conversation(conv_id):
    conn = _connect()
    try:
        cur = conn.execute("DELETE FROM conversations WHERE id=?", (conv_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def _sync_get_messages(conv_id):
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT * FROM messages WHERE conversation_id=? ORDER BY created_at", (conv_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _sync_add_message(conv_id, role, content, tokens):
    now = _now()
    msg = {"id": _uid(), "conversation_id": conv_id, "role": role,
           "content": content, "created_at": now, "tokens": tokens}
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO messages VALUES(:id,:conversation_id,:role,:content,:created_at,:tokens)", msg)
        conn.execute("UPDATE conversations SET updated_at=? WHERE id=?", (now, conv_id))
        conn.commit()
        return msg
    finally:
        conn.close()


# ── Public async API ──────────────────────────────────────────────

async def list_conversations() -> list:
    return await _run_sync(_sync_list_conversations)

async def create_conversation(title="New conversation", model="", system_prompt="") -> dict:
    return await _run_sync(_sync_create_conversation, title, model, system_prompt)

async def get_conversation(conv_id: str) -> Optional[dict]:
    return await _run_sync(_sync_get_conversation, conv_id)

async def update_conversation_title(conv_id: str, title: str) -> bool:
    return await _run_sync(_sync_update_title, conv_id, title)

async def delete_conversation(conv_id: str) -> bool:
    return await _run_sync(_sync_delete_conversation, conv_id)

async def get_messages(conv_id: str) -> list:
    return await _run_sync(_sync_get_messages, conv_id)

async def add_message(conv_id: str, role: str, content: str, tokens: int = 0) -> dict:
    return await _run_sync(_sync_add_message, conv_id, role, content, tokens)

async def export_conversation(conv_id: str) -> dict:
    conv = await get_conversation(conv_id)
    if not conv:
        return {}
    msgs = await get_messages(conv_id)
    return {"conversation": conv, "messages": msgs}
