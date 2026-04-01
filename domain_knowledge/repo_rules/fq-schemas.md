# Domain Rules — fq-schemas

Mined: 2026-03-31 from local clone at `/Users/c-matiasgabrielsfer/Desktop/Test---MCP/temp/fq-schemas`

## Business Invariants

- **Purpose:** Mongoose schemas for FloQast data models (README: *Business Function: Provide Mongoose schemas for FloQast's data models*). **Customer-facing:** No (internal/platform).

## Authorization Rules

- N/A — schema package; auth enforced in services using models.

## State Transition Rules

- N/A at package level; individual schemas encode document shape and indexes.

## Cross-module Notes

- Consumed by **`checklist-service`**, **`reconciliations_service`**, and many lambdas via versioned `git+ssh` / npm deps — **version bumps are contract changes** for checklist/recs ECS and Lambda fleets.

## Failure Patterns (from code signals)

### Pattern: Schema version skew across services
- **Description:** One service updates fq-schemas while another lags — runtime validation or shape mismatches in prod.
- **Root cause:** Independent deploy pipelines per repo.
- **Signal:** Multiple `package.json` pins to different `fq-schemas` semver tags.

## Feature Flag Notes

- N/A — flags live in application repos, not in schema definitions.
