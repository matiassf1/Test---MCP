# Proposal: openrouter-provider

## Why

El análisis en batch de múltiples PRs con modelos de OpenRouter generaba errores 429 frecuentes porque las llamadas eran concurrentes o demasiado rápidas. Se necesitaba un flujo estrictamente secuencial con delays configurables y una estrategia de backoff explícita para los 429.

## What Changes

Integración completa de OpenRouter como proveedor de AI con control de rate-limiting, quality score vía OpenRouter, y un modo liviano para reducir la cantidad de llamadas por PR.

## Capabilities

### New
- **`try_quality_score_openrouter()`** — llama al LLM con un prompt mínimo para obtener un score 0–10 en JSON; usado cuando Anthropic no está configurado
- **`OPENROUTER_LIGHT_MODE`** — flag de config; cuando `True` hace 1 sola llamada LLM por PR (solo coverage), skip de report y quality score

### Modified
- **`src/ai_reporter.py`** — `_call_llm()` implementa backoff manual en 429: espera `openrouter_429_backoff_seconds` (default 60s) y reintenta una vez; delay post-llamada exitosa de `openrouter_delay_seconds` (default 5s); `OpenAI` client con `max_retries=0`
- **`src/config.py`** — nuevos campos: `openrouter_delay_seconds`, `openrouter_batch_delay_seconds`, `openrouter_429_backoff_seconds`, `openrouter_light_mode`
- **`src/tool_api.py`** — `batch_analyze_author` y `batch_analyze_repo` usan `_batch_delay()` entre PRs cuando OpenRouter está configurado
- **`_is_ai_enabled()`** — retorna `True` cuando `OPENROUTER_API_KEY` está seteado (sin necesitar `AI_ENABLED=true`)

## Impact

- Sin breaking changes; el delay y backoff solo se activan cuando OpenRouter está en uso
- El modelo default (`google/gemma-3-27b-it:free`) es gratuito; se puede sobrescribir con `OPENROUTER_MODEL`
