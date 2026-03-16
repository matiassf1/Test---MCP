# Tasks: openrouter-provider

## Config

- [x] 1.1 Agregar `openrouter_delay_seconds: float = 5.0`
- [x] 1.2 Agregar `openrouter_batch_delay_seconds: float = 12.0`
- [x] 1.3 Agregar `openrouter_429_backoff_seconds: float = 60.0`
- [x] 1.4 Agregar `openrouter_light_mode: bool = False`

## ai_reporter

- [x] 2.1 `_call_llm()` — cliente con `max_retries=0`; backoff manual en 429 (wait 60s + 1 reintento); delay post-llamada exitosa
- [x] 2.2 `_is_ai_enabled()` — retorna `True` cuando `OPENROUTER_API_KEY` está seteado
- [x] 2.3 Implementar `try_quality_score_openrouter(metrics)` — score 0–10 en JSON con prompt mínimo
- [x] 2.4 Implementar `_build_quality_score_prompt(metrics)` — contexto mínimo (métricas + top 3 archivos)
- [x] 2.5 Manejar JSON envuelto en markdown code block en `try_quality_score_openrouter`
- [x] 2.6 Aplicar `openrouter_light_mode`: skip report y quality score cuando está activo

## tool_api

- [x] 3.1 Implementar `_batch_delay()` — espera `openrouter_batch_delay_seconds` cuando OpenRouter o OpenAI están configurados
- [x] 3.2 Llamar `_batch_delay()` entre PRs en `batch_analyze_author` y `batch_analyze_repo`
