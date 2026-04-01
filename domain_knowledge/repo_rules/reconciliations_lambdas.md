# Domain Rules — reconciliations_lambdas

Mined: 2026-03-31 from local clone at `/Users/c-matiasgabrielsfer/Desktop/Test---MCP/temp/reconciliations_lambdas`

## Business Invariants

- **Strict sign-off (`close_entity-settings_separate-strict-sign-off`):** When enabled, `getStrictSignOffOptions` exposes per-setting booleans (`signOffByAssigneeManagerAdminOnce`, `sameUserCannotSignOffAsPreparerAndReviewer`, `preparersMustSignOffBeforeReviewers`); when disabled, legacy `strictSignoffEnabled` applies to all three (`signoff.utils.js` comments).
- **Redo mode:** If item has **history** and is **not** tied out, **all signoffs are blocked** with message *"in redo mode and the balances are not tied out"* (`signoff.utils.js`).
- **Rec lock:** `ReconciliationService.isLocked` rejects when `reconciliation.lockStatus.isLocked` is true (tests describe bad-request path).

## Authorization Rules

- `doAuthCheck` combines `authorizationManager.can(CAN_DO_PRIVILEGED_ACTION, …)` with strict sign-off rules; non-assigned preparer signoff blocked when strict rules require assignee-only (`signoff.utils.test.js` describes cases).

## State Transition Rules

- Signoff readiness / completeness helpers in `reconciliations.utils.js` encode preparer/reviewer completion states (see tests: ready for review, completed, incomplete).

## Cross-module Notes

- **reconciliations_lambdas vs `recs-client`:** Same user-visible SIL / strict sign-off strings as checklist; **must** match UI and `checklist_lambdas` flag semantics.

## Failure Patterns (from code signals)

### Pattern: Workday XLSX columns mismatch by export mode
- **Description:** Bulk vs single-entity export includes or omits dimension/ERP columns depending on flag and `forAllEntities`.
- **Root cause:** `close_workday_all_export_upload` branch logic in `xlsx.service.js`.
- **Signal:** `xlsx.service.test.js` describes ON/OFF matrix.

## Feature Flag Notes

- `close_entity-settings_separate-strict-sign-off` — `signoff.utils.js`.
- `close_workday_all_export_upload` — `xlsx.service.js` / tests.
- `close_workday_column_specifier` — template export/import integration tests.
- `close_reconciliations-signed-off` — referenced in `reconciliation.service.test.js` (context: signed-off flows).
