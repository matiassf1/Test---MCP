# Tasks: jira-entry-point

## GitHub Search

- [x] 1.1 Wrapear el ticket key entre comillas en la query de `get_prs_mentioning_ticket()` para match exacto

## tool_api

- [x] 2.1 Implementar `list_prs_by_jira_ticket(ticket_key, org, limit)` — discovery sin análisis
- [x] 2.2 Implementar `analyze_pr_by_jira_ticket(ticket_key, org, pr_index, storage)` — descubre y analiza el PR en `pr_index`
- [x] 2.3 Clamp `pr_index` al rango `[0, len(prs) - 1]`
- [x] 2.4 Retornar `{ error, ticket }` cuando no hay PRs para el ticket

## MCP

- [x] 3.1 Registrar `list_prs_by_jira_ticket` como MCP tool en `mcp_server.py`
- [x] 3.2 Registrar `analyze_pr_by_jira_ticket` como MCP tool en `mcp_server.py`

## Docs

- [x] 4.1 Crear `docs/MCP-RESPONSE-SHAPES.md` con response shapes de todos los tools incluyendo los nuevos de ticket
