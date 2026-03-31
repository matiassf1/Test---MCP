## Modules

- **apps/JEM-migrations**  
  Handles database schema migrations and data backfills related to journal entries and accounting entities for the Close system.

- **apps/adhoc-projects_api**  
  Provides API services for managing ad-hoc projects, including project CRUD operations, user access, and project-specific feature flag handling.

- **apps/ai-matching-migrations**  
  Manages migrations related to AI matching functionalities, adjusting account settings, deduplication of access states, and other AI-specific data transformations.

- **apps/apollo_email-event-trigger**  
  Handles email event integrations (Mandrill, SES, SNS), including email receipt, event processing, and notification controls.

- **apps/autorec-amortization-migrations**  
  Performs migrations related to auto-reconciliation and amortization configurations, including depreciation items and journal entry enhancements.

- **apps/autorec-amortization_main**  
  Main application handling auto-reconciliation, amortization processing, configuration management, and journal entry workflows.

## Critical Logic

- **Authorization**  
  - `apps/adhoc-projects_api/src/authorization.js`  
  - `apps/adhoc-projects_api/src/middleware/authorization.js` (likely key middleware enforcing access control)  
  - `apps/adhoc-projects_api/src/validators/validateUserAccessToProject.js`  
  - `apps/autorec-amortization_main/src/authorization.js`

- **Signoff / State Management**  
  - `apps/JEM-migrations/src/migrations/backfillPostStatus.js` and similar "postStatus" migrations manage state transitions and signoff status of journal entries.  
  - `apps/autorec-amortization_main/src/api/journal-entries.js` (likely key for managing journal entry states)  
  - `apps/autorec-amortization_main/src/api/reconciliations.js` (handles reconciliation state)  
  - `apps/ai-matching-migrations/src/migrations/restoreRecsSourceBalanceFromSignOffHistory.js` (manages signoff history restoration)

- **Feature Flags**  
  - `apps/adhoc-projects_api/src/utils/featureFlag.js` (utility for feature flag checks)  
  - `apps/adhoc-projects_api/e2e/scripts/set-temp-feature-flags.js` (test setup for feature flags)  
  - Other feature flag usage likely scattered in `adhoc-projects_api` for conditional logic.

- **Shared State / Constants**  
  - `apps/autorec-amortization_main/src/constants/` (many files containing business constants like `gl.js`, `policies.js`, `rec.js`, `recPeriod.js`, `schedule.js`, etc.)  
  - `apps/apollo_email-event-trigger/src/constants.js`

## Cross-module Patterns

- **Duplicated Helpers and Utilities**  
  - Utility files like `featureFlag.js` in `adhoc-projects_api` suggest a shared pattern but no centralized shared lib found, indicating duplicates or copy-paste may exist in other modules with similar functionality.  
  - Middleware patterns such as authorization and request validation appear in `adhoc-projects_api` but may have parallels or copies in other apps (e.g., `autorec-amortization_main` though not visible here).  
  - Migration scripts have similar naming and structure across various migration apps (`JEM-migrations`, `ai-matching-migrations`, `autorec-amortization-migrations`), indicating repeated logic style but tailored for domain-specific schemas.

- **Reused Logic Patterns**  
  - Common use of `index.js` to aggregate exports is consistent across modules.  
  - Use of separate folders for migrations suggests an architectural pattern to isolate schema/data changes from app logic.  
  - `e2e` and `test` directories under apps follow uniform testing approach with fixtures and utilities.

- **Shared Utilities Copy-Pasted Instead of Imported**  
  - The presence of `featureFlag.js` and utilities under one module without a clear shared lib hints at possible copy-pasting or duplicated implementation across API services.  
  - Separate `storage-provider-service` and `storage-provider-utils` within `adhoc-projects_api` indicate internal modularization but may replicate similar helpers elsewhere.

## Risk Signals

- **Copied Logic Between Modules**  
  - Multiple migration directories across different apps have very similar migration naming conventions and file structures, potentially leading to duplicated migration logic with subtle divergences and maintenance overhead.

- **Helpers with Similar Names in Different Contexts**  
  - `authorization.js` exists both in `adhoc-projects_api` and `autorec-amortization_main`, which may lead to confusion if different implementations or assumptions exist.  
  - `featureFlag.js` is present in `adhoc-projects_api` but unclear if similarly named utilities exist in other apps, risking inconsistent feature flag handling.

- **Modules Missing Obvious Test Coverage**  
  - Migration apps (`JEM-migrations`, `ai-matching-migrations`, `autorec-amortization-migrations`) have associated tests, but core processing or API apps like `autorec-amortization_main` show no explicit test folders or test files in the provided tree fragment (only fixtures and configs). This points to possible gaps in automated unit or integration testing coverage for main business logic layer.  
  - `apollo_email-event-trigger` has tests for controllers and helpers, suggesting good coverage there.

---

This overview should guide inspection and improvement for modular separation, test coverage gaps, and possible refactoring of duplicated logic across modules.