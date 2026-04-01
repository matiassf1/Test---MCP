# Domain Rules — checklist-service

Mined: 2026-03-31 from local clone at `/Users/c-matiasgabrielsfer/Desktop/Test---MCP/temp/checklist-service`

## Business Invariants

- Express ECS service for checklist domain; depends on **`@floqastinc/fq-schemas`**, **`fq-auth-middleware`**, **`auth-module-server`**, **`layer-utils`** (`package.json`). **Sampled `src/` grep found no literal `close_*` Harness strings** — feature evaluation may be delegated to shared middleware, env, or parity layers; treat **FloQastInc/close** monorepo + **checklist_lambdas** as sources of truth for SIL/SSO flag keys.

## Authorization Rules

- Uses `fq-auth-middleware` / `auth-module-server`; route-level rules not fully enumerated in this pass.

## State Transition Rules

- (Not mined — read handlers/services in a follow-up pass if needed.)

## Cross-module Notes

- **checklist-service vs checklist_lambdas:** ECS vs Lambda; both must agree on lock and signoff invariants for the same checklist item payloads.

## Failure Patterns (from code signals)

- (No dedicated pattern extracted in shallow mine — rely on `close.md` and `checklist_lambdas.md`.)

## Feature Flag Notes

- **Harness keys:** not listed from direct `close_*` grep in `src/` in this pass; confirm with runtime FF bridge or shared package usage.
