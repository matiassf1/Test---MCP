# Demo — chuleta rápida (helper)

Para tener a mano en la segunda pantalla o impreso. **No incluye secretos.**

---

## Checklist previo (2 min)

```
[ ] cd al repo · .venv activado · pip install -r requirements.txt
[ ] cp examples/demo.env.example .env  →  GITHUB_TOKEN + (OpenAI u OpenRouter)
[ ] PR_ANALYZER_PROFILE=demo  →  demo liviana (~1 LLM/PR, sin workflow contextual)
[ ] domain_context.md presente en la raíz (o DOMAIN_CONTEXT_PATH=…)
[ ] python mcp_server.py  (stdio)  o  MCP_TRANSPORT=sse MCP_PORT=8080 …
```

---

## `.env` mínimo demo (concepto)

| Variable | Valor típico demo |
|----------|-------------------|
| `GITHUB_TOKEN` | PAT lectura repos | 
| `PR_ANALYZER_PROFILE` | `demo` |
| `AI_ENABLED` | `true` |
| `OPENAI_API_KEY` *o* `OPENROUTER_API_KEY` | una sola vía |
| `JIRA_*` / `CONFLUENCE_*` | vacío = menos I/O |

**Demo liviana:** no pongas `repo_path` en el tool si no querés Jest/monorepo lento.

---

## Cursor — MCP stdio (plantilla)

Ajustá `command` y `cwd` a tu máquina:

```json
{
  "mcpServers": {
    "pr-analysis": {
      "command": "/ruta/al/repo/.venv/bin/python",
      "args": ["/ruta/al/repo/mcp_server.py"],
      "cwd": "/ruta/al/repo"
    }
  }
}
```

Variables sensibles van en `.env` del **cwd** del servidor (no en el JSON).

---

## Tools MCP que más usás en demo

| Tool | Uso en una frase |
|------|-------------------|
| `analyze_pr` | `repo`, `pr` — analiza un PR; `repo_path` opcional (pesado) |
| `analyze_pr_by_jira_ticket` | ticket key → encuentra PR y analiza |
| `get_pr_metrics` | métricas ya guardadas del PR |
| `analyze_epic` | épica Jira + PRs agregados |
| `get_author_summary` | tendencia por autor |

Lista completa: **README.md → MCP Tools**.

---

## `domain_context.md` — qué mencionar

- **§0:** SIL (CLOSE-9949) vs Separate Strict Sign-Off (CLOSE-8615), flags.
- **§2:** invariantes y locking/signoff.
- **§6:** patrones de fallo conocidos (copy/paste checklist vs recs, V1/V2 SIL, etc.).

---

## OpenSpec (una línea para la audiencia)

*“Las especificaciones y cambios grandes viven en `openspec/`; me ayudó a ordenar el dominio sin ser experto en Python desde el día uno.”*

Detalle: **`docs/DEMO-MCP-GUIDE.md`**.

---

## Si algo falla

| Síntoma | Qué probar |
|---------|------------|
| Muy lento | `PR_ANALYZER_PROFILE=demo` + sin `repo_path` + subí `OPENROUTER_LIGHT_MODE` ya viene en demo |
| 429 OpenRouter | subí delays o modelo de pago; o `OPENAI_API_KEY` |
| Sin AI report | `AI_ENABLED` + key; en `demo` el reporte largo puede estar limitado (light mode) |
| Sin Domain Risk | que exista `domain_context.md` y `DOMAIN_CONTEXT_PATH` correcto |

---

## Enlaces

- Índice: **[`DEMO-GUIA.md`](DEMO-GUIA.md)**
- Guía extendida: **[`DEMO-MCP-GUIDE.md`](DEMO-MCP-GUIDE.md)**
- Guión reunión: **[`../DEMO.md`](../DEMO.md)**
