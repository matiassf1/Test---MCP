# Evidence resolution layer (detection → validation → risk)

## Problem

Domain heuristics and repo scans produce **structural** signals (keyword/path overlap). The workflow LLM produces **contextual** interpretation. Previously, `is_hard=True` heuristics always won in risk scoring, even when `DOMAIN_STRUCT` said **no invariant violations** — causing false HIGH risk.

## Model

1. **Detection** — `run_domain_heuristics`, repo analyzer, flags (unchanged).
2. **Validation** — `signal_validator.apply_evidence_resolution` runs **after** `merge_llm_domain_struct`, using:
   - Parsed **contradictions** (hard invariant heuristic vs empty / NONE `VIOLATED_INVARIANTS`).
   - Optional narrative reinforcement (`DOMAIN_EVIDENCE_NARRATIVE_DISMISSAL`).
3. **Risk** — `compute_risk` uses `validated_hard_signals()` so **dismissed** rows do not add domain points or force HIGH.

`behavior_verifier` can set `validation_status=dismissed` earlier when the diff shows no guard removal.

## Configuration

| Env / field | Default | Meaning |
|-------------|---------|---------|
| `DOMAIN_EVIDENCE_VALIDATION_ENABLED` | `false` | Enable the layer (requires workflow analysis + merge). |
| `DOMAIN_EVIDENCE_DISMISS_ON_LLM_NO_VIOLATIONS` | `true` | Dismiss hard `invariant_violation` when a matching contradiction claims no violations. |
| `DOMAIN_EVIDENCE_NARRATIVE_DISMISSAL` | `false` | Extra dismissal if workflow text matches “safe” regex **and** a contradiction exists (riskier). |
| `DOMAIN_EVIDENCE_UNCERTAIN_WEIGHT` | `0.5` | Reserved for partial scoring on `uncertain` status. |

## Pipeline order

```
run_domain_heuristics  →  …  →  workflow LLM  →  merge_llm_domain_struct
  →  apply_evidence_resolution  →  sync_legacy_domain_lists
  →  compute_risk
```

## `DomainSignal` fields

- `validation_status`: `unvalidated` | `candidate` | `confirmed` | `dismissed` | `uncertain`
- `validation_reason`, `validation_source` (`none` | `behavior_verifier` | `evidence_layer`)

## `HeuristicLLMContradiction.resolution`

- `heuristic_precedence` — default when the layer is off or no dismissal matched.
- `evidence_dismissed` — heuristic was downgraded after validation.
- `evidence_uncertain` — reserved.
