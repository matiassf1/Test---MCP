# Proposal: list-prs-by-author

## Why

El tool `batch_analyze_author` analizaba todos los PRs de un autor de un golpe, lo que consumía muchos tokens y fallaba en silencio para PRs individuales sin forma de reintentar. Los usuarios necesitaban poder descubrir los PRs primero y luego analizarlos de a uno, con control total sobre cuáles procesar.

## What Changes

Un nuevo tool MCP de discovery que lista los PRs de un autor sin analizarlos, habilitando el flujo "listar → analizar uno por uno con `analyze_pr`".

## Capabilities

### New
- **`list_prs_by_author`** — dado `author`, `org`, `since_days` y `limit`, devuelve `{ prs: [{repo, pr}], total }` sin correr el pipeline de análisis

## Impact

- Sin breaking changes — `batch_analyze_author` sigue disponible
- Requiere solo `GITHUB_TOKEN`; no consume API de LLM
