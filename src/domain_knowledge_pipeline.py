"""Domain Knowledge Pipeline — mines repo, Confluence, and Jira to produce domain_context.md.

Phases (1–3 run in parallel, 4–5 run sequentially):
  1. Repo Mining      — extract module structure + critical patterns from GitHub repo tree
  2. Confluence Mining— extract domain rules from wiki pages
  3. Jira Mining      — extract failure patterns from bug/incident tickets
  4. Normalization    — unify the three sources into a coherent domain model
  5. Context Generation — produce domain_context.md for injection into the PR analyzer
  6. (optional) Local repo analyzer — append §10 INFERRED FROM CODE from ``scan_repo_signals`` / local scan

Usage:
  from src.domain_knowledge_pipeline import DomainKnowledgePipeline, load_domain_context

  pipeline = DomainKnowledgePipeline()
  output_path = pipeline.build(
      repo="org/repo",
      jira_project="PROJ",
      confluence_queries=["signoff", "checklist", "authorization"],
      repo_local_path="/path/to/clone",  # optional — appends §10 from RepoAnalyzer
      # repo_signals_json="/path/to/repo_signals.json",  # optional — use precomputed scan
  )

  # In PR analyzer:
  domain_ctx = load_domain_context()  # reads domain_context.md
"""

from __future__ import annotations

import concurrent.futures
import logging
import re
from pathlib import Path
from typing import Optional

from src.confluence_service import ConfluenceService, build_confluence_context
from src.config import settings
from src.github_service import GitHubService

logger = logging.getLogger(__name__)

# Project root (parent of ``src/``) — used so ``domain_context.md`` is found regardless of shell cwd
_PROJECT_ROOT = Path(__file__).resolve().parent.parent

_OUTPUT_DIR = Path("domain_knowledge")
_FINAL_OUTPUT = Path("domain_context.md")

# ---------------------------------------------------------------------------
# Phase 1 — Repo Mining
# ---------------------------------------------------------------------------

_REPO_MINING_SYSTEM = """You are a senior engineer analyzing a large codebase to extract DOMAIN STRUCTURE.

Your goal is NOT to summarize code, but to infer how the system is organized.

## TASK

Given the repository file tree and README, extract:

### 1. Modules
- Identify main domains (e.g. checklist-client, recs-client, lambdas)
- Describe each module's responsibility in 1 line

### 2. Critical Logic Areas
Focus on: authorization, signoff, feature flags, state management.
List: key files and key functions (inferred from names and paths).

### 3. Cross-module Patterns
Detect:
- duplicated helpers across modules (similar function/file names)
- reused logic patterns
- shared utilities that are copy-pasted instead of imported

### 4. Risk Signals
Flag:
- logic that appears copied between modules
- helpers with similar names but different contexts
- modules missing obvious test coverage paths

## OUTPUT

Return structured markdown with exactly these headers:

## Modules
## Critical Logic
## Cross-module Patterns
## Risk Signals

Be concise. Avoid code dumps. Focus on structure and intent."""

# ---------------------------------------------------------------------------
# Phase 2 — Confluence Mining
# ---------------------------------------------------------------------------

_CONFLUENCE_MINING_SYSTEM = """You are extracting DOMAIN RULES from product documentation.

Your goal is to identify how the system SHOULD behave at runtime.

## TASK

From the provided Confluence documents, extract:

### 1. Signoff / Workflow Rules
- ordering requirements (e.g. preparer before reviewer)
- role restrictions and state machine edge cases

### 2. Role Definitions
- what each role can/cannot do
- differences between roles in different module contexts

### 3. Feature Flag Behavior
- what each flag controls
- how behavior changes when flag is on vs off

### 4. Domain Differences
- differences between modules/clients (e.g. checklist vs recs)
- domain-specific invariants that differ across modules

## OUTPUT

## Domain Rules
## Roles
## Feature Flags
## Domain Differences

Only include information relevant to runtime behavior.
Ignore UI descriptions, generic explanations, and setup instructions."""

# ---------------------------------------------------------------------------
# Phase 3 — Jira Mining
# ---------------------------------------------------------------------------

_JIRA_MINING_SYSTEM = """You are analyzing Jira tickets to extract FAILURE PATTERNS.

Focus on bugs, incidents, and regressions. Convert them into reusable review heuristics.

## TASK

For the provided bug/incident tickets:
1. Identify what broke, why it broke, and what domain assumption failed
2. Group related tickets into named patterns
3. Generalize each pattern into a reusable review heuristic

## OUTPUT

## Failure Patterns

For each pattern:
- **Pattern name**: (short, memorable)
- **Description**: what breaks
- **Root cause**: underlying domain assumption that was violated
- **Impact**: blast radius (who/what is affected)
- **Example**: (1 sentence referencing the ticket(s))

Focus on domain mistakes, not syntax bugs.
Generalize — one pattern should cover multiple similar incidents."""

# ---------------------------------------------------------------------------
# Phase 4 — Normalization
# ---------------------------------------------------------------------------

_NORMALIZE_SYSTEM = """You are consolidating multiple knowledge sources into a unified DOMAIN MODEL.

## INPUT
- Repo structure analysis (from codebase)
- Domain rules extracted from documentation
- Failure patterns extracted from incidents

## TASK

Normalize and deduplicate into:

### 1. Modules
- name, responsibility, key differences from sibling modules

### 2. Domain Rules (invariants)
- rules that must always hold at runtime
- prioritize rules that have caused incidents in the past

### 3. Roles
- role behavior and restrictions

### 4. Failure Patterns
- generalized patterns reusable as code review heuristics

## OUTPUT

Return clean, deduplicated markdown. Prioritize clarity over completeness.
Remove implementation details — keep only domain behavior.
If two sources say the same thing, merge them into one bullet."""

# ---------------------------------------------------------------------------
# Phase 5 — Domain Context Generation
# ---------------------------------------------------------------------------

_CONTEXT_GEN_SYSTEM = """You are generating a DOMAIN CONTEXT file for an LLM-powered PR reviewer.

This file will be injected verbatim into a system prompt. The LLM will use it to detect
domain violations, incorrect assumptions, and production risks in pull requests.

## CRITICAL REQUIREMENTS
- Every line must be directly actionable for a code reviewer
- Zero ambiguity — no "it depends", no vague language
- Failure patterns MUST come from real incidents in the provided data
- Cross-module differences MUST be explicitly flagged as distinct (not "similar")
- Total output MUST stay under 2000 tokens

## OUTPUT FORMAT

Produce exactly these 9 sections in this exact order:

---

# DOMAIN CONTEXT

## 1. SYSTEM OVERVIEW

### Modules
- <module-name>
  - Responsibility: <1 line>
(repeat for each module)

---

## 2. DOMAIN INVARIANTS (CRITICAL RULES)

These rules MUST NOT be violated.

- <Invariant category>:
  - <rule>
  - <rule>
(repeat for each category: signoff ordering, feature flag isolation, authorization, etc.)

---

## 3. ROLE MODEL

### Roles

- <Role name>
  - Can: <what this role is allowed to do>
  - Cannot: <what this role must never do>
  - Special behavior: <if applicable — especially for Ops User, Auditor>
  - Risk: <if this role is frequently under-tested, say so>
(repeat for each role)

---

## 4. FEATURE FLAGS

### Known Flags

- <flag-name>
  - Controls: <what behavior it gates>
  - Risk: <what breaks if partially implemented or untested>
(repeat for each flag)

---

## 5. CROSS-MODULE DIFFERENCES (CRITICAL)

These modules DO NOT behave the same.

For Close **ui/** MFEs, always document if applicable:
- **checklist-client:** no workflow-based guards (`!isWorkflow`); strict signoff ordering always.
- **recs-client:** may use workflow conditions; relaxed ordering in some cases.
- 🚨 Never import or replicate recs-client signoff/workflow logic into checklist-client.

- <Module A> vs <Module B>:
  - <Module A>: <what is true here>
  - <Module B>: <what differs here>

⚠️ Never assume logic from <Module B> is valid in <Module A>
(repeat for each dangerous pair)

---

## 6. KNOWN FAILURE PATTERNS

### Pattern: <Name>
- Description: <what breaks>
- Root cause: <domain assumption that was violated>
- Impact: <blast radius>
- Example: <1 sentence from the incidents>

(repeat for each pattern — minimum 3, maximum 8)

---

## 7. REVIEW HEURISTICS (HOW TO THINK)

When analyzing a PR:

- Check if logic:
  - <question 1>
  - <question 2>

- Always verify:
  - <verification 1>
  - <verification 2>

- Be suspicious of:
  - <red flag 1>
  - <red flag 2>

---

## 8. HIGH-RISK AREAS

Focus extra scrutiny on:

- <area 1>
- <area 2>
(list 4–6 specific file paths, function patterns, or logic categories from the repo analysis)

---

## 9. CONFIDENCE GUIDELINES

Raise risk level if:
- <condition 1>
- <condition 2>

Lower risk if:
- <condition 1>
- <condition 2>

---

## IMPORTANT NOTES ON FORMAT
- Use indented bullet points, not prose paragraphs
- Use ⚠️ only for truly dangerous cross-module assumptions
- Never write "N/A" — omit a section only if you have zero data for it
- Failure patterns are the highest-value section: make them specific and grounded"""


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

class DomainKnowledgePipeline:
    """Mines repo, Confluence, and Jira to build a reusable domain_context.md.

    Phases 1–3 run in parallel; phases 4–5 run sequentially.
    Intermediate files are cached in ``domain_knowledge/`` and reused on
    subsequent runs unless ``force_refresh=True``.
    """

    def __init__(
        self,
        github_service: Optional[GitHubService] = None,
        confluence_service: Optional[ConfluenceService] = None,
        output_dir: Optional[Path] = None,
        final_output: Optional[Path] = None,
    ) -> None:
        self._gh = github_service or GitHubService()
        # Prefer explicit confluence_username; fall back to jira_username (same Atlassian account on Cloud)
        _conf_user = (
            getattr(settings, "confluence_username", "") or
            getattr(settings, "jira_username", "")
        )
        self._confluence = confluence_service or ConfluenceService(
            base_url=settings.confluence_base_url,
            token=settings.confluence_token,
            username=_conf_user,
        )
        self._output_dir = output_dir or _OUTPUT_DIR
        self._final_output = final_output or _FINAL_OUTPUT

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def build(
        self,
        repo: str,
        *,
        jira_project: str = "",
        confluence_queries: Optional[list[str]] = None,
        confluence_spaces: Optional[list[str]] = None,
        jira_issue_types: Optional[list[str]] = None,
        max_jira_tickets: int = 100,
        since_days: int = 180,
        force_refresh: bool = False,
        repo_local_path: Optional[str] = None,
        repo_signals_json: Optional[str] = None,
        repos_file: Optional[str] = None,
        enrich: bool = True,
        extract_feature_flags: bool = False,
    ) -> Path:
        """Run the full pipeline and return the path to ``domain_context.md``.

        Args:
            repo: GitHub repo in ``org/name`` format (used for phase 1).
            jira_project: Jira project key (e.g. ``CLOSE``).
            confluence_queries: Domain keywords for Confluence search.
            confluence_spaces: Confluence space keys for bulk mining (new phase 2).
                Defaults to ``settings.confluence_spaces`` split by comma.
            jira_issue_types: Issue types for Jira mining. Defaults to broad set.
            max_jira_tickets: Max tickets to fetch (default 100).
            since_days: Jira ticket recency window in days (default 180).
            force_refresh: Re-run all phases even if cached files exist.
            repo_local_path: Optional local clone for §10 repo analyzer appendix.
            repo_signals_json: Optional precomputed repo_signals.json for §10.
            repos_file: Path to repo_priority_index.yaml for phase 0 / feature flag extraction.
            enrich: When True (default), run DomainContextEnricher after generation.
            extract_feature_flags: When True and repos_file is set, run FeatureFlagExtractor.

        Returns:
            Path to the generated ``domain_context.md``.
        """
        from src.ai_reporter import _is_ai_enabled

        if not _is_ai_enabled():
            raise RuntimeError(
                "Domain knowledge pipeline requires AI. "
                "Set ANTHROPIC_API_KEY, OPENAI_API_KEY, or OPENROUTER_API_KEY."
            )

        self._output_dir.mkdir(exist_ok=True)

        # ---- Phase 0 (optional): load repo priority index ------------------
        priority_repos: list[str] = []
        if repos_file:
            priority_repos = self._load_repos_file(repos_file)
            logger.info("Phase 0: loaded %d repos from %s", len(priority_repos), repos_file)

        # ---- Phases 1–3 in parallel ----------------------------------------
        def _cached(name: str, fn) -> str:  # type: ignore[type-arg]
            path = self._output_dir / name
            if path.exists() and not force_refresh:
                logger.info("Using cached %s", path)
                return path.read_text(encoding="utf-8")
            result: str = fn()
            path.write_text(result, encoding="utf-8")
            logger.info("Wrote %s", path)
            return result

        # Resolve confluence spaces: prefer explicit arg, then settings, then fall back to queries
        spaces = confluence_spaces
        if not spaces:
            spaces_cfg = (getattr(settings, "confluence_spaces", "") or "").strip()
            spaces = [s.strip() for s in spaces_cfg.split(",") if s.strip()] if spaces_cfg else []

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            f1 = executor.submit(_cached, "repo_analysis.md", lambda: self._mine_repo(repo))
            f2 = executor.submit(
                _cached,
                "confluence_rules.md",
                lambda: self._mine_confluence_v2(
                    spaces=spaces,
                    query_terms=confluence_queries or ["signoff", "authorization", "locking", "checklist"],
                ),
            )
            f3 = executor.submit(
                _cached,
                "jira_patterns.md",
                lambda: self._mine_jira_v2(
                    jira_project=jira_project,
                    issue_types=jira_issue_types,
                    max_tickets=max_jira_tickets,
                    since_days=since_days,
                ),
            )
            repo_md = f1.result()
            confluence_md = f2.result()
            jira_md = f3.result()

        # ---- Phase 4: Normalize --------------------------------------------
        normalized = _cached(
            "normalized_domain.md",
            lambda: self._normalize(repo_md, confluence_md, jira_md),
        )

        # ---- Phase 5: Generate final context --------------------------------
        domain_context = self._generate_context(normalized)

        # ---- Phase 6 (optional): repo analyzer appendix --------------------
        signals_doc = self._load_repo_signals_document(repo_signals_json, repo_local_path)
        if signals_doc is not None and signals_doc.signals:
            from src.repo_analyzer.context_appendix import format_domain_context_appendix

            appendix = format_domain_context_appendix(signals_doc)
            domain_context = domain_context.rstrip() + "\n\n" + appendix
            logger.info(
                "Appended §10 repo analyzer appendix (%s signals, %s files scanned)",
                len(signals_doc.signals),
                signals_doc.files_scanned,
            )

        self._final_output.write_text(domain_context, encoding="utf-8")
        logger.info("Domain context written to %s", self._final_output)

        # ---- Phase 5c (optional): feature flag extraction ------------------
        if extract_feature_flags and priority_repos:
            try:
                from src.feature_flag_extractor import FeatureFlagExtractor
                logger.info("Phase 5c: extracting feature flags from %d repos", len(priority_repos))
                extractor = FeatureFlagExtractor()
                result = extractor.extract(priority_repos[:10])  # cap at 10 for speed
                extractor.write_output(result)
                logger.info("Phase 5c: feature flags written")
            except Exception as exc:
                logger.warning("Phase 5c: feature flag extraction failed: %s", exc)

        # ---- Phase 5b (optional): domain context enrichment ----------------
        if enrich:
            try:
                from src.domain_context_enricher import DomainContextEnricher
                logger.info("Phase 5b: enriching domain_context.md")
                DomainContextEnricher().enrich()
                logger.info("Phase 5b: enrichment complete")
            except Exception as exc:
                logger.warning("Phase 5b: enrichment failed: %s", exc)

        return self._final_output

    def _load_repos_file(self, repos_file: str) -> list[str]:
        """Load repo names from a repo_priority_index.yaml file."""
        import yaml as _yaml
        p = Path(repos_file)
        if not p.exists():
            logger.warning("repos_file not found: %s", p)
            return []
        try:
            with open(p, encoding="utf-8") as f:
                entries = _yaml.safe_load(f) or []
            return [e["repo"] for e in entries if isinstance(e, dict) and "repo" in e]
        except Exception as exc:
            logger.warning("Failed to load repos_file %s: %s", p, exc)
            return []

    def _mine_confluence_v2(self, spaces: list[str], query_terms: list[str]) -> str:
        """Phase 2 (v2) — bulk space-scoped Confluence mining."""
        logger.info("Phase 2 (v2): mining Confluence spaces=%s queries=%s", spaces, query_terms)

        if not self._confluence.is_available():
            return "# Confluence Rules\n(Confluence not configured — set CONFLUENCE_BASE_URL and CONFLUENCE_TOKEN)"

        # Try new space-scoped mining first
        if spaces:
            try:
                from src.confluence_domain_miner import ConfluenceDomainMiner
                miner = ConfluenceDomainMiner(confluence_service=self._confluence)
                pages = miner.mine(spaces=spaces, query_terms=query_terms)
                if pages:
                    from src.confluence_service import build_confluence_context
                    context = build_confluence_context(pages, budget=12000)
                    user = f"# Confluence Documentation ({len(pages)} pages)\n\n{context}"
                    return self._llm_call(
                        "Phase 2v2", _CONFLUENCE_MINING_SYSTEM, user,
                        fallback="# Confluence Rules\n(unavailable)"
                    )
                logger.warning("Phase 2 (v2): 0 pages from spaces %s — falling back to keyword search", spaces)
            except Exception as exc:
                logger.warning("Phase 2 (v2): space mining failed: %s — falling back", exc)

        # Fallback: original keyword search
        return self._mine_confluence(query_terms)

    def _mine_jira_v2(
        self,
        jira_project: str,
        issue_types: Optional[list[str]],
        max_tickets: int,
        since_days: int,
    ) -> str:
        """Phase 3 (v2) — broad Jira mining using JiraDomainMiner."""
        logger.info("Phase 3 (v2): mining Jira project=%s", jira_project or "(none)")

        if not jira_project:
            return "# Jira Patterns\n(No Jira project key provided — pass --jira-project)"

        try:
            from src.jira_domain_miner import JiraDomainMiner
            miner = JiraDomainMiner()
            out_path = self._output_dir / "jira_patterns.md"
            miner.mine_and_write(
                project=jira_project,
                issue_types=issue_types,
                max_tickets=max_tickets,
                since_days=since_days,
                output_path=out_path,
            )
            if out_path.exists():
                return out_path.read_text(encoding="utf-8")
        except Exception as exc:
            logger.warning("Phase 3 (v2): JiraDomainMiner failed: %s — falling back", exc)

        # Fallback: original implementation
        return self._mine_jira(jira_project)

    # ------------------------------------------------------------------
    # Phase 6 — Repo signals (local scan or JSON)
    # ------------------------------------------------------------------

    def _load_repo_signals_document(
        self,
        repo_signals_json: Optional[str],
        repo_local_path: Optional[str],
    ):
        """Load or produce RepoSignalsFile for §10 appendix. Returns None if disabled/empty."""
        from pathlib import Path as _Path

        from src.repo_analyzer.analyzer import RepoAnalyzer, load_repo_signals_file, write_repo_signals_json

        path_json = (repo_signals_json or "").strip()
        if path_json:
            p = _Path(path_json).expanduser()
            doc = load_repo_signals_file(p)
            if doc is not None:
                return doc
            logger.warning("repo_signals_json not found or invalid: %s", p)
            return None

        path_repo = (repo_local_path or "").strip()
        if not path_repo:
            pj = (getattr(settings, "domain_build_repo_signals_json", "") or "").strip()
            if pj:
                doc = load_repo_signals_file(_Path(pj).expanduser())
                if doc is not None:
                    return doc
            path_repo = (getattr(settings, "domain_build_repo_path", "") or "").strip()

        if not path_repo:
            return None

        root = _Path(path_repo).expanduser().resolve()
        if not root.is_dir():
            logger.warning("repo_local_path is not a directory: %s", root)
            return None

        logger.info("Phase 6: scanning local repo for structural signals: %s", root)
        doc = RepoAnalyzer().analyze_repo(root)
        try:
            self._output_dir.mkdir(parents=True, exist_ok=True)
            write_repo_signals_json(doc, self._output_dir / "repo_signals.json")
            logger.info("Wrote %s", self._output_dir / "repo_signals.json")
        except Exception as exc:
            logger.debug("Could not write repo_signals.json: %s", exc)
        return doc

    # ------------------------------------------------------------------
    # Phase implementations
    # ------------------------------------------------------------------

    def _mine_repo(self, repo: str) -> str:
        """Phase 1 — extract domain structure from repo file tree + README."""
        from src.ai_reporter import _call_llm

        logger.info("Phase 1: mining repo %s", repo)

        file_paths: list[str] = []
        readme = ""
        try:
            gh_repo = self._gh._client.get_repo(repo)
            tree = gh_repo.get_git_tree(gh_repo.default_branch, recursive=True)
            file_paths = [
                item.path
                for item in (tree.tree or [])
                if item.type == "blob" and not item.path.startswith(".")
            ][:500]
            try:
                readme_file = gh_repo.get_readme()
                readme = readme_file.decoded_content.decode("utf-8", errors="replace")[:3000]
            except Exception:
                pass
        except Exception as exc:
            logger.warning("Phase 1: failed to fetch repo tree for %s: %s", repo, exc)

        tree_text = "\n".join(file_paths[:400]) if file_paths else "(unavailable)"
        user = (
            f"# Repository: {repo}\n\n"
            f"## File tree (first 400 paths)\n```\n{tree_text}\n```\n\n"
            f"## README (excerpt)\n{readme}"
        )
        return self._llm_call("Phase 1", _REPO_MINING_SYSTEM, user, fallback="# Repo Analysis\n(unavailable)")

    def _mine_confluence(self, queries: list[str]) -> str:
        """Phase 2 — extract domain rules from Confluence wiki pages."""
        from src.ai_reporter import _call_llm

        logger.info("Phase 2: mining Confluence queries=%s", queries)

        if not self._confluence.is_available():
            return "# Confluence Rules\n(Confluence not configured — set CONFLUENCE_BASE_URL and CONFLUENCE_TOKEN)"

        pages = []
        seen_ids: set[str] = set()
        for query in queries:
            try:
                found = self._confluence.search_pages_for_domain(
                    file_paths=[query], max_results=5
                )
                for p in found:
                    if p.page_id not in seen_ids:
                        seen_ids.add(p.page_id)
                        pages.append(p)
            except Exception as exc:
                logger.warning("Phase 2: search failed for %r: %s", query, exc)

        if not pages:
            return "# Confluence Rules\n(No pages found — check CONFLUENCE_BASE_URL and query terms)"

        context = build_confluence_context(pages, budget=12000)
        user = f"# Confluence Documentation ({len(pages)} pages)\n\n{context}"
        return self._llm_call("Phase 2", _CONFLUENCE_MINING_SYSTEM, user, fallback="# Confluence Rules\n(unavailable)")

    def _mine_jira(self, jira_project: str) -> str:
        """Phase 3 — extract failure patterns from Jira bug/incident tickets."""
        logger.info("Phase 3: mining Jira project=%s", jira_project or "(none)")

        if not jira_project:
            return "# Jira Patterns\n(No Jira project key provided — pass --jira-project)"

        # Build a temporary JiraClient from settings
        if not (settings.jira_url and settings.jira_username and settings.jira_api_token):
            return "# Jira Patterns\n(Jira not configured — set JIRA_URL, JIRA_USERNAME, JIRA_API_TOKEN)"

        try:
            from src.jira_service import JiraClient
            client = JiraClient(
                url=settings.jira_url,
                username=settings.jira_username,
                api_token=settings.jira_api_token,
            )
            if not client.is_connected() or not client._raw:
                return "# Jira Patterns\n(Jira connection failed)"

            jql = (
                f'project = "{jira_project}" '
                f'AND issuetype in (Bug, Incident) '
                f'AND status in (Done, Resolved, Closed) '
                f'ORDER BY updated DESC'
            )
            issues = client._raw.search_issues(jql, maxResults=30)
        except Exception as exc:
            logger.warning("Phase 3: Jira search failed: %s", exc)
            return f"# Jira Patterns\n(Search failed: {exc})"

        if not issues:
            return f"# Jira Patterns\n(No bug/incident tickets found in project {jira_project!r})"

        parts: list[str] = []
        for issue in issues:
            f = issue.fields
            summary = getattr(f, "summary", "") or ""
            desc = getattr(f, "description", "") or ""
            desc = re.sub(r"<[^>]+>", " ", str(desc))
            desc = re.sub(r"\s+", " ", desc).strip()[:400]
            parts.append(f"**{issue.key}**: {summary}\n{desc}")

        user = (
            f"# Jira Bug/Incident Tickets — {jira_project} ({len(parts)} tickets)\n\n"
            + "\n\n---\n".join(parts)
        )
        return self._llm_call("Phase 3", _JIRA_MINING_SYSTEM, user, fallback="# Jira Patterns\n(unavailable)")

    def _normalize(self, repo_md: str, confluence_md: str, jira_md: str) -> str:
        """Phase 4 — normalize all sources into a unified domain model."""
        logger.info("Phase 4: normalizing domain model")
        user = (
            f"# Phase 1 — Repo Structure\n{repo_md[:4000]}\n\n"
            f"---\n\n# Phase 2 — Confluence Rules\n{confluence_md[:4000]}\n\n"
            f"---\n\n# Phase 3 — Jira Failure Patterns\n{jira_md[:4000]}"
        )
        return self._llm_call("Phase 4", _NORMALIZE_SYSTEM, user, fallback="# Normalized Domain\n(unavailable)")

    def _generate_context(self, normalized: str) -> str:
        """Phase 5 — generate the final domain_context.md."""
        logger.info("Phase 5: generating domain context")
        user = f"# Normalized Domain Model\n\n{normalized[:6000]}"
        return self._llm_call("Phase 5", _CONTEXT_GEN_SYSTEM, user, fallback="# DOMAIN CONTEXT\n(unavailable)")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _llm_call(self, phase: str, system: str, user: str, fallback: str) -> str:
        from src.ai_reporter import _call_llm

        try:
            result = _call_llm([
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ])
            return result or fallback
        except Exception as exc:
            logger.warning("%s LLM call failed: %s", phase, exc)
            return f"{fallback}\n(Error: {exc})"


# ---------------------------------------------------------------------------
# Loader — used by PR analyzer to inject domain context
# ---------------------------------------------------------------------------

def load_domain_context(path: Optional[Path | str] = None) -> str:
    """Return the contents of domain_context.md, or '' if missing.

    Relative paths are tried in order:
    1. ``<project_root>/<path>`` (directory containing ``src/``, i.e. this repo)
    2. ``<current working directory>/<path>``

    So ``analyze_change`` finds ``domain_context.md`` even when run from ``~`` or another folder,
    as long as the file lives next to ``src/``.
    """
    p = Path(path) if path is not None else _FINAL_OUTPUT
    candidates: list[Path]
    if p.is_absolute():
        candidates = [p]
    else:
        candidates = [_PROJECT_ROOT / p, Path.cwd() / p]
    for c in candidates:
        try:
            if c.is_file():
                return c.read_text(encoding="utf-8")
        except OSError as e:
            logger.debug("Could not read domain context %s: %s", c, e)
    return ""
