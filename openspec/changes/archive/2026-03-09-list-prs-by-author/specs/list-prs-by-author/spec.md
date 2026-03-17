# Spec: list-prs-by-author

---

### Requirement: Listar PRs mergeados de un autor

El sistema DEBE poder listar los PRs mergeados de un autor en una org sin ejecutar el pipeline de análisis.

#### Scenario: PRs encontrados

WHEN se llama `list_prs_by_author` con `author`, `org`, `since_days` y `limit`
THEN retorna `{ prs: [{repo, pr}], total }` con los PRs del autor en el período indicado

#### Scenario: No hay PRs

WHEN el autor no tiene PRs mergeados en la org en el período
THEN retorna `{ prs: [], total: 0 }`

#### Scenario: Error de GitHub

WHEN la llamada a GitHub falla
THEN retorna `{ error: "<mensaje>", prs: [], total: 0 }` sin propagar la excepción

---

### Requirement: El tool NO ejecuta análisis

El sistema NO DEBE correr `PRAnalysisPipeline` al listar; solo hace búsqueda en GitHub.

#### Scenario: Solo discovery

WHEN se llama `list_prs_by_author`
THEN no se realiza ninguna llamada a Jira, LLM ni se persiste ninguna métrica

---

### Requirement: Límite configurable de resultados

#### Scenario: Límite respetado

WHEN se pasa `limit=10`
THEN el resultado contiene como máximo 10 PRs
