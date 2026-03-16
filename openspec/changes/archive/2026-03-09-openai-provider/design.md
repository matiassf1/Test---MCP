# Design: openai-provider

## Decisiones técnicas

### Decisión: Prioridad OpenAI > OpenRouter > Anthropic > Ollama

**Alternativas:** orden configurable; OpenRouter siempre primero.

**Rationale:** OpenAI directo tiene mejores rate limits y menor latencia que OpenRouter para los mismos modelos. Si el usuario tiene `OPENAI_API_KEY`, probablemente lo prefiere. Anthropic va antes que Ollama porque es más capaz; Ollama es el fallback local de última instancia.

### Decisión: `max_retries=0` en el cliente OpenAI

**Alternativas:** usar los reintentos automáticos del SDK.

**Rationale:** Los reintentos automáticos en batch pueden generar colas de requests bloqueados que empeoran los 429. Se prefiere el control manual explícito (igual que con OpenRouter) para poder aplicar el backoff apropiado.

### Decisión: `gpt-4o-mini` como modelo default

**Rationale:** Costo muy bajo (~$0.15/1M tokens input), rate limits altos, suficientemente capaz para el análisis de coverage y quality score. El usuario puede sobreescribir con `OPENAI_MODEL`.
