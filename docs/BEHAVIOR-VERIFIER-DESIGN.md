# Behavior Verifier — De pattern-matching a evidencia

Este doc describe el problema de **dos verdades** (heurística hard vs LLM) y la arquitectura de **verificación de comportamiento** para bajar falsos positivos y alinear riesgo con evidencia.

---

## 1. El problema que estás viendo

### Dos fuentes, un override rígido

| Fuente | Dice | Origen |
|--------|------|--------|
| **Domain heuristics (hard)** | "Posible violación de invariantes de signoff" / "Riesgo por patrones históricos (recs-client, isWorkflow)" | `domain_context.md` + match por texto (keywords, filenames) |
| **Workflow context (LLM)** | "No hay violaciones" / "Refuerza invariantes" | Razonamiento semántico sobre el diff |

**Hoy:** `if heuristic.is_hard: ignore(LLM)` → **siempre gana la heurística**. Resultado: HIGH RISK + invariant violation aunque el diff no quite guards ni agregue bypasses.

### Bug conceptual

- Las heurísticas están **overfit al dominio histórico** (recs-client, isWorkflow, signoff).
- Disparan con **solo tocar archivos/palabras**, sin comprobar si el **comportamiento** cambió.
- El sistema es **pattern-matching + override**, no **evidence-based reasoning**.

---

## 2. Arquitectura objetivo

### De “patrón → señal hard” a “patrón → hipótesis → verificación → señal”

```
Hoy:
  domain_context bullets + diff keywords → invariant_violation (is_hard=True) → gana sobre LLM

Objetivo:
  domain_context bullets → HYPOTHESIS (ej. "preparer must sign before reviewer")
       ↓
  BEHAVIOR VERIFIER (diff-aware)
       ↓
  verified_violation | not_verified | inconclusive
       ↓
  Si not_verified → downgrade (is_hard=False, confidence *= 0.35)
  Si verified → mantener hard
  Si inconclusive → mantener o bajar un poco
```

### Modelo de decisión (evidencia, no solo precedencia)

| Fuente | Peso | Uso |
|--------|------|-----|
| Repo behavior (tests + código) | Alto | ¿Hay tests que cubren el cambio? ¿Se removieron guards? |
| Incident history | Alto | Si un incidente refuerza la regla, sube confianza. |
| Heurística (domain_context) | Medio | Dispara **hipótesis**; no es verdad hasta verificar. |
| LLM reasoning | Medio | No se ignora; se combina. Si heurística no verificada, LLM puede bajar riesgo. |

**Regla:** Heuristic triggered **but** not verified → **downgrade** (MEDIUM/LOW, no HIGH por ese solo motivo).

---

## 3. Behavior Verifier — contrato

### Entradas

- **prod_diff:** diff unificado del PR (solo prod, no tests).
- **signal_type:** `invariant_violation` | `failure_pattern` (y opcionalmente otros).
- **description:** texto del hallazgo heurístico (ej. "Possible overlap with invariant: ...").

### Salida

- **`verified`** — Hay evidencia en el diff de cambio de comportamiento que podría violar la regla (ej. guard eliminado, bypass agregado). → Mantener señal hard.
- **`not_verified`** — No hay tal evidencia (ej. no se removieron guards, cambio es UI/config). → Downgrade.
- **`inconclusive`** — No se puede decidir con el diff solo. → No forzar hard; opcionalmente bajar confianza un poco.

### Verificaciones concretas (MVP)

1. **Guard removido o debilitado**
   - En el diff, líneas **removidas** (`-`) que parecen guard: `if (...) return`, `if (...) throw`, o llamadas tipo `isAuthorized`, `canSign`, `hasPermission`.
   - Si existe al menos una → **verified**.

2. **Bypass agregado**
   - Líneas **agregadas** (`+`) que introducen condición que podría saltarse el flujo estricto (ej. `if (isWorkflow) return` en contexto de checklist donde no debería haber workflow). Más ruidoso; opcional en MVP.

3. **Sin evidencia**
   - No guards removidos, no bypass obvio → **not_verified** (downgrade).

### Pseudocódigo

```python
def verify_behavior_change(prod_diff: str, signal_type: str, description: str) -> Literal["verified", "not_verified", "inconclusive"]:
    if signal_type not in ("invariant_violation", "failure_pattern"):
        return "inconclusive"

    removed = [line[1:].strip() for line in prod_diff.splitlines() if line.startswith("-") and not line.startswith("---")]
    added   = [line[1:].strip() for line in prod_diff.splitlines() if line.startswith("+") and not line.startswith("+++")]

    # ¿Se eliminó algún guard?
    guard_removed = any(_looks_like_guard(line) for line in removed)
    if guard_removed:
        return "verified"

    # ¿Se agregó bypass obvio? (opcional, más estricto)
    bypass_added = any(_looks_like_bypass(line) for line in added)
    if bypass_added:
        return "verified"

    # Diff no muestra cambio de comportamiento que respalde la violación
    if removed or added:
        return "not_verified"
    return "inconclusive"
```

---

## 4. Integración en el pipeline

### Punto de enganche

**Después** de que `run_domain_heuristics` construya la lista de `DomainSignal` (invariant_violation, failure_pattern, etc.) y **antes** de devolver:

1. Si `domain_verify_behavior_before_hard` está activo (config):
2. Para cada señal con `type in (invariant_violation, failure_pattern)` y `is_hard=True`:
   - `outcome = verify_behavior_change(prod_diff, signal.type, signal.description)`.
   - Si `outcome == "not_verified"`: `signal.is_hard = False`, `signal.confidence *= 0.35`.
   - Si `outcome == "inconclusive"`: opcionalmente `signal.confidence *= 0.8` (no quitar hard por defecto en MVP).

### Config

- **`domain_verify_behavior_before_hard`** (bool, default `True` en el diseño; puede ser `False` al principio para rollout gradual): si True, las señales invariant_violation/failure_pattern pasan por el verifier antes de considerarse hard.

### Riesgo final

- El **Risk Engine** sigue usando `domain_risk_signals` con señales ya posiblemente downgraded.
- Si ninguna señal queda hard para invariant → `domain_force_high_on_hard_invariant` no pisa a HIGH (porque ya no hay hard invariant).
- Así se evita el caso “heurística dice violación pero el diff no lo respalda → HIGH” cuando el LLM y el diff indican lo contrario.

---

## 5. Próximos pasos (opcional)

- **Hypothesis Builder:** convertir cada bullet de §2/§6 en una **hipótesis estructurada** (ej. “preparer before reviewer”) con checklist de verificación explícito.
- **Evidence Aggregator:** combinar verifier + LLM + repo signals (tests, guards en repo) en un único score de evidencia en vez de solo “hard > LLM”.
- **Incidentes:** que incidentes conocidos eleven la confianza de una hipótesis o fuercen verified cuando el patrón coincida.

---

## 6. Resumen

| Antes | Después |
|-------|--------|
| Patrón en diff → invariant_violation hard | Patrón → hipótesis → **verificar en diff** → hard solo si verified |
| Heurística siempre gana sobre LLM | Heurística no verificada → downgrade; se combina con LLM/evidencia |
| Falsos positivos en cambios UI/solo texto | Menos falsos positivos cuando no hay guards removidos ni bypass |

El **Behavior Verifier** es la pieza que convierte “detectamos algo que suele romper invariantes” en “detectamos algo **y** el diff muestra un cambio de comportamiento que lo respalda”.
