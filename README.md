# 🤖 claude-local-proxy
### واجهة محلية لـ Claude AI — Local Web UI Proxy for Anthropic Claude

<div align="center">

![Platform](https://img.shields.io/badge/platform-Android%20%7C%20Linux%20%7C%20macOS%20%7C%20Windows-blue)
![Python](https://img.shields.io/badge/python-3.9%2B-green)
![FastAPI](https://img.shields.io/badge/FastAPI-0.110%2B-009688)
![License](https://img.shields.io/badge/license-MIT-brightgreen)
![Termux](https://img.shields.io/badge/Termux-ready-orange)

**Run a full-featured Claude AI chat interface from your phone or local machine.**
Supports Anthropic API, streaming responses, conversation history,
markdown rendering, Arabic RTL, dark mode, and mobile-first design.

</div>

---

## What is this?

`claude-local-proxy` is a **self-hosted FastAPI server** that runs on your
device (Android/Termux, Raspberry Pi, laptop, VPS) and provides:

- 🌐 **Browser UI** at `http://127.0.0.1:8080` — talk to Claude from any
  browser without installing apps
- 🔌 **REST API** at `/v1/chat` — drop-in proxy for apps that speak
  the Anthropic Messages API
- 📱 **Mobile-first design** — works beautifully on phone screens,
  supports Arabic RTL and LTR, dark mode
- 🔒 **Local-only by default** — your API key never leaves your device
  to a third-party; all requests go directly to Anthropic
- 💬 **Full conversation history** — multi-turn chat with memory,
  stored locally in SQLite
- ⚡ **Streaming** — real-time token streaming via Server-Sent Events
- 🔑 **Optional auth** — protect the UI with a simple token when
  exposing to a local network

---

## Quick Start

### Option A — One-command setup (Linux / Termux / macOS)

```bash
curl -fsSL https://raw.githubusercontent.com/swordenkisk/claude-local-proxy/main/scripts/setup.sh | bash
```

### Option B — Manual setup

```bash
git clone https://github.com/swordenkisk/claude-local-proxy
cd claude-local-proxy
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env: set ANTHROPIC_API_KEY=sk-ant-...
python -m src.server
```

Open `http://127.0.0.1:8080` in your browser. Done.

### Termux (Android) setup

```bash
pkg update && pkg install python git
git clone https://github.com/swordenkisk/claude-local-proxy
cd claude-local-proxy
pip install -r requirements.txt
cp .env.example .env
nano .env   # set your API key
python -m src.server
```

---

## Features

| Feature | Status |
|---------|--------|
| Chat UI with markdown rendering | ✅ |
| Streaming responses (SSE) | ✅ |
| Conversation history (SQLite) | ✅ |
| Multiple conversations | ✅ |
| Arabic RTL + bilingual UI | ✅ |
| Dark / light mode | ✅ |
| Mobile responsive | ✅ |
| API token authentication | ✅ |
| Anthropic Messages API proxy | ✅ |
| HuggingFace / remote endpoint | ✅ |
| Model selector | ✅ |
| System prompt customisation | ✅ |
| Export conversation (JSON/MD) | ✅ |
| Rate limiting | ✅ |
| Swap file setup (low-RAM devices) | ✅ |
| systemd service installer | ✅ |

---

## Repository Structure

```
claude-local-proxy/
├── README.md
├── requirements.txt
├── .env.example
├── .gitignore
│
├── src/
│   ├── __init__.py
│   ├── server.py          ← FastAPI app + entry point
│   ├── config.py          ← Settings loaded from .env
│   ├── providers.py       ← Anthropic + remote endpoint clients
│   ├── database.py        ← SQLite conversation storage
│   └── auth.py            ← Optional API token auth
│
├── templates/
│   └── index.html         ← Single-page chat UI (Jinja2)
│
├── static/
│   ├── css/
│   │   └── style.css      ← Mobile-first, RTL, dark-mode styles
│   ├── js/
│   │   └── app.js         ← Chat logic, streaming, markdown
│   └── icons/
│       └── favicon.svg
│
├── scripts/
│   ├── setup.sh           ← One-command installer
│   ├── setup_swap.sh      ← Swap file setup for low-RAM devices
│   └── install_service.sh ← systemd service installer
│
├── tests/
│   └── test_server.py     ← Test suite (18 cases)
│
└── docs/
    ├── api.md             ← REST API reference
    ├── termux.md          ← Termux/Android guide
    ├── security.md        ← Security considerations
    └── providers.md       ← Configuring different AI providers
```

---

## API Reference (brief)

```
POST /v1/chat
  Body: { "messages": [...], "model": "claude-opus-4-5", "stream": false }
  Returns: Anthropic Messages API response

GET  /v1/conversations
  Returns: list of saved conversations

POST /v1/conversations
  Body: { "title": "..." }
  Returns: { "id": "...", "title": "..." }

GET  /v1/conversations/{id}/messages
  Returns: all messages in conversation

DELETE /v1/conversations/{id}
  Deletes conversation and all messages

GET  /v1/models
  Returns: available models

GET  /health
  Returns: { "status": "ok", "provider": "anthropic" }
```

Full API docs at `http://127.0.0.1:8080/docs` (Swagger UI).

---

## Configuration (.env)

```env
# Required
ANTHROPIC_API_KEY=sk-ant-...

# Optional
API_PROVIDER=anthropic          # anthropic | remote
REMOTE_INFERENCE_URL=           # URL for remote endpoint
MODEL=claude-sonnet-4-6         # default model
MAX_TOKENS=1024                 # default max tokens
BIND_ADDR=127.0.0.1             # 0.0.0.0 to expose on LAN
PORT=8080
UI_AUTH_TOKEN=                  # set to require auth in browser
RATE_LIMIT_PER_MINUTE=20        # requests per minute per IP
SYSTEM_PROMPT=                  # optional default system prompt
DB_PATH=./data/conversations.db # SQLite database path
```

---

## Security

- **Never set `BIND_ADDR=0.0.0.0`** without also setting `UI_AUTH_TOKEN`
- Your API key is stored only in `.env` on your device
- All Claude API calls go directly from your device to Anthropic — no intermediary
- See `docs/security.md` for full security guide

---

## License

MIT — © 2026 swordenkisk
