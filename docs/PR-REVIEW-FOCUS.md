# Revisar PRs con foco: ticket + producción

Objetivo único: **¿el código hace lo del ticket?** y **¿puede chocar con producción o reglas de dominio?**

## Qué mirar en el reporte (orden)

1. **PR review focus** (arriba del todo) — tabla resumen: scope vs Jira, riesgo, dominio, business rules.
2. **Executive summary** — veredicto de ship, flags, paths legacy.
3. **AI Testing Quality Analysis** — sección **Scope vs ticket** + **Risk Analysis** ancladas al diff.
4. **Domain Risk Analysis** — invariantes / patrones tras *behavior verifier* + *evidence layer* (por defecto activos en config).
5. **Workflow context analysis** — mapeo a §2 / §6 y bloque `DOMAIN_STRUCT`.

## Config recomendada (consolidada)

En `config.py` los defaults ya apuntan aquí:

| Variable | Default | Rol |
|----------|---------|-----|
| `DOMAIN_VERIFY_BEHAVIOR_BEFORE_HARD` | `true` | No marcar invariante hard si el diff no quita guards / bypass. |
| `DOMAIN_EVIDENCE_VALIDATION_ENABLED` | `true` | Si el LLM pone `VIOLATED_INVARIANTS: NONE` y hay contradicción, baja el falso positivo en riesgo. |
| `CONTEXTUAL_WORKFLOW_ANALYSIS_ENABLED` | `true` | Segundo pase LLM con ticket + docs + `domain_context.md`. |
| `REPO_BEHAVIOR_REPORT_ENABLED` | `false` | Oculta el dump experimental de repo scan (pesado); activar solo si lo necesitás. |

Opcional: Jira + Confluence llenos para mejor alineación de ticket y reglas wiki.

## Qué podés apagar si solo querés velocidad

- `OPENROUTER_LIGHT_MODE=true` — un LLM/PR (cobertura); **pierde** workflow + merge DOMAIN_STRUCT + evidence validation útil.
- Sin `domain_context.md` — menos ruido de dominio pero también menos chequeo de invariantes escritas.

Ver también: `docs/EVIDENCE-RESOLUTION-LAYER.md`, `docs/BEHAVIOR-VERIFIER-DESIGN.md`.
