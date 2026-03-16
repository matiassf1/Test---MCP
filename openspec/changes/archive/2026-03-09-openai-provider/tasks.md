# Tasks: openai-provider

## Config

- [x] 1.1 Agregar `openai_api_key: str = ""` a `Settings`
- [x] 1.2 Agregar `openai_model: str = "gpt-4o-mini"` a `Settings`

## ai_reporter

- [x] 2.1 Implementar `_call_openai()` — llama a la API de OpenAI con `max_retries=0`
- [x] 2.2 Actualizar `_call_llm()` para intentar OpenAI antes que OpenRouter
- [x] 2.3 Actualizar `_is_ai_enabled()` para retornar `True` cuando `OPENAI_API_KEY` está seteado
