# Design: list-prs-by-author

## Decisiones técnicas

### Decisión: Tool de discovery puro, sin análisis

**Alternativas:** retornar métricas básicas de cada PR junto con la lista.

**Rationale:** El objetivo es el control granular: el usuario/agente decide cuáles PRs analizar y en qué orden. Incluir análisis en el listado reintroduciría el problema del batch (costo, 429, fallos silenciosos). La separación también permite al agente mostrar la lista al usuario y pedir confirmación antes de gastar tokens.

### Decisión: `since_days` como parámetro, no fecha absoluta

**Alternativas:** recibir una fecha ISO.

**Rationale:** "30 días" es más natural que una fecha fija para el caso de uso de "¿qué hizo este autor este mes?". Consistente con el parámetro `--since` del CLI.

### Decisión: Implementado en `tool_api.py` como callable plano

**Rationale:** Sin lógica de estado ni dependencias complejas; una función es suficiente. Consistente con el patrón de todos los tools de discovery.
