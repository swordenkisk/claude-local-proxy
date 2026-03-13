# Security Guide

## Default: Local-Only (Safe)

`BIND_ADDR=127.0.0.1` — only accepts connections from the same device.
Your API key never leaves your device to any third-party.

## Exposing on a Local Network

1. Set `BIND_ADDR=0.0.0.0` in `.env`
2. **Always** set `UI_AUTH_TOKEN=some-long-random-string`
3. Open `http://<IP>:8080?token=your-token`

Never expose without `UI_AUTH_TOKEN` when `BIND_ADDR=0.0.0.0`.

## Your API Key

- Stored only in `.env` on your device
- Sent only to `api.anthropic.com` — no intermediaries
- `.env` is in `.gitignore`

## Rate Limiting

`RATE_LIMIT_PER_MINUTE=20` — limits API requests per IP per minute.
