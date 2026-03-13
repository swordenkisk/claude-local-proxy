"""
providers.py -- AI provider clients (Anthropic + remote endpoint)
Uses only Python stdlib (urllib / http.client) for HTTP requests.
Streaming is simulated via chunked read of the SSE response body.
"""

import json
import ssl
import urllib.request
import urllib.error
from asyncio import get_event_loop
from functools import partial
from typing import AsyncIterator

from . import config


# ── Standard response ─────────────────────────────────────────────

class ChatResponse:
    def __init__(self, content="", model="", input_tokens=0, output_tokens=0, stop_reason="end_turn"):
        self.content = content
        self.model = model
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.stop_reason = stop_reason

    def to_dict(self):
        return {
            "content": self.content,
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.input_tokens + self.output_tokens,
            "stop_reason": self.stop_reason,
        }


def _ssl_ctx():
    ctx = ssl.create_default_context()
    return ctx


def _post_json(url: str, headers: dict, body: dict, timeout: int = 120) -> dict:
    """Synchronous POST, returns parsed JSON body."""
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout, context=_ssl_ctx()) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _post_stream(url: str, headers: dict, body: dict, timeout: int = 180):
    """
    Synchronous streaming POST.
    Returns a generator of SSE 'data: ...' lines.
    """
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    resp = urllib.request.urlopen(req, timeout=timeout, context=_ssl_ctx())
    buf = b""
    while True:
        chunk = resp.read(512)
        if not chunk:
            break
        buf += chunk
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            yield line.decode("utf-8", errors="replace")
    resp.close()


# ── Anthropic Provider ────────────────────────────────────────────

class AnthropicProvider:
    API_URL = "https://api.anthropic.com/v1/messages"
    API_VERSION = "2023-06-01"

    def __init__(self, api_key: str, default_model: str = "claude-3-haiku-20240307"):
        self.api_key = api_key
        self.default_model = default_model

    def _headers(self) -> dict:
        return {
            "x-api-key": self.api_key,
            "anthropic-version": self.API_VERSION,
            "content-type": "application/json",
        }

    def _body(self, messages, model, max_tokens, system_prompt, stream=False):
        b = {
            "model": model or self.default_model,
            "max_tokens": max_tokens,
            "messages": messages,
            "stream": stream,
        }
        if system_prompt:
            b["system"] = system_prompt
        return b

    def _sync_chat(self, messages, model, max_tokens, system_prompt):
        body = self._body(messages, model, max_tokens, system_prompt, stream=False)
        data = _post_json(self.API_URL, self._headers(), body)
        text = "".join(
            b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"
        )
        usage = data.get("usage", {})
        return ChatResponse(
            content=text,
            model=data.get("model", model),
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            stop_reason=data.get("stop_reason", "end_turn"),
        )

    async def chat(self, messages, model="", max_tokens=1024, system_prompt="") -> ChatResponse:
        loop = get_event_loop()
        return await loop.run_in_executor(
            None,
            partial(
                self._sync_chat,
                messages,
                model or self.default_model,
                max_tokens,
                system_prompt,
            ),
        )

    def _sync_stream(self, messages, model, max_tokens, system_prompt):
        """Yield text delta strings, then final [DONE]..."""
        body = self._body(messages, model, max_tokens, system_prompt, stream=True)
        in_tok = 0
        out_tok = 0
        final_model = model or self.default_model
        chunks = []
        for line in _post_stream(self.API_URL, self._headers(), body):
            if not line.startswith("data: "):
                continue
            payload = line[6:].strip()
            if not payload or payload == "[DONE]":
                continue
            try:
                ev = json.loads(payload)
            except Exception:
                continue
            et = ev.get("type", "")
            if et == "message_start":
                in_tok = ev.get("message", {}).get("usage", {}).get("input_tokens", 0)
                final_model = ev.get("message", {}).get("model", final_model)
            elif et == "content_block_delta":
                d = ev.get("delta", {})
                if d.get("type") == "text_delta":
                    chunks.append(d.get("text", ""))
            elif et == "message_delta":
                out_tok = ev.get("usage", {}).get("output_tokens", 0)
        chunks.append(
            "[DONE]"
            + json.dumps(
                {
                    "model": final_model,
                    "input_tokens": in_tok,
                    "output_tokens": out_tok,
                }
            )
        )
        return chunks

    async def stream(
        self, messages, model="", max_tokens=1024, system_prompt=""
    ) -> AsyncIterator[str]:
        loop = get_event_loop()
        chunks = await loop.run_in_executor(
            None,
            partial(
                self._sync_stream,
                messages,
                model or self.default_model,
                max_tokens,
                system_prompt,
            ),
        )
        for chunk in chunks:
            yield chunk


# ── Remote Provider ───────────────────────────────────────────────

class RemoteProvider:
    def __init__(self, url: str):
        self.url = url

    def _sync_chat(self, messages, model, max_tokens, system_prompt):
        parts = []
        if system_prompt:
            parts.append(f"System: {system_prompt}")
        for m in messages:
            parts.append(f"{m.get('role', 'user').capitalize()}: {m.get('content', '')}")
        parts.append("Assistant:")
        prompt = "\n".join(parts)
        headers = {"content-type": "application/json"}
        body = {"inputs": prompt, "parameters": {"max_new_tokens": max_tokens}}
        data = _post_json(self.url, headers, body)
        if isinstance(data, list) and data:
            text = data[0].get("generated_text", str(data[0]))
        elif isinstance(data, dict):
            text = data.get("generated_text", data.get("text", str(data)))
        else:
            text = str(data)
        if text.startswith(prompt):
            text = text[len(prompt):].strip()
        return ChatResponse(content=text, model=model or self.url)

    async def chat(self, messages, model="", max_tokens=512, system_prompt="") -> ChatResponse:
        loop = get_event_loop()
        return await loop.run_in_executor(
            None,
            partial(
                self._sync_chat,
                messages,
                model,
                max_tokens,
                system_prompt,
            ),
        )

    async def stream(
        self, messages, model="", max_tokens=512, system_prompt=""
    ) -> AsyncIterator[str]:
        res = await self.chat(messages, model, max_tokens, system_prompt)
        yield res.content
        import json as _json
        yield "[DONE]" + _json.dumps(
            {"model": res.model, "input_tokens": 0, "output_tokens": 0}
        )


# ── Factory ───────────────────────────────────────────────────────

def get_provider():
    if config.API_PROVIDER == "remote":
        if not config.REMOTE_INFERENCE_URL:
            raise ValueError("REMOTE_INFERENCE_URL not set.")
        return RemoteProvider(config.REMOTE_INFERENCE_URL)
    if not config.ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY not set. Add it to .env.")
    return AnthropicProvider(config.ANTHROPIC_API_KEY, config.DEFAULT_MODEL)
