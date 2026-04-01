# Domain Rules — close

Mined: 2026-03-31 from local clone at `/Users/c-matiasgabrielsfer/Desktop/Test---MCP/temp/close`

## Business Invariants

- JEM **journal entry batch export** must not run when `close_jem_batch-export` is off — service throws `ApiError.ForbiddenError('Batch export is not enabled')` (`apps/jem_api/src/service/journal-entry-batch/create-batch-for-export.ts`).
- For **scheduled reversal** JEs on ERPs in `ERP_MANAGES_REVERSING`, **sync may be blocked** when `close_jem_workday_ga` is on (documented in `getPermissionsV2.ts` and enforced via `isSyncBlockedForScheduledReversal`).
- **Recs reconciliation row**: signoff toggle is disabled when folder is locked **or** when SIL flag + company `singleItemLock === LOCK_ALL` and `reconciliation.lockStatus.isLocked` (`ui/recs-client/src/components/ReconciliationTable/ReconciliationRow/index.js`).
- **Todos checklist procedures**: when TLC module `TDL_Expanded_Range` is disabled, checklist items for procedures come from Lambda `GET /items` on `fq-checklist-item:live` with due-date range + `incomplete` + assignee filter; when enabled, an in-process aggregation pipeline is used instead (`apps/todos_api/src/services/checklistService.js`).
- **Template download worker**: “download all” path requires `styx_reconciliationBulkChanges` TLC setting; otherwise throws `'Bulk changes not enabled for this TLC'` (`run-template-download.ts`).

## Authorization Rules

- **Checklist signoff UI** resolves `strictSignOffV2` from Harness flag `close_entity-settings_separate-strict-sign-off` and passes it into `useAuthModule` with `SIGN_OFF_AUTHORIZED` (`ui/checklist-client/src/components/ChecklistRowV2/AssigneeSignature.js`).
- **JEM entitlements**: `FQ_JEM` / `FQ_JEM_POSTING_ONLY` documented as entitlement flags in `apps/jem_api/src/packages/feature-flags/constants.ts` (see package README for handler examples).

## State Transition Rules

- JEM **approval / permissions** combine approval status, entity settings (`approvalWorkflowEnabled`), approval rules, and state machine (`getPermissionsV2` + `useMachine`). Exact transition matrix not reproduced here — implementation is the source of truth.

## Cross-module Notes

- **Standalone repos (outside this monorepo):** `FloQastInc/checklist_lambdas`, `checklist-service`, `reconciliations_service`, `reconciliations_lambdas` implement overlapping checklist/recs paths — mined rules live in `domain_knowledge/repo_rules/checklist_lambdas.md`, `checklist-service.md`, `reconciliations_service.md`, `reconciliations_lambdas.md`; keep SIL/SSO flag strings aligned with this repo’s UI apps.
- **JEM API vs JEM client**: API uses `getFlagState` + `FEATURE_FLAGS` from `src/packages/feature-flags`; client uses `useJemFeatureFlag` / `getJemFeatureFlag` bridging to shared FF SDK (`ui/jem-client` does not call `useFeatureFlag` from `@floqastinc/ff-react` directly in the JEM-specific hook — see `useJemFeatureFlag.ts` comment).
- **Checklist vs Recs vs close-client-v2**: checklist and close-client-v2 share the same **feature flag registry entries** for patch save, strict sign-off, and SIL (`feature-flags.js` in each app); recs-client reuses the same Harness **string keys** for strict sign-off and SIL with additional helpers (`reconciliationRow.js`, `featureFlags.js`).
- **todos_api vs checklist Lambda**: checklist item reads are either **local aggregation** or **delegated Lambda** depending on `TDL_Expanded_Range` — behavior must stay consistent across that boundary for(assignee, due-date) semantics.
- **Reconciliations worker**: reads multiple behaviors from **TLC `modules`** object (`multiCurrency`, NetSuite locations, Workday column specifier), not only from a single flags provider.

## Failure Patterns (from code signals)

### Pattern: Batch export 403 when flag off
- **Description**: Users or integrations cannot create an export batch even when data is valid.
- **Root cause**: `close_jem_batch-export` evaluated false for TLC.
- **Signal**: `create-batch-for-export.ts` throws `ForbiddenError`.

### Pattern: Stale or split checklist procedure source
- **Description**: Procedure lists differ between tenants or code paths depending on whether expanded-range aggregation or Lambda listing is used.
- **Root cause**: `TDL_Expanded_Range` toggles between two implementations with different query/filter behavior.
- **Signal**: `apps/todos_api/src/services/checklistService.js` branching.

### Pattern: SIL / strict sign-off drift across surfaces
- **Description**: Checklist auth allows signoff while recs row disables toggle (or vice versa) when flag keys or company `singleItemLock` / `LOCK_ALL` disagree.
- **Root cause**: Same **Harness key strings** must align across checklist-client, recs-client, and backend lock payloads (`lockStatus`).
- **Signal**: Comments in `ReconciliationRow/index.js` and `AssigneeSignature.js` combining SIL + strict sign-off flags.

### Pattern: Checklist performance flag name mismatch
- **Description**: Engineers search for `CLOSE_PERFORMANCE_Q4_FEBRUARY` in code but Harness receives `scalability_performance_q1_feb`.
- **Root cause**: Internal `FF_KEYS` constant name differs from deployed flag `name` in `FF_INFO`.
- **Signal**: `ui/checklist-client/src/constants/feature-flags.js`.

## Feature Flag Notes

- **`close_jem_workday_ga`**: controls retry / validation paths and scheduled-reversal sync gating — **tests** in `post-failed-journal-entry.test.ts` label “legacy” vs “retry-enabled” by flag state.
- **`close_locking_single-item-lock` / `close_entity-settings_separate-strict-sign-off`**: **already captured** in root `domain_context.md`; recs + checklist both consume — add tests when touching either client.
- **JEM `TLC_MODULE_FLAGS_WHITELIST`**: only listed keys read from TLC modules; others use Harness — misclassification breaks flag reads in production (`constants.ts`).
