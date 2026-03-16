# Spec: llm-score-blend

---

### Requirement: Blend del score con juicio del LLM

El sistema DEBE combinar el score mecánico con el score cualitativo del LLM cuando `ANTHROPIC_API_KEY` está seteado.

#### Scenario: Anthropic disponible y PR testeable

WHEN `ANTHROPIC_API_KEY` está seteado y `metrics.has_testable_code == True`
THEN llama a `AIAnalyzer.try_analyze()` y blendea: `0.65 × formula_score + 0.35 × llm_quality_score`

#### Scenario: Anthropic no disponible

WHEN `ANTHROPIC_API_KEY` no está seteado
THEN el score es 100% mecánico; no se llama a `AIAnalyzer`

#### Scenario: PR sin código testeable

WHEN `metrics.has_testable_code == False`
THEN no se llama al LLM; el score queda como calculado por la fórmula

#### Scenario: AIAnalyzer no retorna score

WHEN `try_analyze()` retorna `None` o `ai_quality_score` es `None`
THEN el score no es modificado (permanece el mecánico)

---

### Requirement: Persistencia de llm_quality_score

El sistema DEBE guardar el score del LLM en `PRMetrics` para trazabilidad.

#### Scenario: Score obtenido

WHEN el blend es aplicado
THEN `metrics.llm_quality_score` contiene el score original del LLM (antes del blend), redondeado a 2 decimales

---

### Requirement: Preferencia de LLM coverage sobre CI en el scoring

El sistema DEBE usar `llm_estimated_coverage` como fuente primaria cuando está disponible.

#### Scenario: LLM coverage disponible (Branch A)

WHEN `llm_estimated_coverage` es un valor entre 0.0 y 1.0
THEN la fórmula usa `llm_cov × 0.85 × 0.45 + test_ratio × 0.35 + pairing × 0.20`

#### Scenario: Solo CI coverage disponible (Branch B)

WHEN `llm_estimated_coverage` es `None` y `change_coverage > 0`
THEN la fórmula usa `ci_cov × 0.5 + test_ratio × 0.3 + pairing × 0.2`

#### Scenario: Solo estimación por diff heurístico (Branch C)

WHEN ni LLM ni CI coverage están disponibles pero existe `ai_estimated_coverage`
THEN la fórmula aplica descuento: `diff_est × 0.7 × 0.35 + test_ratio × 0.4 + pairing × 0.25`

#### Scenario: Sin ninguna cobertura (Branch D)

WHEN no hay ninguna fuente de coverage
THEN el score se basa solo en `test_ratio` y `file_pairing_rate`

---

### Requirement: Prompts alineados con FloQast

El sistema DEBE incluir contexto de estándares FloQast en los prompts de coverage.

#### Scenario: Prompt de coverage estimado

WHEN se genera el prompt para `try_estimate_coverage`
THEN incluye guías sobre assertions significativas, no inflación de cobertura, y tests de comportamiento
