# Tasks: list-prs-by-author

## tool_api

- [x] 1.1 Implementar `list_prs_by_author(author, org, since_days, limit)` — retorna `{ prs: [{repo, pr}], total }`
- [x] 1.2 Sin llamadas a Jira ni LLM — solo GitHub Search

## MCP

- [x] 2.1 Registrar `list_prs_by_author` como MCP tool en `mcp_server.py` con docstring que explica el flujo "listar → analizar uno por uno"
