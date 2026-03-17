from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from src.change_analyzer import ChangeAnalyzer
from src.confluence_service import ConfluenceService, build_confluence_context
from src.copy_detector import CopyDetector
from src.cross_repo_fetcher import CrossRepoSiblingFetcher
from src.github_service import GitHubService
from src.jira_invariant_extractor import JiraInvariantExtractor
from src.jira_service import JiraService, extract_ticket
from src.metrics_engine import MetricsEngine
from src.models import BusinessRuleContext, FileChange, PRMetrics
from src.risk_analyzer import compute_risk
from src.storage import JSONStorage, StorageBackend
from src.test_detector import TestDetector
from src.test_invariant_validator import TestInvariantValidator


class PRAnalysisPipeline:
    """Orchestrates the full PR analysis flow.

    Coordinates all services and produces a ``PRMetrics`` object.  The CLI
    delegates to this pipeline so that analysis logic lives in one place and can
    be reused by the tool API, tests, or any future agent/MCP integration.

    All service dependencies are injected, defaulting to sensible instances when
    not provided.  This makes the pipeline easy to test with mocks.
    """

    def __init__(
        self,
        github_service: Optional[GitHubService] = None,
        jira_service: Optional[JiraService] = None,
        change_analyzer: Optional[ChangeAnalyzer] = None,
        test_detector: Optional[TestDetector] = None,
        storage: Optional[StorageBackend] = None,
        confluence_service: Optional[ConfluenceService] = None,
        use_cache: bool = False,
        cache_dir: str = ".cache",
        cache_ttl: int = 3600,
    ) -> None:
        raw_gh = github_service or GitHubService()

        if use_cache:
            from src.cache import CachedGitHubService
            self._gh = CachedGitHubService(
                raw_gh, cache_dir=cache_dir, ttl_seconds=cache_ttl
            )
        else:
            self._gh = raw_gh  # type: ignore[assignment]

        self._jira: Optional[JiraService] = jira_service
        self._analyzer: ChangeAnalyzer = change_analyzer or ChangeAnalyzer()
        self._detector: TestDetector = test_detector or TestDetector()
        self._storage: StorageBackend = storage or JSONStorage()
        self._engine = MetricsEngine(storage=self._storage)
        self._confluence: Optional[ConfluenceService] = confluence_service or self._build_confluence_service()
        self.timings: dict[str, float] = {}  # step → elapsed ms (populated after analyze_pr)

    # ------------------------------------------------------------------
    # Primary entry point
    # ------------------------------------------------------------------

    def analyze_pr(
        self,
        repo: str,
        pr_number: int,
        repo_path: Optional[str] = None,
    ) -> PRMetrics:
        """Run the full analysis pipeline for a single PR.

        Steps:
        1. Fetch PR metadata from GitHub
        2. Extract and fetch Jira issue
        3. Analyse changed files (production vs test split)
        4. Detect and classify test files
        5. Run pytest coverage (only when ``repo_path`` is provided)
        6. Compute and return ``PRMetrics``

        Never raises — failures in optional steps (Jira, coverage) are captured
        and the pipeline continues with degraded data.
        """
        self.timings = {}
        t_total = time.perf_counter()

        # ---- 1. GitHub PR metadata ------------------------------------
        t = time.perf_counter()
        pr = self._gh.get_pull_request(repo, pr_number)
        author = self._gh.get_author(pr)
        title = self._gh.get_title(pr)
        pr_date = getattr(pr, "merged_at", None) or getattr(pr, "created_at", None)
        branch = getattr(pr.head, "ref", "") or ""
        description = pr.body or ""
        self.timings["github_pr"] = (time.perf_counter() - t) * 1000

        # Extract Jira ticket (pure string — no I/O)
        jira_ticket = extract_ticket(title=title, branch=branch, description=description)

        # ---- 2+1b. Parallel: file changes & Jira ----------------------
        # get_changed_files and jira fetch are independent network calls — run together
        t = time.perf_counter()
        file_changes: list[FileChange] = []
        jira_issue = None

        def _fetch_files() -> list[FileChange]:
            return self._gh.get_changed_files(pr)

        def _fetch_jira():
            if not jira_ticket:
                return None
            jira_svc = self._jira or self._build_jira_service()
            if jira_svc is None or not jira_svc.is_available():
                return None
            try:
                return jira_svc.fetch_issue(jira_ticket)
            except Exception:
                return None

        with ThreadPoolExecutor(max_workers=2) as pool:
            files_fut = pool.submit(_fetch_files)
            jira_fut = pool.submit(_fetch_jira)
            file_changes = files_fut.result()
            jira_issue = jira_fut.result()

        self.timings["github_files_and_jira"] = (time.perf_counter() - t) * 1000

        # ---- 2b. Confluence docs (optional, requires CONFLUENCE_BASE_URL + CONFLUENCE_TOKEN) ----
        confluence_context = ""
        if self._confluence and self._confluence.is_available() and jira_ticket:
            try:
                ticket_description = jira_issue.description if jira_issue else ""
                pages = self._confluence.get_pages_for_ticket(jira_ticket, description=ticket_description or "")
                confluence_context = build_confluence_context(pages)
            except Exception:
                pass  # Confluence fetch failure is non-fatal

        # ---- 3. Change analysis (in-memory) ---------------------------
        t = time.perf_counter()
        production_changes = self._analyzer.filter_production_changes(file_changes)
        test_file_changes = self._analyzer.filter_test_changes(file_changes)
        lines_modified = self._analyzer.total_modified_lines(production_changes)
        production_lines_added = self._analyzer.total_added_lines(production_changes)
        test_lines_added = self._analyzer.total_added_lines(test_file_changes)
        test_files = self._detector.detect(file_changes)
        diff_coverage = self._analyzer.estimate_diff_coverage(production_changes, test_file_changes)
        pairing_rate = self._analyzer.compute_test_file_pairing(production_changes, test_file_changes)
        assertion_count = self._analyzer.count_test_assertions(test_file_changes)
        has_testable_code = len(production_changes) > 0
        is_modification_only = has_testable_code and production_lines_added == 0 and lines_modified > 0
        # Contract-only: consider all non-test paths (incl. generated/spec); production_changes
        # excludes generated, so we'd miss domain.oas3 + generated/ and never flag contract-only.
        from src.file_classification import is_contract_only_pr, is_test_file
        all_non_test_paths = [
            f.filename for f in file_changes
            if not is_test_file(f.filename) and f.status != "removed"
        ]
        is_contract_only = is_contract_only_pr(all_non_test_paths)
        self.timings["change_analysis"] = (time.perf_counter() - t) * 1000

        # ---- 4. Coverage ----------------------------------------------
        # Only mechanical source: Jest --findRelatedTests (requires local repo_path).
        # Anything else (CI artifacts, Codecov, Sonar) is skipped — the LLM
        # estimate in step 6 covers repos without a local checkout.
        t = time.perf_counter()
        lines_covered = 0
        coverage_result = None
        if repo_path:
            coverage_result = self._fetch_jest_coverage(
                repo_path=repo_path, file_changes=production_changes,
            )
            if coverage_result and coverage_result.ran_successfully:
                lines_covered = coverage_result.lines_covered
        self.timings["coverage"] = (time.perf_counter() - t) * 1000

        # ---- 5. Metrics -----------------------------------------------
        t = time.perf_counter()
        metrics = self._engine.compute_pr_metrics(
            pr_number=pr_number,
            author=author,
            title=title,
            repo=repo,
            file_changes=file_changes,
            test_files=test_files,
            lines_covered=lines_covered,
            lines_modified=lines_modified,
            jira_ticket=jira_ticket,
            jira_issue=jira_issue,
            pr_date=pr_date,
            coverage_result=coverage_result,
            production_lines_added=production_lines_added,
            test_lines_added=test_lines_added,
            diff_estimated_coverage=diff_coverage,
            test_file_pairing_rate=pairing_rate,
            assertion_count=assertion_count,
            has_testable_code=has_testable_code,
            is_modification_only=is_modification_only,
        )
        metrics.ai_estimated_coverage = diff_coverage
        if is_contract_only:
            metrics.is_contract_only = True
            metrics.testing_quality_score = 7.0

        # ---- 5b. Risk scoring (always runs, no AI key needed) ---------
        from src.file_classification import is_test_file as _is_test_file
        prod_diff = "\n".join(
            fc.patch for fc in file_changes
            if fc.patch and not _is_test_file(fc.filename)
        )
        test_diff = "\n".join(
            fc.patch for fc in file_changes
            if fc.patch and _is_test_file(fc.filename)
        )
        risk_level, risk_points, risk_factors = compute_risk(metrics, prod_diff, test_diff)
        metrics.risk_level = risk_level
        metrics.risk_points = risk_points
        metrics.risk_factors = risk_factors

        # ---- 5c. Business rule violation detection (all layers, no AI key needed) ----
        biz_context = self._run_business_rule_detection(
            file_changes=file_changes,
            jira_issue=jira_issue,
        )
        metrics.copy_flags = biz_context.copy_flags
        metrics.jira_invariants = biz_context.jira_invariants
        metrics.test_invariants = biz_context.test_invariants

        self.timings["metrics"] = (time.perf_counter() - t) * 1000

        # ---- 6. AI report (narrative) + LLM coverage estimate (requires AI_ENABLED or OPENROUTER_API_KEY) ----
        # When OPENROUTER_LIGHT_MODE=true: only try_estimate_coverage (1 call/PR) to avoid 429.
        t = time.perf_counter()
        from src.ai_reporter import try_generate_report, try_estimate_coverage
        from src.metrics_engine import _compute_testing_quality_score

        try:
            from src.config import settings
            light = getattr(settings, "openrouter_light_mode", False)
        except Exception:
            light = False

        if not light:
            metrics.ai_report = try_generate_report(
                metrics,
                confluence_context=confluence_context,
                business_rule_context=biz_context,
            )
        metrics.llm_estimated_coverage = try_estimate_coverage(metrics)

        # Recompute quality score whenever LLM coverage is available (preferred over CI)
        if metrics.llm_estimated_coverage is not None:
            metrics.testing_quality_score = _compute_testing_quality_score(
                change_coverage=metrics.change_coverage,
                test_lines_added=metrics.test_lines_added,
                production_lines_added=metrics.production_lines_added,
                diff_estimated_coverage=metrics.ai_estimated_coverage,
                test_file_pairing_rate=metrics.test_file_pairing_rate,
                llm_estimated_coverage=metrics.llm_estimated_coverage,
            )

        # Optional: blend with qualitative LLM score (skipped in light mode to reduce 429)
        if not light and metrics.has_testable_code:
            from src.ai_analyzer import try_analyze
            from src.ai_reporter import try_quality_score_openrouter
            q: Optional[float] = None
            analysis, _ = try_analyze(metrics)
            if analysis is not None and getattr(analysis, "ai_quality_score", None) is not None:
                q = max(0.0, min(10.0, float(analysis.ai_quality_score)))
            if q is None:
                q = try_quality_score_openrouter(metrics)
            if q is not None:
                metrics.llm_quality_score = round(q, 2)
                # Final score: 65% formula (coverage/ratio/pairing) + 35% LLM qualitative opinion
                blended = 0.65 * metrics.testing_quality_score + 0.35 * metrics.llm_quality_score
                metrics.testing_quality_score = round(min(max(blended, 0.0), 10.0), 2)

        # Contract-only: keep neutral score (overrides any blend/recompute above)
        if is_contract_only:
            metrics.testing_quality_score = 7.0

        # Extract spec violations, business rule risks, and apply LLM risk upgrade from AI report
        if metrics.ai_report:
            from src.report_generator import _extract_spec_violations, _extract_business_rule_risks
            metrics.spec_violations = _extract_spec_violations(metrics.ai_report)
            metrics.business_rule_risks = _extract_business_rule_risks(metrics.ai_report)
            # Upgrade risk level one step if LLM suggests higher risk
            import re as _re
            llm_risk_match = _re.search(
                r"risk[_\s]level[:\s]+([A-Z]+)", metrics.ai_report, _re.IGNORECASE
            )
            if llm_risk_match:
                llm_suggestion = llm_risk_match.group(1).upper()
                _, _, _ = compute_risk(
                    metrics, prod_diff, test_diff, llm_risk_suggestion=llm_suggestion
                )
                _RANK = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}
                _FROM_RANK = {1: "LOW", 2: "MEDIUM", 3: "HIGH"}
                current = _RANK.get(metrics.risk_level or "LOW", 1)
                suggested = _RANK.get(llm_suggestion, 0)
                if suggested > current:
                    metrics.risk_level = _FROM_RANK.get(min(current + 1, 3), metrics.risk_level)

        self.timings["ollama"] = (time.perf_counter() - t) * 1000

        self.timings["total"] = (time.perf_counter() - t_total) * 1000
        return metrics

    def save(self, metrics: PRMetrics) -> object:
        """Persist metrics via the configured storage backend."""
        return self._engine.save_pr_metrics(metrics)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _build_confluence_service(self) -> Optional[ConfluenceService]:
        """Build a ConfluenceService from settings; returns None if not configured."""
        try:
            from src.config import settings
            if settings.confluence_base_url and settings.confluence_token:
                return ConfluenceService(
                    base_url=settings.confluence_base_url,
                    token=settings.confluence_token,
                )
        except Exception:
            pass
        return None

    def _build_jira_service(self) -> Optional[JiraService]:
        """Lazily build a JiraService; return None if not configured."""
        try:
            svc = JiraService()
            return svc if svc.is_available() else None
        except Exception:
            return None

    def _fetch_jest_coverage(
        self,
        repo_path: str,
        file_changes: list[FileChange],
    ) -> Optional[object]:
        """Run Jest --findRelatedTests against the local repo checkout."""
        try:
            from src.coverage_providers.jest_runner import JestRunner
            return JestRunner(repo_path).get_coverage(file_changes)
        except Exception:
            return None

    def _run_business_rule_detection(
        self,
        file_changes: list[FileChange],
        jira_issue: Optional[object],
    ) -> "BusinessRuleContext":
        """Run all four business rule violation detection layers.

        Each layer is isolated in a try/except — a single layer failure never
        aborts the pipeline.  Returns a ``BusinessRuleContext`` with whatever
        signals were collected.
        """
        copy_flags: list[dict] = []
        jira_invariants: list[str] = []
        test_invariants: list[str] = []
        sibling_refs: list[dict] = []

        # Layer 1: intra-PR copy detection
        try:
            copy_flags = CopyDetector().detect(file_changes)
        except Exception:
            pass

        # Layer 2: Jira description invariant extraction
        try:
            if jira_issue is not None:
                description = getattr(jira_issue, "description", None) or ""
                summary = getattr(jira_issue, "summary", None) or ""
                ctx = JiraInvariantExtractor().extract(description, summary)
                if ctx.has_porting_signal:
                    jira_invariants = ctx.invariants
        except Exception:
            pass

        # Layer 3: cross-repo sibling context
        try:
            from src.config import settings
            if getattr(settings, "enable_cross_repo_siblings", True):
                sibling_refs = CrossRepoSiblingFetcher(self._gh).fetch(file_changes)
        except Exception:
            pass

        # Layer 4: test-derived invariant validation
        try:
            from src.config import settings
            if getattr(settings, "enable_test_invariants", True):
                threshold = getattr(settings, "test_invariant_threshold", 0.8)
                test_invariants = TestInvariantValidator(threshold=threshold).extract(file_changes)
        except Exception:
            pass

        return BusinessRuleContext(
            copy_flags=copy_flags,
            jira_invariants=jira_invariants,
            test_invariants=test_invariants,
            sibling_refs=sibling_refs,
        )
