# Domain Model Consolidation

---

## 1. Modules

### apps/JEM-migrations  
**Responsibility:** Manage database schema and data migrations related to journal entries and close processes.  
**Key differences:** Focused solely on migration scripts impacting journal entry states and financial close cycles.

### apps/adhoc-projects_api  
**Responsibility:** Provide API backend for managing ad hoc projects including full CRUD operations, authorization, feature flag management, and validation layers.  
**Key differences:** Primarily an API service with comprehensive middleware layers for authorization and validation; manages feature flags and user access.

### apps/ai-matching-migrations  
**Responsibility:** Handle migrations related to AI-driven matching features and account settings adjustments.  
**Key differences:** Specialized migrations focused on AI matching data and configurations.

### apps/apollo_email-event-trigger  
**Responsibility:** Process and trigger transactional email events through integration with third-party email services (Mandrill, SES, SNS).  
**Key differences:** Domain focused on event-driven email notification workflows external to core domain models.

### apps/autorec-amortization-migrations  
**Responsibility:** Contains migration scripts for amortization and auto-recurring accounting data/schema changes.  
**Key differences:** Migration-only module specific to amortization and automatic recurring accounting entries.

### apps/autorec-amortization_main  
**Responsibility:** Core domain module managing amortization and auto-recurring accounting logic, including APIs, authorization, constants, and helper functions.  
**Key differences:** Contains both domain logic and API interfaces distinct from migration scripts; distinct from `autorec-amortization-migrations`.

### Shared Utilities (implied)  
**Responsibility:** Provide generic helpers for feature flags, HTTP communications, and storage provider interfaces.  
**Key differences:** Cross-cutting concerns shared between modules, though explicit centralization is unclear.

---

## 2. Domain Rules (Invariants)

- **Authorization Invariants:**  
  - Access to project or amortization resources must be verified at every API interaction using validated authorization logic.  
  - Users must have explicit rights confirmed via validators before any modification or data retrieval is permitted.

- **State Management / Signoff:**  
  - Journal entries and close process statuses can only transition in permitted sequences defined by migration-based state logic.  
  - Signoff histories must be preserved and referenced to restore states reliably.  
  - No unauthorized alterations to signoff or reconciliation states allowed.

- **Feature Flag Enforcement:**  
  - Feature flags must be correctly checked and enforced at runtime to enable or disable features.  
  - Temporary feature flags manipulated during tests must not leak into production behavior.

- **Data Integrity Validations:**  
  - Input data for projects, users, and recurring entries must pass defined validation rules to prevent duplication and maintain integrity.  
  - Middleware layers must reject invalid duplication or malformed requests before reaching business logic.

---

## 3. Roles

### Project User (in adhoc-projects_api)  
- Can create, read, update, and delete ad hoc projects based on assigned permissions.  
- Requires authorization checks for every operation to ensure access compliance.  
- Subject to validation ensuring data consistency and no duplicates.

### Accounting Manager (in autorec-amortization_main)  
- Responsible for managing amortization schedules and automatic recurring entries.  
- Must enforce signoff state transitions according to defined business rules.  
- Can trigger reconciliation operations but constrained by domain invariants preventing invalid state changes.

### System Administrator / Migration Operator  
- Executes migration scripts for domain-specific database changes (journal entries, AI matching, amortization).  
- Must ensure migrations preserve data consistency and do not violate signoff or authorization rules.

---

## 4. Failure Patterns

- **Duplicated Authorization Logic:**  
  Multiple independent authorization implementations across modules lead to inconsistent enforcement and maintenance overhead. Risk of diverging rules causing permission leaks.

- **Migrations Duplication:**  
  Similar migration structures repeated independently in different modules can cause coordination issues and inconsistent handling of domain state transitions.

- **Feature Flag Mismanagement:**  
  Improper cleanup or leakage of test-specific feature flags into production can cause unexpected behaviors or bypasses of critical rules.

- **Validation Gaps:**  
  Missing or incomplete validation layers, especially for project duplication checks or user access, can lead to integrity violations or unauthorized access.

- **State Transition Inconsistencies:**  
  Failure to properly track or enforce signoff history and journal entry post status changes can lead to corrupted reconciliation or close processes.

---

# Summary Notes

- **Centralization Needed:** Authorization, migration handling, and validation logic duplication pose maintainability and correctness risks—consider consolidating shared logic into reusable libraries.  
- **Enforced Invariants:** Authorization, signoff state management, and validation rules are critical invariants to prevent failures seen historically in similar systems.  
- **Failure patterns point to a lack of DRY (Don't Repeat Yourself) principles in critical domain logic and domain state management.**

---

*This consolidation abstracts domain behavior from implementation details and merges overlapping concepts across modules and sources.*