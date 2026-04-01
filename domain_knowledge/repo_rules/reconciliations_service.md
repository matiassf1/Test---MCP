# Domain Rules — reconciliations_service

Mined: 2026-03-31 from local clone at `/Users/c-matiasgabrielsfer/Desktop/Test---MCP/temp/reconciliations_service`

## Business Invariants

- **Balance API migration:** Callers must use **`CoreDataBalanceClient`** only when **`close_balance_api_migration`** is enabled; otherwise use legacy `CoreDataService.getAccountPeriodActivity()` (`core-data-balance-client.ts` module docstring).
- **Completeness / Workday:** `completeness-service.ts` reads TLC module settings including **`close_workday_currency_account_balance_filter`** and **`close_workday_column_specifier`** for Workday-oriented completeness behavior.

## Authorization Rules

- Service uses `@floqastinc/auth-module-server`, `fq-auth-middleware`, and **`@floqastinc/rec-schemas`** — authorization patterns align with other ECS services (details in route handlers; not fully traced in this pass).

## State Transition Rules

- (Not fully mined — no single state machine file read end-to-end.)

## Cross-module Notes

- **reconciliations_service vs `reconciliations` monorepo apps:** Overlaps with `apps/reconciliations_core-service` in **FloQastInc/close**; verify which deployment is canonical for a given env before duplicating completeness/balance fixes.

## Failure Patterns (from code signals)

### Pattern: Wrong balance source when migration flag mismatched
- **Description:** Mixed use of Core Data client vs legacy path for the same tenant.
- **Root cause:** `close_balance_api_migration` gating not respected at call site.
- **Signal:** `core-data-balance-client.ts` remarks.

## Feature Flag Notes

- `close_balance_api_migration` — balance client gating (docstring).
- `close_workday_currency_account_balance_filter`, `close_workday_column_specifier` — `completeness-service.ts` / tests.
