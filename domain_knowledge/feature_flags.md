# Feature flags — mined (FloQast)

Parsed by `DomainContextEnricher`: sections **`## Harness Flags`** and **`## tlcModules`** must use bullet lines starting with ``- `key`:`` ….

## Harness Flags

- `close_locking_single-item-lock`: SIL; checklist + recs UI + `checklist_lambdas` `update-lock-status`; legacy vs new path in middleware comments.
- `close_entity-settings_separate-strict-sign-off`: Strict sign-off V2; `reconciliations_lambdas` `signoff.utils.js`; checklist `AssigneeSignature`; `checklist_lambdas` constants.
- `close_checklist_patch_save`: Checklist patch-save; `checklist-client` / `close-client-v2` registries.
- `scalability_performance_q1_feb`: Harness name for checklist perf (`CLOSE_PERFORMANCE_Q4_FEBRUARY` in `checklist-client` FF_INFO).
- `platform_performance_q4-improvements`: Platform Q4 perf umbrella (`checklist-client` FF_INFO).
- `platform_performance_q4-improvements_companies`: Companies slice; `recs-client` Dependencies.
- `platform_performance_q4-improvements_users`: Users slice (`checklist-client` FF_INFO).
- `close_jem_workday_ga`: JEM; scheduled-reversal sync gating Workday-class ERPs (`jem_api` `getPermissionsV2`).
- `close_jem_batch-export`: JEM batch export; forbidden if off (`create-batch-for-export.ts`).
- `close_jem_sync`: JEM field-config sync (`syncFieldConfig.ts`).
- `close_jem_sftp_export_fq_url`: SFTP outbound FQ URLs (`processOutboundJournalEntries.ts`).
- `close_jem_sftp_export_csp_doc_links`: SFTP CSP doc links (same area).
- `close_jem_notifier_ecs_queue_routing`: Notifier ECS queue routing (`jem_api`, `jem_sync-worker`).
- `close_jem_approval_machine_v2`: JEM approval state machine v2.
- `close_jem_presend_status_check_v2_cutover`: JEM presend status check cutover (declared in `FEATURE_FLAGS`).
- `close_jem_sidecar-required`: JEM sidecar (declared in `FEATURE_FLAGS`).
- `close_jem_clientside_error_reporting`: JEM client error reporting (`jem-client` registry).
- `close_jem_sftp_onboarding_ux`: Maps from `JEM_SFTP_ONBOARDING_UX` via `HARNESS_FLAG_NAMES`.
- `close_jem_backend_error_banner`: JEM backend error banner (`jem-client`).
- `close_recs_template_download_async`: Rec settings async template download (`rec-settings-client`).
- `close_ai_matching_je_rules`: AI matching JE rules UI (`matching-ai-client`, `je-rules-client`).
- `close_ai_matching_scale_je_sync`: AI matching JE sync scale (`useJemSyncStatus.js`).
- `close_amort_sftp_jeposting`: Amortization SFTP JE posting (`amortization` MainButtons).
- `close_amort_workday_jeposting`: Amortization Workday JE posting (`amortization` MainButtons).
- `close_balance_api_migration`: Recs service; gates `CoreDataBalanceClient` vs legacy `getAccountPeriodActivity` (`reconciliations_service` `core-data-balance-client.ts`).
- `close_workday_currency_account_balance_filter`: Recs completeness / TLC module setting (`completeness-service.ts`).
- `close_workday_column_specifier`: Workday column specifier; completeness + template download + `reconciliations_lambdas` xlsx/template paths.
- `close_workday_all_export_upload`: Recs lambdas XLSX export branches (`xlsx.service.js`).
- `transform_blocks-checklist_signoff`: Checklist signoff transform block (`checklist-client` `AssigneeSignature.js`).

## tlcModules

- `TDL_Expanded_Range`: `todos_api` — expanded checklist query vs proxy to `fq-checklist-item:live` (`checklistService.js`).
- `clio_profileSettingsUserPreferences`: Close setup new-user i18n (`close-setup-client` `newUserSetup.js`).
- `close_workday_column_specifier`: TLC modules blob; reconciliations worker + completeness.
- `recs_multiCurrency`: Template download / export options (`reconciliations_core-worker` `run-template-download.ts`).
- `romulus_netsuite_locations`: Same (NetSuite locations).
- `styx_reconciliationBulkChanges`: Bulk template export gate (`run-template-download.ts`).
- `soxControls`: Template download SOX fields (`getTlcModuleSetting`).
- `close_entity-settings_separate-strict-sign-off`: Surfaced as module in some recs TLC/module tests (same string as Harness flag).

---

## Notes (not parsed by enricher)

### Monorepo `close` (canonical for many apps)

See `domain_knowledge/repo_rules/close.md`. JEM canonical flag list: `apps/jem_api/src/packages/feature-flags/constants.ts`; resolution: `getFlagState` + `TLC_MODULE_FLAGS_WHITELIST` per `feature-flags/README.md`.

### Standalone repos (2026-03-31 mines)

- **`checklist_lambdas`**: `src/shared/constants/constants.js` — `STRICT_SIGNOFF`, `SINGLE_ITEM_LOCK`; `update-lock-status.js` documents legacy vs SIL paths.
- **`reconciliations_service`**: `completeness-service.ts` — Workday TLC module keys; `close_balance_api_migration` in balance client docstring.
- **`reconciliations_lambdas`**: `signoff.utils.js` — strict sign-off V2 with `close_entity-settings_separate-strict-sign-off`; XLSX `close_workday_all_export_upload`.
- **`checklist-service`**: No `close_*` string matches in sampled `src/` — flags likely evaluated via shared middleware / ECS parity with monorepo + `fq-schemas`.
