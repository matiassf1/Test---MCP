# Design: jira-entry-point

## Decisiones técnicas

### Decisión: Dos tools separados (list + analyze) en lugar de uno combinado

**Alternativas:** un solo tool `analyze_by_ticket` que lista y analiza en un paso.

**Rationale:** El flujo de agente necesita pasos separados: primero descubrir cuántos PRs hay y cuáles son, luego decidir cuál analizar. Un tool combinado forzaría al agente a adivinar el índice sin ver la lista. La separación refleja el patrón ya establecido con `list_prs_by_author` + `analyze_pr`.

### Decisión: `pr_index` con clamp (no error) cuando está fuera de rango

**Alternativas:** retornar error si el índice es inválido.

**Rationale:** Los agentes suelen pasar `pr_index=0` por defecto. Si hay exactamente 1 PR y el agente pasa `pr_index=1`, fallar sería un comportamiento sorpresivo. El clamp silencioso al máximo es más robusto para el uso en agentes.

### Decisión: Match exacto con comillas en GitHub Search

**Alternativas:** búsqueda sin comillas (comportamiento anterior).

**Rationale:** Sin comillas, buscar `PROJ-123` retornaba PRs que mencionaban `PROJ-1234` o `PROJ-123456`. Las comillas dobles en la GitHub Search API garantizan match de substring exacto, eliminando falsos positivos que contaminaban los resultados.

### Decisión: Response shape como `dict` plano, no modelo Pydantic

**Rationale:** Consistente con el resto de `tool_api.py`. Los tools de discovery retornan dicts simples; los de análisis retornan métricas dentro de un dict wrapper. No justifica un modelo dedicado.
