# Configuring AI Providers

## Anthropic (default)

```
API_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
MODEL=claude-sonnet-4-6
```

Available models: `claude-opus-4-6`, `claude-sonnet-4-6`, `claude-haiku-4-5-20251001`

## HuggingFace Inference API

```
API_PROVIDER=remote
REMOTE_INFERENCE_URL=https://api-inference.huggingface.co/models/mistralai/Mistral-7B-Instruct-v0.2
```

## Local LLM (Ollama)

```
API_PROVIDER=remote
REMOTE_INFERENCE_URL=http://127.0.0.1:11434/api/generate
```
