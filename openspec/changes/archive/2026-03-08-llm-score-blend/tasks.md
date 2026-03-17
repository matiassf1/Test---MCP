# Tasks: llm-score-blend

## models

- [x] 1.1 Agregar `llm_quality_score: Optional[float] = None` a `PRMetrics`
- [x] 1.2 Agregar modelo `AIAnalysis` con campos `assessment`, `untested_areas`, `suggestions`, `ai_quality_score`, `reasoning`

## metrics_engine

- [x] 2.1 Refactorizar `_compute_testing_quality_score()` con 4 branches (A: LLM cov, B: CI cov, C: diff heurístico, D: sin coverage)
- [x] 2.2 Branch A usa `llm_estimated_coverage` con descuento 0.85 y peso 0.45
- [x] 2.3 Branch B usa `change_coverage` con peso 0.5 (solo cuando LLM no disponible)

## pr_analysis_pipeline

- [x] 3.1 Llamar a `AIAnalyzer.try_analyze()` cuando `ANTHROPIC_API_KEY` está seteado y `has_testable_code == True`
- [x] 3.2 Guardar `llm_quality_score` en métricas cuando el análisis retorna score
- [x] 3.3 Blend final: `0.65 × formula_score + 0.35 × llm_quality_score`
- [x] 3.4 Clamp del score blended a `[0.0, 10.0]`

## ai_reporter

- [x] 4.1 Actualizar prompt de `try_estimate_coverage` con contexto FloQast (assertions significativas, no inflación)
