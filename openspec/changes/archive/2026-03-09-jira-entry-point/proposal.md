# Proposal: jira-entry-point

## Why

Los usuarios de Jira necesitan analizar PRs partiendo desde un ticket, no desde un número de PR. Obligarles a buscar primero el PR en GitHub para luego pasarlo al tool rompía el flujo natural de trabajo en Cursor/Claude Desktop. Además, las búsquedas de ticket en GitHub retornaban resultados parciales porque el término no estaba entre comillas (match parcial).

## What Changes

Dos nuevas herramientas MCP que permiten usar un Jira ticket como punto de entrada completo, más un fix de exactitud en la búsqueda.

## Capabilities

### New
- **`list_prs_by_jira_ticket`** — dado un ticket key y un org, devuelve todos los PRs mergeados que lo mencionan (sin analizar); útil para descubrir y elegir qué PR analizar
- **`analyze_pr_by_jira_ticket`** — descubre y analiza directamente el PR en `pr_index` (default: primero) vinculado al ticket; retorna métricas completas

### Modified
- **`src/github_service.py`** — la query de GitHub Search ahora wrappea el ticket key entre comillas para match exacto

## Impact

- Sin breaking changes — las herramientas existentes (`analyze_pr`, etc.) no cambian
- Agrega docs `MCP-RESPONSE-SHAPES.md` con los response shapes de todas las herramientas
