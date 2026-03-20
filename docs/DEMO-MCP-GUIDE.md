# Demo tranquila: MCP + cobertura/calidad + un poco de `domain_context`

Guía informal para **mostrar el proyecto sin quemar CPU, rate limits ni cerebros**. Pensada para alguien que lo sube a un host y lo consume desde Cursor / otro cliente MCP.

**Índice general:** [`DEMO-GUIA.md`](DEMO-GUIA.md) · **Chuleta 1 página:** [`DEMO-HELPER.md`](DEMO-HELPER.md) · **Guión reunión (EN):** [`../DEMO.md`](../DEMO.md)

---

## Qué problema resuelve OpenSpec (deuda con Python / dominio)

No hace falta ser ninja de Python desde el día 1: **OpenSpec** en este repo es el “andamio” para cambios — propuestas, specs, tareas, verificación — antes de tocar código. Sirve para:

- Bajar a papel **qué** hace el pipeline de PRs, el reporte, Confluence, etc. (`openspec/specs/`, cambios archivados en `openspec/changes/archive/`).
- Trabajar con la IA de forma **dirigida** (skills en `.claude/skills/openspec-*`) en lugar de improvisar todo en el chat.

**Trade-off:** más fricción al arrancar un cambio; **menos** sorpresas cuando el analizador crece. Para una demo rápida no tenés que mostrar OpenSpec en vivo; alcanza con una frase: *“El comportamiento vivo está versionado en specs; domain_context.md es el contrato de producto que el analizador lee.”*

---

## Cómo se hablan las piezas (base)

```
Cursor / MCP client
       │  JSON-RPC / stdio  o  HTTP+SSE
       ▼
  mcp_server.py  (FastMCP)
       │  llama
       ▼
  src/tool_api.py  →  PRAnalysisPipeline
       │                    │
       ├── GitHub (diff, archivos)      ├── Jira (si configurado)
       ├── Confluence (opcional)       └── domain_context.md → heurísticas + informe
       └── LLM (1 o varias llamadas)
```

- **Sin repo local:** tenés métricas de diff, score heurístico, estimación de cobertura por LLM (si hay API key), y sección **Domain Risk** si existe `domain_context.md`.
- **Con `repo_path`:** podés sumar Jest / cobertura mecánica — **pesado** en monorepos; en demo suele ir **sin** path.

---

## Perfiles: `full` vs `demo`

| | **`PR_ANALYZER_PROFILE=full`** (default) | **`PR_ANALYZER_PROFILE=demo`** |
|--|-------------------------------------------|--------------------------------|
| **LLM** | Reporte largo + **workflow context** + cobertura + quality blend | **Solo ~1 llamada** (cobertura estimada); sin reporte narrativo completo ni segundo pase |
| **Workflow / DOMAIN_STRUCT** | Sí (si `CONTEXTUAL_WORKFLOW_ANALYSIS_ENABLED=true`) | **Off** por defecto |
| **Evidence merge** (heurística vs LLM) | Sí si está habilitado | **Off** por defecto |
| **Repo behavior JSON** | Como configures | **Off** por defecto |
| **Delays OpenRouter** | Los tuyos | **Cap a 2s** si no definís `OPENROUTER_DELAY_SECONDS` |

**Importante:** si en `.env` ya fijaste `OPENROUTER_LIGHT_MODE`, `CONTEXTUAL_WORKFLOW_ANALYSIS_ENABLED`, etc., esos valores **mandan** — el perfil `demo` **no los pisa**.

Qué **sí** sigue activo en `demo`:

- **Heurísticas** de `domain_context.md` (§2, §5, §6, roles…)
- **Behavior verifier** (si lo tenés `true`) — barato, va sobre el diff
- **Riesgo** (`compute_risk`) y **PR review focus** en el markdown
- **Shipping** básico (flags legacy, etc.)

Referencia de flags: **`domain_context.md` §0** (SIL vs strict sign-off), §2 invariants, feature flags en §4.

---

## Configuración mínima MCP (demo)

1. Cloná el repo, `pip install -r requirements.txt`.
2. Copiá **`examples/demo.env.example`** → `.env` y completá al menos **`GITHUB_TOKEN`** y una vía de LLM barata (**`OPENROUTER_API_KEY`** o **`OPENAI_API_KEY`**).
3. **`PR_ANALYZER_PROFILE=demo`**
4. **`domain_context.md`** en la raíz del proyecto (o `DOMAIN_CONTEXT_PATH`).
5. Arrancá el servidor:

```bash
python mcp_server.py
```

**Cursor (stdio):** configurá el MCP apuntando a `python /ruta/al/repo/mcp_server.py` (o el equivalente en tu OS).

**Remoto (SSE):** `MCP_TRANSPORT=sse MCP_PORT=8080 python mcp_server.py` y en el cliente la URL SSE + auth si usás `MCP_AUTH_SECRET`.

**Trade-offs remotos:** compartís un token con el servidor → **rotar** y acotar permisos del `GITHUB_TOKEN`; nunca commitees `.env`.

---

## Qué contar en 3 minutos de demo

1. **Tool `analyze_pr`** con un PR chico, **sin** `repo_path`: mostrar score, factores de riesgo, tabla “PR review focus” si generás reporte Markdown aparte o desde CLI.
2. Abrir **`domain_context.md` §0** y un invariant: *“Esto es lo que el anclaje textual + el LLM contextual en modo full verían.”*
3. **Alternar** `full` vs `demo` en una sola variable y notar tiempo de respuesta.
4. (Opcional) Misma PR con `repo_path` en monorepo → comentar **por qué** no lo hacés en la demo.

---

## Fragmentación / qué dejamos fuera a propósito en demo

| Capa | Demo | Full |
|------|------|------|
| Segundo LLM (workflow + Jira/Confluence/DOCUMENT_STRUCT) | Off | On |
| Evidence resolution post-merge | Off | On |
| Repo scan masivo (`repo_signals.json`) | Off | Opcional |
| Jest local | Evitar | Opcional |
| Confluence | Vacío en `.env` suele bastar | On si hay token |

---

## Siguiente paso si querés más modularidad en código

Hoy el “switch” es **env + perfil `demo`**. Si más adelante querés **herramientas MCP separadas** (`analyze_pr_lite`, `domain_risk_only`), es un cambio acotado en `mcp_server.py` + pipeline — buen candidato para un **OpenSpec** chico.

---

*Documento orientado a demo; comportamiento exacto según `src/config.py` y `.env`.*
