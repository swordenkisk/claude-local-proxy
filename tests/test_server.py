import asyncio, json, os, sys, tempfile, types
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

def _stub(name, attrs=None):
    if name in sys.modules: return
    mod = types.ModuleType(name)
    for k, v in (attrs or {}).items(): setattr(mod, k, v)
    sys.modules[name] = mod

def _dc(name):
    return type(name, (), {
        "__init__": lambda s, *a, **k: None,
        "__init_subclass__": classmethod(lambda cls, **k: None),
        "model_dump": lambda s: {},
    })

_stub("fastapi", {
    "FastAPI": _dc("FastAPI"), "Depends": lambda f: None,
    "HTTPException": type("HTTPException", (Exception,), {"__init__": lambda s, **k: None}),
    "Request": object, "Response": object, "Cookie": lambda **k: None,
})
_stub("fastapi.middleware.cors", {"CORSMiddleware": object})
_stub("fastapi.responses", {"HTMLResponse": object, "JSONResponse": object, "StreamingResponse": object})
_stub("fastapi.staticfiles", {"StaticFiles": object})
_stub("fastapi.templating", {"Jinja2Templates": _dc("Jinja2Templates")})
_stub("pydantic", {"BaseModel": _dc("BaseModel"), "Field": lambda *a, **k: None})
_stub("uvicorn", {"run": lambda *a, **k: None})

_TMPDIR = tempfile.mkdtemp()
os.environ.update({
    "ANTHROPIC_API_KEY": "sk-ant-test-key-000",
    "DB_PATH": str(Path(_TMPDIR) / "test.db"),
    "UI_AUTH_TOKEN": "",
    "RATE_LIMIT_PER_MINUTE": "0",
    "API_PROVIDER": "anthropic",
})

from src import config
from src import database as db
from src.providers import AnthropicProvider, RemoteProvider, ChatResponse
from src.auth import _token_valid

W = 64
passed = failed = 0
results = []
loop = asyncio.new_event_loop()

def run(coro):
    return loop.run_until_complete(coro)

def check(name, cond, detail=""):
    global passed, failed
    msg = "  [" + ("PASS" if cond else "FAIL") + "] " + name
    if detail: msg += "  --  " + detail
    print(msg)
    results.append((name, cond))
    if cond: passed += 1
    else: failed += 1

print("=" * W)
print("  claude-local-proxy -- Test Suite (18 tests)")
print("=" * W)

# Block A: Config
print("\n[ Block A: Config (3 tests) ]\n")
check("A1: API key loaded", config.ANTHROPIC_API_KEY == "sk-ant-test-key-000")
check("A2: DB path in temp dir", config.DB_PATH.startswith(_TMPDIR))
check("A3: validate() returns list", isinstance(config.validate(), list))

# Block B: Database
print("\n[ Block B: Database (5 tests) ]\n")
conv = run(db.create_conversation(title="Test", model="claude-sonnet-4-6"))
check("B1: create_conversation has id", isinstance(conv, dict) and "id" in conv)
convs = run(db.list_conversations())
check("B2: list includes new conv", any(c["id"] == conv["id"] for c in convs))
msg = run(db.add_message(conv["id"], "user", "hello", tokens=5))
check("B3: add_message role=user", isinstance(msg, dict) and msg["role"] == "user")
msgs = run(db.get_messages(conv["id"]))
check("B4: get_messages returns content", len(msgs) == 1 and msgs[0]["content"] == "hello")
run(db.add_message(conv["id"], "assistant", "world", tokens=4))
exp = run(db.export_conversation(conv["id"]))
check("B5: export has 2 messages", "conversation" in exp and len(exp["messages"]) == 2)

# Block C: Delete
print("\n[ Block C: Delete (2 tests) ]\n")
ok = run(db.delete_conversation(conv["id"]))
check("C1: delete returns True", ok is True)
check("C2: deleted not in list", not any(c["id"] == conv["id"] for c in run(db.list_conversations())))

# Block D: Providers (mock urllib.request.urlopen)
print("\n[ Block D: Providers (5 tests) ]\n")

FAKE_RESPONSE = {
    "content": [{"type": "text", "text": "Hello!"}],
    "model": "claude-sonnet-4-6", "stop_reason": "end_turn",
    "usage": {"input_tokens": 10, "output_tokens": 8},
}

class FakeHTTPResp:
    def __init__(self, data):
        self._data = json.dumps(data).encode()
    def read(self): return self._data
    def __enter__(self): return self
    def __exit__(self, *a): pass

def fake_urlopen_chat(req, timeout=None, context=None):
    return FakeHTTPResp(FAKE_RESPONSE)

with patch("urllib.request.urlopen", fake_urlopen_chat):
    prov = AnthropicProvider("sk-ant-test", "claude-sonnet-4-6")
    res  = run(prov.chat([{"role": "user", "content": "hi"}]))

check("D1: Anthropic returns ChatResponse", isinstance(res, ChatResponse))
check("D2: content non-empty", isinstance(res.content, str) and len(res.content) > 0, repr(res.content))
check("D3: token counts are ints", isinstance(res.input_tokens, int) and isinstance(res.output_tokens, int))
d = res.to_dict()
check("D4: to_dict has required keys", all(k in d for k in ["content","model","input_tokens","output_tokens","total_tokens"]))

FAKE_REMOTE = [{"generated_text": "Prompt text\nAssistant: answer"}]

def fake_urlopen_remote(req, timeout=None, context=None):
    return FakeHTTPResp(FAKE_REMOTE)

with patch("urllib.request.urlopen", fake_urlopen_remote):
    r2 = run(RemoteProvider("http://fake").chat([{"role":"user","content":"hi"}]))
check("D5: Remote returns ChatResponse", isinstance(r2, ChatResponse), repr(r2.content[:20]))

# Block E: Auth
print("\n[ Block E: Auth (3 tests) ]\n")
check("E1: empty token -> True", _token_valid(None) is True)
with patch.object(config, "UI_AUTH_TOKEN", "secret123"):
    check("E2: correct token -> True",  _token_valid("secret123") is True)
    check("E3: wrong token   -> False", _token_valid("wrong")     is False)

# Block F: Streaming (uses _sync_stream logic directly)
print("\n[ Block F: Streaming (1 test) ]\n")

SSE_RAW = b"\n".join([
    b"data: {\"type\":\"message_start\",\"message\":{\"usage\":{\"input_tokens\":5},\"model\":\"x\"}}",
    b"data: {\"type\":\"content_block_delta\",\"delta\":{\"type\":\"text_delta\",\"text\":\"Hello\"}}",
    b"data: {\"type\":\"content_block_delta\",\"delta\":{\"type\":\"text_delta\",\"text\":\" world\"}}",
    b"data: {\"type\":\"message_delta\",\"usage\":{\"output_tokens\":2}}",
])

class FakeStreamResp:
    def __init__(self):
        self._buf = SSE_RAW
        self._pos = 0
    def read(self, n):
        chunk = self._buf[self._pos:self._pos+n]
        self._pos += n
        return chunk
    def close(self): pass

def fake_urlopen_stream(req, timeout=None, context=None):
    return FakeStreamResp()

with patch("urllib.request.urlopen", fake_urlopen_stream):
    p = AnthropicProvider("sk-ant-test", "claude-sonnet-4-6")
    stream_chunks = list(p._sync_stream([{"role":"user","content":"hi"}], "claude-sonnet-4-6", 512, ""))

text_parts = [c for c in stream_chunks if not c.startswith("[DONE]")]
done_parts = [c for c in stream_chunks if c.startswith("[DONE]")]
check("F1: stream yields text chunks + [DONE]",
      len(text_parts) > 0 and len(done_parts) == 1,
      "text=" + str(len(text_parts)) + " done=" + str(len(done_parts)))

# Summary
total = passed + failed
print()
print("=" * W)
status = "ALL PASS" if failed == 0 else str(failed) + " FAILED"
print("  Results  :  " + str(passed) + "/" + str(total) + " tests passed  (" + status + ")")
if failed > 0:
    print("  Failures :  " + ", ".join(n for n, ok in results if not ok))
print("=" * W)
import sys as _sys; _sys.exit(0 if failed == 0 else 1)
