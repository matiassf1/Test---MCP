# Spec: openai-provider

---

### Requirement: Activación por OPENAI_API_KEY

El sistema DEBE habilitar AI cuando `OPENAI_API_KEY` está seteado, sin necesitar `AI_ENABLED=true`.

#### Scenario: Solo OPENAI_API_KEY seteado

WHEN `OPENAI_API_KEY` está seteado y `AI_ENABLED=false`
THEN `_is_ai_enabled()` retorna `True`

#### Scenario: Ninguna key seteada

WHEN ni `OPENAI_API_KEY` ni `OPENROUTER_API_KEY` ni `AI_ENABLED` están activos
THEN `_is_ai_enabled()` retorna `False`

---

### Requirement: Prioridad OpenAI sobre OpenRouter en _call_llm

El sistema DEBE intentar OpenAI directa antes que OpenRouter cuando ambas keys están presentes.

#### Scenario: Ambas keys seteadas

WHEN `OPENAI_API_KEY` y `OPENROUTER_API_KEY` están seteados
THEN `_call_llm()` usa el cliente OpenAI directo

#### Scenario: Solo OpenRouter

WHEN solo `OPENROUTER_API_KEY` está seteado
THEN `_call_llm()` usa OpenRouter (comportamiento anterior)

---

### Requirement: Modelo configurable

#### Scenario: Modelo default

WHEN `OPENAI_MODEL` no está seteado en `.env`
THEN se usa `gpt-4o-mini`

#### Scenario: Modelo custom

WHEN `OPENAI_MODEL=gpt-4o` está seteado
THEN `_call_openai()` usa ese modelo
