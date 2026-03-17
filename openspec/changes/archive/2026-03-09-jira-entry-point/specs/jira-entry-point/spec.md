# Spec: jira-entry-point

---

### Requirement: Listar PRs por ticket Jira

El sistema DEBE poder descubrir todos los PRs mergeados que mencionan un ticket Jira dado.

#### Scenario: PRs encontrados

WHEN se llama `list_prs_by_jira_ticket` con un `ticket_key` válido y un `org`
THEN retorna `{ ticket, prs: [{repo, pr}], total }` con todos los PRs encontrados

#### Scenario: No hay PRs

WHEN GitHub Search no retorna resultados para el ticket
THEN retorna `{ ticket, prs: [], total: 0 }`

#### Scenario: Error de GitHub

WHEN la llamada a GitHub falla (token inválido, red, etc.)
THEN retorna `{ ticket, error: "<mensaje>", prs: [], total: 0 }` sin propagar la excepción

---

### Requirement: Analizar PR por ticket Jira

El sistema DEBE poder analizar el PR vinculado a un ticket Jira sin que el usuario conozca el número de PR.

#### Scenario: Análisis del primer PR

WHEN se llama `analyze_pr_by_jira_ticket` con un ticket key válido
THEN descubre los PRs, analiza el de índice `pr_index` (default 0), y retorna `{ ticket, repo, pr, metrics }`

#### Scenario: pr_index fuera de rango

WHEN `pr_index` es mayor que el número de PRs encontrados
THEN se usa el último PR disponible (clamp al máximo)

#### Scenario: No hay PRs para el ticket

WHEN no se encuentran PRs para el ticket
THEN retorna `{ error: "No merged PRs found for ticket ...", ticket }`

---

### Requirement: Match exacto en búsqueda de GitHub

El sistema DEBE usar el ticket key entre comillas en la query de GitHub Search para evitar falsos positivos.

#### Scenario: Búsqueda con término exacto

WHEN se construye la query de GitHub Search para un ticket key
THEN el término aparece entre comillas dobles (ej. `"PROJ-123"`)
