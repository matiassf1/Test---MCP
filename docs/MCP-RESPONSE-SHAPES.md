# Respuestas del MCP pr-analysis

Este documento describe la forma (estructura y campos) de lo que retorna cada herramienta del MCP **pr-analysis**. Todas las herramientas devuelven **JSON en string**; los objetos siguientes son el contenido de ese JSON una vez parseado.

---

## 1. `analyze_pr(repo, pr, repo_path?)`

Analiza un PR (GitHub + Jira + LLM) y persiste métricas. Retorna un objeto con métricas y resumen de archivos; **no** incluye los diffs completos ni la lista de `test_files` en detalle.

### Ejemplo de respuesta (campos)

```json
{
  "pr_number": 651,
  "author": "c-sandroquinteros_floqast",
  "title": "[CLOSE-12515]: Update isLocked check to account for item-level locking",
  "repo": "FloQastInc/checklist_lambdas",
  "pr_date": "2026-03-09T15:20:16+00:00",
  "jira_ticket": "CLOSE-12515",
  "jira_issue": {
    "key": "CLOSE-12515",
    "summary": "[1] Update isLocked check to account for item-level locking...",
    "issue_type": "Story",
    "status": "In Progress",
    "priority": "P3 - Low",
    "components": ["checklist_lambdas", "reconciliations_lambdas"],
    "labels": []
  },
  "files_changed": 5,
  "lines_modified": 13,
  "lines_covered": 0,
  "change_coverage": 0.0,
  "production_lines_added": 13,
  "production_lines_modified": 13,
  "test_lines_added": 20,
  "overall_coverage": null,
  "test_code_ratio": 1.54,
  "testing_quality_score": 7.74,
  "tests_added": 1,
  "test_types": { "unit": 1, "integration": 0, "e2e": 0, "unknown": 0 },
  "test_file_pairing_rate": 0.25,
  "assertion_count": 1,
  "has_testable_code": true,
  "is_modification_only": false,
  "ai_report": "# Testing Audit Report for PR #651\n\n## Testing Integrity Assessment\n...",
  "ai_estimated_coverage": null,
  "llm_estimated_coverage": 0.8,
  "llm_quality_score": 9.0,
  "files_summary": [
    { "file": "src/lambdas/item/routes.js", "status": "modified", "additions": 6 },
    { "file": "src/shared/utils/checklist-item.utils.test.js", "status": "modified", "additions": 20 }
  ]
}
```

### Descripción de campos (analyze_pr / get_pr_metrics)

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `pr_number` | int | Número del PR |
| `author` | string | Usuario de GitHub del autor |
| `title` | string | Título del PR |
| `repo` | string | Repositorio `org/name` |
| `pr_date` | string \| null | Fecha de merge o creación (ISO) |
| `jira_ticket` | string \| null | Clave del ticket (ej. CLOSE-12515) |
| `jira_issue` | object \| null | Datos de Jira: `key`, `summary`, `issue_type`, `status`, `priority`, `components`, `labels` |
| `files_changed` | int | Cantidad de archivos tocados |
| `lines_modified` | int | Líneas modificadas (suma de cambios) |
| `lines_covered` | int | Líneas cubiertas por coverage mecánico (Jest/pytest si hay `repo_path`) |
| `change_coverage` | float | Coverage de cambios 0.0–1.0 (mecánico; 0 si no se corre coverage) |
| `production_lines_added` | int | Líneas añadidas en archivos de producción |
| `production_lines_modified` | int | Líneas modificadas en producción |
| `test_lines_added` | int | Líneas añadidas en archivos de test |
| `overall_coverage` | float \| null | Coverage global del repo si está disponible |
| `test_code_ratio` | float | test_lines_added / production_lines_added |
| `testing_quality_score` | float | Puntuación final 0–10: fórmula (coverage, ratio, pairing) y, si hay LLM, **65% fórmula + 35% llm_quality_score**. Es el score de referencia. |
| `tests_added` | int | Número de tests detectados añadidos |
| `test_types` | object | `unit`, `integration`, `e2e`, `unknown` (conteos) |
| `test_file_pairing_rate` | float | Fracción de archivos de prod con archivo de test asociado (0–1) |
| `assertion_count` | int | Número de aserciones en diffs de tests |
| `has_testable_code` | bool | Si el PR toca código de producción testeable |
| `is_modification_only` | bool | True si solo se modifican líneas existentes (no se añaden de prod) |
| `ai_report` | string \| null | Reporte en markdown (Integrity, Coverage, Design, Risk, Recommendations). Null si light mode o AI no disponible |
| `ai_estimated_coverage` | float \| null | Coverage estimado por heurística de nombres (si aplica) |
| `llm_estimated_coverage` | float \| null | Coverage 0.0–1.0 estimado por el LLM según diffs |
| `llm_quality_score` | float \| null | Puntuación 0–10 solo del modelo (opinión cualitativa); no usa fórmulas. Null si light mode o sin AI. Se mezcla al 35% con la fórmula para obtener `testing_quality_score`. |
| `files_summary` | array | Lista de `{ file, status, additions }` por archivo tocado |

En caso de error, la respuesta es un objeto con clave `"error"` y mensaje en string.

#### Scores de calidad (testing_quality_score vs llm_quality_score)

- **`testing_quality_score`**: Score final 0–10 usado en resúmenes. Se calcula con una fórmula (coverage, ratio test/prod, test file pairing). Si el LLM devuelve un score cualitativo (`llm_quality_score`), se hace un blend **65% fórmula + 35% llm_quality_score** y ese es el valor final.
- **`llm_quality_score`**: Score 0–10 que da únicamente el modelo al leer los diffs; es solo opinión cualitativa. No incluye métricas numéricas. Cuando está presente, entra al 35% en el `testing_quality_score`.

---

## 2. `get_pr_metrics(repo, pr)`

Devuelve las métricas ya persistidas de un PR (misma forma que `analyze_pr`). Si no hay métricas: `{ "error": "No metrics found. Run analyze_pr first." }`.

---

## 3. `list_prs_by_author(author, org, since_days?, limit?)`

Solo listado de PRs merged del autor en la org; no ejecuta análisis.

### Ejemplo de respuesta

```json
{
  "prs": [
    { "repo": "FloQastInc/www-close", "pr": 5477 },
    { "repo": "FloQastInc/platform", "pr": 2093 }
  ],
  "total": 2
}
```

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `prs` | array | Lista de `{ "repo": string, "pr": number }` |
| `total` | int | Cantidad de PRs devueltos |
| `error` | string | Solo si hubo error (ej. fallo de GitHub) |

---

## 3b. `list_prs_by_jira_ticket(ticket_key, org, limit?)`

Lista PRs merged que mencionan el ticket de Jira (título, body o branch). No ejecuta análisis.

### Ejemplo de respuesta

```json
{
  "ticket": "CLOSE-13348",
  "prs": [
    { "repo": "FloQastInc/close", "pr": 4974 }
  ],
  "total": 1
}
```

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `ticket` | string | Clave del ticket (ej. CLOSE-13348) |
| `prs` | array | Lista de `{ "repo": string, "pr": number }` |
| `total` | int | Cantidad de PRs |
| `error` | string | Solo si hubo error |

---

## 3c. `analyze_pr_by_jira_ticket(ticket_key, org, pr_index?)`

Busca PRs merged que mencionan el ticket, analiza el PR en la posición `pr_index` (0 = el más reciente) y devuelve métricas + reporte. No hace falta saber repo/número de PR.

### Ejemplo de respuesta (éxito)

```json
{
  "ticket": "CLOSE-13348",
  "repo": "FloQastInc/close",
  "pr": 4974,
  "metrics": {
    "pr_number": 4974,
    "author": "...",
    "title": "[CLOSE-13348] Hotfix ...",
    "testing_quality_score": 8.2,
    "ai_report": "# Testing Audit Report...",
    "files_summary": [...]
  }
}
```

En error: `{ "error": "...", "ticket": "..." }` o, si no hay PRs: `{ "error": "No merged PRs found for ticket X in org Y", "ticket": "X" }`.

---

## 3d. `analyze_epic(epic_key, org, repo?, limit_per_ticket?, skip_existing?, include_ai_report?)`

Mapea una épica de Jira a sus child tickets y a los PRs que los mencionan; analiza cada PR y devuelve un informe consolidado.

### Ejemplo de respuesta (éxito)

```json
{
  "epic_key": "CLOSE-8615",
  "epic_summary": "Epic title from Jira",
  "child_tickets": [
    { "key": "CLOSE-12083", "summary": "...", "issue_type": "Story", "status": "Done" }
  ],
  "prs_analyzed": [
    {
      "repo": "FloQastInc/close", "pr": 4377, "ticket_linked": "CLOSE-12083",
      "title": "...", "author": "...", "testing_quality_score": 6.94,
      "llm_estimated_coverage": 0.85, "tests_added": 5, "ai_report": "# Testing Audit..."
    }
  ],
  "summary": {
    "total_prs": 5, "failed": 0, "avg_testing_quality_score": 7.2, "total_tests_added": 25
  }
}
```

| Campo | Descripción |
|-------|-------------|
| `epic_key` | Clave de la épica |
| `epic_summary` | Resumen desde Jira (null si Jira no configurado) |
| `child_tickets` | Lista de tickets hijos desde Jira (key, summary, issue_type, status) |
| `prs_analyzed` | Por cada PR: repo, pr, ticket_linked, título, autor, scores, tests_added, ai_report (si include_ai_report) |
| `summary` | total_prs, failed, avg_testing_quality_score, total_tests_added |

Si no hay PRs: `prs_analyzed` vacío y `summary.message` indicando que no se encontraron PRs.

---

## 4. `get_author_summary(author)`

Agregados por autor a partir de los PRs ya analizados y guardados en storage.

### Ejemplo de respuesta

```json
{
  "author": "c-matiasgabrielsfer_floqast",
  "prs": 6,
  "repos": ["FloQastInc/platform", "FloQastInc/www-close"],
  "avg_change_coverage_pct": 0.0,
  "avg_testing_quality_score": 7.85,
  "total_tests_added": 12,
  "total_lines_modified": 180,
  "pr_numbers": [2093, 2120, 2179, 5466, 5477]
}
```

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `author` | string | Usuario de GitHub |
| `prs` | int | Cantidad de PRs analizados de ese autor |
| `repos` | array | Lista de repos distintos |
| `avg_change_coverage_pct` | float | Promedio de coverage de cambios en % (0–100) |
| `avg_testing_quality_score` | float | Promedio del score 0–10 |
| `total_tests_added` | int | Suma de tests añadidos |
| `total_lines_modified` | int | Suma de líneas modificadas |
| `pr_numbers` | array | Lista ordenada de números de PR |

---

## 5. `get_repo_summary(repo, since_days?)`

Resumen agregado de un único repo (solo PRs ya analizados en ese repo).

### Ejemplo de respuesta (campos principales)

```json
{
  "repo": "FloQastInc/checklist_lambdas",
  "since_days": 30,
  "prs_analyzed": 15,
  "average_change_coverage": 0.42,
  "average_testing_quality_score": 7.2,
  "total_tests_added": 45,
  "test_type_distribution": { "unit": 0.8, "integration": 0.15, "e2e": 0.05, "unknown": 0.0 },
  "top_contributors": [
    { "author": "user1", "prs": 5, "avg_score": 7.5 }
  ],
  "coverage_trend": [],
  "repos": ["FloQastInc/checklist_lambdas"]
}
```

No se incluyen `pr_metrics` ni `by_author` en la respuesta serializada para mantener el payload ligero.

---

## 6. `get_multi_repo_summary(repos, since_days?)`

Misma forma que `get_repo_summary` pero para varios repos; `repo` puede ser una etiqueta (ej. lista de nombres) y `repos` es el listado de repos considerados.

---

## 7. `batch_analyze_author(author, org, since_days?, limit?, skip_existing?)`

Ejecuta análisis en batch para PRs del autor en la org. Retorna un resumen de la ejecución, no las métricas completas de cada PR.

### Ejemplo de respuesta

```json
{
  "total_found": 6,
  "analyzed": [
    { "repo": "FloQastInc/platform", "pr": 2093, "status": "ok", "score": 8.56 },
    { "repo": "FloQastInc/www-close", "pr": 5477, "status": "error", "error": "..." }
  ],
  "skipped": 2,
  "failed": 1
}
```

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `total_found` | int | PRs encontrados por GitHub para ese autor/org |
| `analyzed` | array | Por cada PR procesado: `repo`, `pr`, `status` ("ok" \| "error"), y opcionalmente `score` o `error` |
| `skipped` | int | PRs omitidos (ya existían en storage si `skip_existing=true`) |
| `failed` | int | PRs en los que el análisis falló |
| `error` | string | Solo si falla toda la operación (ej. error de GitHub) |

---

## 8. `batch_analyze_repo(repo, since_days?, limit?, skip_existing?)`

Misma forma que `batch_analyze_author` pero para un solo repo: `total_found`, `analyzed`, `skipped`, `failed` (y opcionalmente `error` global).

---

## Notas

- **Métricas vs reporte:** Las métricas numéricas y `files_summary` vienen en el JSON. El **reporte en prosa** es el campo `ai_report` (markdown); si quieres un único documento “métricas + reporte”, hay que componerlo en el cliente (p. ej. una tabla de métricas + el contenido de `ai_report`).
- **Fechas:** `pr_date` y cualquier fecha en `jira_issue` vienen en ISO 8601.
- **Errores:** Cualquier tool puede devolver un objeto con clave `"error"` y un mensaje en string cuando algo falla.
