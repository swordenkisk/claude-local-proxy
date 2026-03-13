# API Reference

All endpoints are served at `http://127.0.0.1:8080`.
Interactive Swagger docs available at `/docs`.

## Authentication

When `UI_AUTH_TOKEN` is set, include the token as:
- Header: `Authorization: Bearer <token>`
- Query param: `?token=<token>`

## Endpoints

### Health
```
GET /health
Response: { "status": "ok", "provider": "anthropic", "model": "...", "auth": false }
```

### Models
```
GET /v1/models
Response: { "models": ["claude-opus-4-6", "claude-sonnet-4-6", ...] }
```

### Chat (stateless)
```
POST /v1/chat
Body: {
  "messages":      [{ "role": "user", "content": "Hello" }],
  "model":         "claude-sonnet-4-6",
  "max_tokens":    1024,
  "system_prompt": "..."
}
Response: {
  "content": "...", "model": "...",
  "input_tokens": 10, "output_tokens": 50,
  "total_tokens": 60, "stop_reason": "end_turn"
}
```

### Chat streaming (stateless)
```
POST /v1/chat/stream
Body: same as /v1/chat
Response: text/event-stream
  data: {"text": "chunk..."}
  data: [DONE]{"model":...}
```

### Conversations (stateful)
```
GET    /v1/conversations
POST   /v1/conversations          { "title": "...", "model": "..." }
GET    /v1/conversations/{id}
PUT    /v1/conversations/{id}     { "title": "..." }
DELETE /v1/conversations/{id}
GET    /v1/conversations/{id}/messages
POST   /v1/conversations/{id}/messages   { "content": "...", "stream": true }
GET    /v1/conversations/{id}/export
```
