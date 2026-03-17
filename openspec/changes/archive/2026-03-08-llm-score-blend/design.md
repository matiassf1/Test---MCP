# Design: llm-score-blend

## Decisiones técnicas

### Decisión: 65/35 como pesos del blend (fórmula/LLM)

**Alternativas:** 50/50; 80/20; LLM como override absoluto.

**Rationale:** La fórmula mecánica es objetiva y reproducible; el LLM aporta juicio cualitativo pero puede alucinar o ser inconsistente entre llamadas. 65/35 da peso mayor a los datos objetivos mientras incorpora el juicio cualitativo de forma significativa. 50/50 daría demasiado poder a una fuente no determinista.

### Decisión: Solo Anthropic/Claude activa el blend; OpenRouter/OpenAI no

**Alternativas:** cualquier proveedor AI activa el blend.

**Rationale:** `AIAnalyzer` usa el sistema prompt de Claude (más largo, con contexto de FloQast completo) y el SDK de Anthropic directamente. Para OpenRouter/OpenAI se usa `try_quality_score_openrouter()` que tiene un prompt mínimo optimizado para JSON — no tiene el contexto de calidad completo. Mezclar ambos podría introducir inconsistencias en el score.

### Decisión: `llm_quality_score` persistido en PRMetrics

**Alternativas:** solo persistir el score final blended.

**Rationale:** Tener el score del LLM separado del score final permite auditar cuánto influyó el LLM en cada PR. Es útil para calibrar los pesos del blend con datos reales.

### Decisión: Branch A (LLM coverage) toma prioridad sobre Branch B (CI) en la fórmula

**Alternativas:** usar el máximo entre LLM y CI; promediarlos.

**Rationale:** La cobertura de CI mecánica tiende a ser 0% cuando no hay datos de CI disponibles, lo que penaliza injustamente a PRs bien testeados. La estimación del LLM, aunque aproximada, es más informativa que 0%. El descuento de 0.85 en Branch A ya compensa la menor precisión de la estimación.
