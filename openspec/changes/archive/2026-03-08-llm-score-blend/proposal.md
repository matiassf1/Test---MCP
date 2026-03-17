# Proposal: llm-score-blend

## Why

El score de testing quality se calculaba 100% con métricas mecánicas (coverage de CI, ratio líneas test/prod, file pairing). Esto generaba scores que no reflejaban la calidad real: un PR con muchos tests superficiales obtenía score alto. Se necesitaba incorporar el juicio cualitativo de un LLM alineado con los estándares de FloQast.

Además, la cobertura estimada por CI (0% cuando no hay datos) degradaba injustamente el score de PRs bien testeados. La estimación del LLM resultó más representativa que el 0% mecánico.

## What Changes

El score final combina la fórmula mecánica con el juicio del LLM (Claude vía `AIAnalyzer`). Cuando hay estimación LLM de cobertura disponible, se prefiere sobre el 0% de CI.

## Capabilities

### Modified
- **`src/pr_analysis_pipeline.py`** — cuando `ANTHROPIC_API_KEY` está seteado y el PR tiene código testeable, llama a `AIAnalyzer.try_analyze()`; blendea el score resultante: `0.65 × formula_score + 0.35 × llm_quality_score`
- **`src/metrics_engine.py`** — `_compute_testing_quality_score()` usa `llm_estimated_coverage` como fuente primaria cuando está disponible; CI coverage solo como fallback (branch A > B > C > D)
- **`src/models.py`** — nuevo campo `llm_quality_score: Optional[float]` en `PRMetrics`; nuevo modelo `AIAnalysis` con `ai_quality_score`, `untested_areas`, `suggestions`, `reasoning`
- **`src/ai_reporter.py`** — prompts de coverage alineados con FloQast: énfasis en assertions significativas, no inflación de cobertura; contexto de estándares de testing (AAA, behavior-focused, mocking apropiado)

## Impact

- Score puede subir o bajar respecto al cálculo anterior dependiendo del juicio del LLM
- Solo activo cuando `ANTHROPIC_API_KEY` está seteado; sin él el score es 100% mecánico
- `llm_quality_score` queda persistido en `PRMetrics` para trazabilidad
