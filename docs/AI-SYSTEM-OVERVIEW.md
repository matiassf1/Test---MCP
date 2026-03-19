# Panorama del sistema — para contexto de IA

Documento de referencia para que una IA entienda qué está desarrollado, integrado, y cuáles son las fortalezas y debilidades del proyecto.

---

## 1. Qué es el sistema

**PR Testing Impact Analyzer** — Herramienta que:

- Obtiene PRs de GitHub y los analiza (diff, tests, cobertura, riesgo).
- Genera reportes en Markdown (calidad de testing, riesgos, recomendaciones).
- Integra Jira (ticket, epic), Confluence (docs), y un artefacto **domain context** (`domain_context.md`) para análisis de riesgo de dominio.
- Expone la misma lógica vía **CLI** y **servidor MCP** (stdio + HTTP/SSE) para Cursor, Claude Desktop o clientes remotos.

**Stack:** Python 3.11+, PyGithub, Pydantic v2, pydantic-settings, múltiples proveedores de LLM (Anthropic, OpenAI, OpenRouter, Ollama), FastMCP.

---

## 2. Funcionalidades desarrolladas e integradas

### 2.0 Repo Analyzer (MVP, experimental)

- **`src/repo_analyzer/`:** Escaneo local del repo (JS/TS/Py) con heurísticas de línea: guards, feature flags, roles, tests (`*.test.*` / `__tests__`), comentarios tipo must/never.
- **CLI:** `python -m src.cli scan_repo_signals --path <repo>` → escribe **`artifacts/repo_signals.json`** (por defecto bajo el repo escaneado).
- **PR analysis:** Con `--repo-path` puede cargarse `artifacts/repo_signals.json`; la sección **Repo behavior signals** solo aparece si **`repo_behavior_report_enabled=true`** (por defecto está apagado para aligerar el reporte).
- **Config:** `repo_signals_json_path`, `repo_behavior_report_enabled` en `config.py` / `.env`.

### 2.1 Núcleo del pipeline (`pr_analysis_pipeline.py`)

| Paso | Qué hace | Dependencias |
|------|-----------|--------------|
| 1 | Fetch PR (metadata, autor, título, descripción, branch) | GitHub |
| 2 | Extracción de ticket Jira (título/branch/descripción) y fetch opcional de issue + epic | Jira (opcional) |
| 2b | Búsqueda Confluence: páginas del ticket + búsqueda por rutas de archivos cambiados | Confluence (opcional) |
| 3 | Análisis de cambios: prod vs test, líneas modificadas/añadidas, pairing rate, assertions, contract-only detection | `ChangeAnalyzer`, `TestDetector`, `file_classification` |
| 4 | Cobertura: Jest `--findRelatedTests` si hay `repo_path` local | `artifact_coverage` / Jest |
| 5 | Cálculo de métricas (testing quality score 0–10, etc.) | `MetricsEngine` |
| 5b | **Shipping metadata:** flags en diff, flags sin test, archivos legacy, ship verdict (SHIP / SHIP_WITH_CONDITIONS / REVIEW / INFORMATIONAL) | `shipping_signals.populate_shipping_metadata` |
| 5c | **Domain heuristics:** si existe `domain_context.md`, se carga y se ejecuta `run_domain_heuristics` sobre prod diff + test diff + file changes; resultado en `metrics.domain_risk_signals` | `domain_context_heuristics`, `domain_knowledge_pipeline.load_domain_context` |
| 5c+ | **Porting signals:** si hay `copy_flags` (CopyDetector + Jira invariant extractor), se añaden señales de “código portado entre módulos” al domain risk | `append_porting_signals` |
| 6 | **Reporte AI:** narrativa (riesgos, recomendaciones, resumen) + estimación de cobertura por LLM; opcional segundo paso de **workflow context analysis** (Jira epic + Confluence + repo docs + diff + domain context) | `ai_reporter`, `contextual_workflow_analysis` |
| 6+ | **Merge LLM → domain:** el markdown del workflow se parsea y se fusiona en `domain_risk_signals` (invariants §2, failure patterns §6); contradicciones heurística vs LLM se guardan en `heuristic_llm_contradictions` | `merge_llm_domain_struct` |
| 6+ | **Evidence resolution (opcional):** si `DOMAIN_EVIDENCE_VALIDATION_ENABLED=true`, `apply_evidence_resolution` puede **despedir** invariantes hard cuando `DOMAIN_STRUCT` dice NONE y hay contradicción registrada; el riesgo usa `validated_hard_signals` | `signal_validator` · ver `docs/EVIDENCE-RESOLUTION-LAYER.md` |
| 6+ | **Riesgo final:** `compute_risk` usa quality score, auth/test pairing, flags, branching, **domain_signals** validadas (puntos por señales hard, cap, opcional HIGH si hard invariant) | `risk_analyzer` |
| 6+ | **Ship summary:** verdict final y bullets ejecutivos | `shipping_signals.finalize_ship_summary` |

Todo lo anterior está **integrado**: un solo `analyze_pr` dispara este flujo; fallos en pasos opcionales (Jira, Confluence, domain, AI) no tiran el pipeline, se degrada con datos parciales.

### 2.2 Domain context y heurísticas

- **`domain_context.md`:** Artefacto Markdown con secciones: §1 overview, §2 invariants, §3 role model, §4 feature flags, §5 cross-module, §6 known failure patterns, §7 review heuristics, etc. Puede ser **escrito a mano** o generado por **`DomainKnowledgePipeline.build()`** (repo + Confluence + Jira, con LLM).
- **`domain_context_heuristics.run_domain_heuristics(domain_md, prod_diff, file_changes, test_diff)`:**  
  Parsea §2, §5, §6; matchea líneas del diff con bullets (invariants, cross-module, failure patterns); emite **`DomainRiskSignals`** con `signals` (tipo `DomainSignal`: type, source, is_hard, confidence, description), listas legacy (`violated_invariants`, `triggered_failure_patterns`, `cross_module_concerns`, `missing_role_coverage`, `early_warnings`).  
  **Precedencia (por defecto):** señales “hard” (desde §2/§5/§6) no son anulables por el LLM narrativo; si el LLM contradice, queda en `heuristic_llm_contradictions`. Con **evidence validation** activada, esas contradicciones pueden bajar la señal a **dismissed** y dejar de sumar puntos (el LLM en `DOMAIN_STRUCT` gana peso real).
- **`risk_analyzer.compute_risk`:** Suma puntos por auth sin test, flags sin test, role gaps, branching; **suma puntos por cada señal hard de domain** (config: `domain_hard_signal_points`, cap `domain_hard_signal_points_cap`); si `domain_force_high_on_hard_invariant` y hay violación de invariant hard, riesgo = HIGH.
- **`shipping_signals.compute_ship_verdict`:** Incluye “domain hot” (hard invariants o contradicciones) para bajar a SHIP_WITH_CONDITIONS o exigir revisión del Domain Risk Analysis.

**Integración:** Domain context se carga por path (config `domain_context_path`, default `domain_context.md`), resuelto desde project root luego cwd; si el archivo no existe, domain heuristics devuelve señales vacías/soft y no rompe el flujo.

### 2.3 Reporte y salidas

- **`report_generator.ReportGenerator`:** Arma el Markdown del reporte: resumen ejecutivo, shipping verdict, Domain Risk Analysis (tabla de señales, invariants, failure patterns, cross-module, role gaps, early warnings, contradicciones heurística vs LLM), AI summary, recomendaciones, scope alignment, etc. Incluye leyenda “How to read this section” (findings = riesgos hipotéticos; QA scenarios = verificación).
- **Salidas:** Reporte en disco (`reports/pr_<n>_report.md`), métricas en JSON/SQLite (`metrics/`), y por MCP/CLI respuestas estructuradas (JSON con métricas, description report opcional).

### 2.4 Otras capacidades

- **Copy/porting detection:** `CopyDetector` + `JiraInvariantExtractor` detectan bloques copiados entre archivos y extraen invariantes desde descripción Jira; se combinan con domain context vía `append_porting_signals`.
- **Cross-repo sibling fetcher:** Obtiene contenido de archivos “hermanos” en otros repos (por convención de rutas) para contexto; 404 se loguean a nivel debug.
- **Cobertura:** Jest (local), Codecov/Sonar/Jest artifacts como proveedores opcionales; si no hay cobertura mecánica, el LLM puede estimar cobertura.
- **Múltiples LLM:** Anthropic, OpenAI, OpenRouter, Ollama; reporte y workflow analysis usan el primer proveedor disponible (configurable).
- **Build domain context:** CLI `build_domain_context` ejecuta `DomainKnowledgePipeline.build(...)` y escribe `domain_context.md` (requiere AI para fases 1–5). Opcional: `--repo-path` (scan local) o `--repo-signals-json` (JSON precomputado) **añade §10 INFERRED FROM CODE** al final; también se guarda `domain_knowledge/repo_signals.json` si escaneaste desde path. Defaults en `.env`: `DOMAIN_BUILD_REPO_PATH`, `DOMAIN_BUILD_REPO_SIGNALS_JSON`.

### 2.5 MCP y CLI

- **MCP:** `analyze_pr`, `get_pr_metrics`, `get_pr_description_report`, `get_repo_summary`, `get_author_summary`, `get_multi_repo_summary`, `list_prs_by_author`, `list_prs_by_jira_ticket`, `analyze_pr_by_jira_ticket`, `analyze_epic`, `batch_analyze_author`, `batch_analyze_repo`.
- **CLI:** `analyze_change`, `analyze_author`, `analyze_epic`, `generate_summary`, `build_domain_context`, `generate_workflow_docs`, `regenerate_epic_report`, etc.

---

## 3. Puntos fuertes

- **Pipeline único y bien definido:** Un solo flujo `analyze_pr` orquesta GitHub, Jira, Confluence, diff, domain context, AI y riesgo; fácil de seguir y extender.
- **Domain-agnóstico en diseño:** Las reglas de dominio viven en `domain_context.md` (y en heurísticas que parsean secciones); no hay hardcodeo de negocio en el código más allá de palabras clave genéricas (auth, signoff, permission, etc.) en `risk_analyzer` y en patrones de §6.
- **Precedencia clara:** Heurísticas hard (§2/§5/§6) > LLM; contradicciones expuestas en el reporte; riesgo y ship verdict reflejan señales de dominio.
- **Degradación controlada:** Fallos en Jira, Confluence, domain load o AI no tiran el análisis; se reporta con los datos disponibles.
- **Configuración centralizada:** `config.Settings` (env + `.env`); paths de domain context, pesos de riesgo, legacy segments, flags de AI/workflow, etc.
- **Doble interfaz:** Mismo backend vía CLI y MCP; reportes reutilizables (Markdown, JSON).
- **Documentación de diseño:** `docs/DOMAIN-KNOWLEDGE-PIPELINE-DESIGN.md` describe el sistema “compilador de conocimiento”, evidence model, conflict detection, source weighting, behavioral diffing y MVP; alineado con feedback Staff+.

---

## 4. Puntos débiles y limitaciones

- **Domain context es estático por ejecución:** Se carga una vez por PR; no hay “conflict detector” en runtime ni “evidence model” estructurado en el artefacto (solo diseño en el doc). Las contradicciones entre invariantes (ej. “reviewer must wait” vs “reviewer can sign anytime”) no se resuelven automáticamente; el reporte puede mostrar ambas.
- **Heurísticas de dominio son léxicas:** Match por palabras clave y secciones de Markdown; no hay AST ni inferencia de comportamiento “before/after” del diff (behavioral diffing no implementado). Riesgo de ruido en §6 (muchos bullets genéricos matchean en PRs grandes).
- **Dependencia de calidad del artefacto:** Si `domain_context.md` está desactualizado o mal escrito, las señales hard pueden ser falsos positivos o perder violaciones reales. No hay loop de incidentes integrado en el pipeline (solo diseño).
- **Tests limitados:** Pocos tests unitarios (p. ej. `test_domain_context_heuristics.py`, `test_contextual_workflow_analysis.py`); el resto del pipeline no está cubierto por tests automáticos visibles en el repo.
- **AI y rate limits:** Varios llamados a LLM por PR (reporte, workflow analysis, calidad, cobertura); en batch o con OpenRouter pueden aparecer 429; `openrouter_light_mode` reduce a una llamada por PR.
- **Cobertura real opcional:** Cobertura “dura” depende de Jest con repo local o de artefactos; en muchos flujos solo hay estimación por LLM o por diff pairing.
- **Ship verdict y riesgo en inglés:** Bullets y etiquetas del reporte están en inglés; no hay i18n.

---

## 5. Resumen para una IA

- **Usar cuando:** Necesites analizar un PR de GitHub con foco en calidad de tests, riesgo (auth, flags, dominio) y generación de reporte; o exponer esa lógica vía MCP/CLI.
- **No asumir:** Que el domain context esté siempre presente ni que las heurísticas sean exactas; que exista cobertura real; que haya tests E2E del pipeline completo.
- **Extensiones naturales (diseño ya descrito):** Evidence model en `domain_context`, conflict detector, source weighting explícito, behavioral diffing en PRs, ingest de incidentes para reforzar invariants/failure patterns.

Si necesitas profundizar en un módulo concreto (p. ej. `domain_context_heuristics`, `risk_analyzer`, `shipping_signals`, `report_generator`), este doc sirve de índice; los nombres de funciones y flujos anteriores son los que debes buscar en el código.
