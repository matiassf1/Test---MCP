# Design: openrouter-provider

## Decisiones técnicas

### Decisión: Backoff manual de 429 (1 reintento, sin loop)

**Alternativas:** retry automático con exponential backoff; SDK `max_retries`.

**Rationale:** En modelos gratuitos de OpenRouter, los 429 suelen ser "cuota agotada por ventana de 1 minuto". Esperar 60s fijo y reintentar una sola vez es más predecible que un backoff exponencial que puede acumular muchas requests en cola. Más de 1 reintento automático puede empeorar la situación para otros callers.

### Decisión: `max_retries=0` en el cliente OpenAI usado para OpenRouter

**Rationale:** Mismo razonamiento que para OpenAI directo: control manual explícito sobre cuándo y cuánto esperar.

### Decisión: Quality score con prompt mínimo (solo métricas + top files)

**Alternativas:** enviar el diff completo para el quality score.

**Rationale:** El diff completo se usa para el report narrativo (`ai_report`). Para el score numérico, las métricas de líneas + top 3 archivos son suficiente señal y reducen el costo de tokens por llamada. Separar las dos llamadas también permite que el score sea más rápido y barato.

### Decisión: `openrouter_light_mode` como flag de config, no parámetro por llamada

**Alternativas:** parámetro `light_mode=True` en cada tool call.

**Rationale:** Es una preferencia de despliegue (entorno con límites de API muy ajustados), no una decisión por PR. Tiene más sentido como configuración global en `.env` que como argumento que el agente tendría que pasar en cada llamada.
