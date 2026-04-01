# Domain Rules — checklist_lambdas

Mined: 2026-03-31 from local clone at `/Users/c-matiasgabrielsfer/Desktop/Test---MCP/temp/checklist_lambdas`

## Business Invariants

- **Single Item Lock:** When `close_locking_single-item-lock` is off, **legacy** lock path runs (middleware may still update `lockStatus` and call CSP when legacy auto-lock flags apply). When the FF is on, **new** path requires **both** the FF **and** `company.settings.singleItemLock` enabled; if `singleItemLock` is **DISABLED**, middleware **early-returns** without CSP update even if FF is on (`update-lock-status.js` comments).
- **CSP lock:** FQ `lockStatus` can be updated regardless of CSP; CSP file lock/unlock is **additive** when CSP file locking is enabled for the item.

## Authorization Rules

- Feature flag keys for SSO/SIL are centralized: `STRICT_SIGNOFF` = `close_entity-settings_separate-strict-sign-off`, `SINGLE_ITEM_LOCK` = `close_locking_single-item-lock` (`src/shared/constants/constants.js`).

## State Transition Rules

- Lock status updates after checklist item mutations are applied in the **after** hook of `updateLockStatus` (Middy); invalid `checklistItem` without `company` logs error and returns item unchanged.

## Cross-module Notes

- **checklist_lambdas vs `checklist-service` (ECS):** Same domain (checklist items, locks) but different runtime; **SIL** and strict sign-off behavior must stay **consistent** with monorepo UI (`checklist-client`) and **recs** (`reconciliations_lambdas` / `recs-client`).

## Failure Patterns (from code signals)

### Pattern: SIL disabled at company blocks new path while FF on
- **Description:** Operators expect SIL behavior when Harness FF is on, but company `singleItemLock` is `DISABLED` — middleware exits without new-path lock/CSP updates.
- **Root cause:** Product rule: SIL requires **both** FF and entity policy.
- **Signal:** `update-lock-status.test.js` cases for `singleItemLock` DISABLED + FF on.

## Feature Flag Notes

- `close_locking_single-item-lock` — `update-lock-status.js`; tests in `update-lock-status.test.js`.
- `close_entity-settings_separate-strict-sign-off` — constants; **test coverage:** partial (via lock middleware and integration tests).
