# Spec: openrouter-provider

---

### Requirement: Activación por OPENROUTER_API_KEY

El sistema DEBE habilitar AI cuando `OPENROUTER_API_KEY` está seteado, sin `AI_ENABLED=true`.

#### Scenario: Solo OPENROUTER_API_KEY seteado

WHEN `OPENROUTER_API_KEY` está seteado
THEN `_is_ai_enabled()` retorna `True`

---

### Requirement: Quality score vía OpenRouter

El sistema DEBE poder obtener un score 0–10 usando OpenRouter cuando Anthropic no está configurado.

#### Scenario: Quality score obtenido

WHEN `try_quality_score_openrouter()` es llamado con un `PRMetrics` válido y AI habilitado
THEN retorna un `float` entre 0.0 y 10.0 parseado del JSON retornado por el LLM

#### Scenario: PR sin código testeable

WHEN `metrics.has_testable_code == False`
THEN retorna `None` sin llamar al LLM

#### Scenario: LLM retorna JSON en markdown code block

WHEN el LLM wrappea el JSON en triple backticks
THEN el sistema extrae el contenido entre `{` y `}` correctamente

#### Scenario: Error de parseo

WHEN el LLM retorna un string que no es JSON válido
THEN retorna `None` sin propagar la excepción

---

### Requirement: Backoff manual en 429

El sistema DEBE manejar errores 429 con un wait explícito y un solo reintento.

#### Scenario: 429 recibido

WHEN `_call_llm()` recibe un error 429
THEN espera `openrouter_429_backoff_seconds` (default 60s) y reintenta una vez

#### Scenario: Segundo 429

WHEN el reintento también falla con 429
THEN retorna string vacío sin más reintentos

---

### Requirement: Delay post-llamada exitosa

El sistema DEBE insertar un delay después de cada llamada exitosa a OpenRouter.

#### Scenario: Llamada exitosa

WHEN `_call_llm()` obtiene respuesta exitosa de OpenRouter
THEN espera `openrouter_delay_seconds` (default 5s) antes de retornar

---

### Requirement: Delay entre PRs en batch

El sistema DEBE insertar un delay más largo entre PRs consecutivos en operaciones batch.

#### Scenario: OPENROUTER_API_KEY configurado en batch

WHEN `batch_analyze_author` o `batch_analyze_repo` procesan múltiples PRs con OpenRouter activo
THEN `_batch_delay()` espera `openrouter_batch_delay_seconds` (default 12s) entre cada PR

---

### Requirement: Light mode

El sistema DEBE soportar un modo liviano que reduce las llamadas LLM a 1 por PR.

#### Scenario: OPENROUTER_LIGHT_MODE=true

WHEN `openrouter_light_mode=True`
THEN por PR solo se llama al LLM para estimar coverage; skip de report y quality score
