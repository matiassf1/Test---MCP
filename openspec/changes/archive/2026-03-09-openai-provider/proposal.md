# Proposal: openai-provider

## Why

OpenRouter tiene rate limits agresivos (429 frecuentes en batch). Los usuarios con acceso directo a la API de OpenAI necesitaban poder usarla sin pasar por OpenRouter, con mejor estabilidad y sin los delays forzados de rate-limiting.

## What Changes

Soporte para la API de OpenAI directa como proveedor de AI, con prioridad sobre OpenRouter en la cadena de selección.

## Capabilities

### Modified
- **`src/ai_reporter.py`** — nueva función `_call_openai()` usando el cliente `openai`; `_call_llm()` ahora intenta en orden: OpenAI → OpenRouter → Anthropic → Ollama
- **`src/config.py`** — nuevos campos `openai_api_key` y `openai_model` (default `gpt-4o-mini`); `_is_ai_enabled()` se activa cuando `OPENAI_API_KEY` está seteado

## Impact

- Sin breaking changes — la cadena de fallback preserva el comportamiento anterior cuando `OPENAI_API_KEY` no está seteado
- `gpt-4o-mini`: costo bajo, rate limits altos, ideal para análisis en batch
