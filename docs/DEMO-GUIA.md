# Guía demo — por dónde empezar

Todo lo relacionado con **mostrar el analizador de PRs** (MCP + calidad/cobertura + dominio) está repartido en pocos archivos. Usá esta página como **mapa**.

---

## Documentos

| Archivo | Para qué sirve | Idioma / tono |
|---------|----------------|---------------|
| **[`DEMO-HELPER.md`](DEMO-HELPER.md)** | **Chuleta** copy-paste: env, MCP en Cursor, tools, flags, fallos típicos | ES, 1 página |
| **[`DEMO-MCP-GUIDE.md`](DEMO-MCP-GUIDE.md)** | Explicación **tranquila**: OpenSpec, diagrama de capas, perfil `demo` vs `full`, trade-offs | ES, informal |
| **[`../DEMO.md`](../DEMO.md)** | **Guión de reunión** ~10 min (ticket → PR, autor, épica, Q&A) | EN (podés narrar en ES) |
| **[`PR-REVIEW-FOCUS.md`](PR-REVIEW-FOCUS.md)** | Qué mirar primero en un reporte (ticket vs producción) | ES |
| **`examples/demo.env.example`** | Plantilla `.env` para demo liviana (`PR_ANALYZER_PROFILE=demo`) | comentarios ES |

---

## Orden sugerido

1. **Antes de la demo:** copiá `examples/demo.env.example` → `.env`, completá `GITHUB_TOKEN` + una API LLM, poné `PR_ANALYZER_PROFILE=demo` si querés respuestas rápidas.
2. **Si tenés 2 minutos:** leé **`DEMO-HELPER.md`**.
3. **Si explicás el producto a alguien no técnico:** usá el guión **`DEMO.md`** o contá lo mismo en español con la misma estructura.
4. **Si preguntan “¿cómo se conecta esto?”:** **`DEMO-MCP-GUIDE.md`** (diagrama + OpenSpec en una frase).

---

## Dominio en demo

- **`domain_context.md`** en la raíz del repo del **analizador** (no hace falta el monorepo bajo análisis para que se carguen heurísticas).
- Mirá **§0** (SIL vs strict sign-off), **§2** invariantes, **§4** flags — eso es lo que el pipeline usa en informes y riesgo.

---

## Scripts rápidos (CLI)

Desde la raíz del repo, con venv activado — ver **`scripts/README.md`**:

- `python scripts/demo_pr.py <org/repo> <pr>`
- `python scripts/demo_ticket.py <TICKET-123> [org/repo_fallback]`
- `python scripts/demo_author.py <github_user> <org> [días]`

*(Ajustá org/repos a los tuyos; los del repo pueden ser ejemplos históricos.)*
