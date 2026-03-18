"""Domain Knowledge Pipeline — mines repo, Confluence, and Jira to produce domain_context.md.

Phases (1–3 run in parallel, 4–5 run sequentially):
  1. Repo Mining      — extract module structure + critical patterns from GitHub repo tree
  2. Confluence Mining— extract domain rules from wiki pages
  3. Jira Mining      — extract failure patterns from bug/incident tickets
  4. Normalization    — unify the three sources into a coherent domain model
  5. Context Generation — produce domain_context.md for injection into the PR analyzer

Usage:
  from src.domain_knowledge_pipeline import DomainKnowledgePipeline, load_domain_context

  pipeline = DomainKnowledgePipeline()
  output_path = pipeline.build(
      repo="org/repo",
      jira_project="PROJ",
      confluence_queries=["signoff", "checklist", "authorization"],
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
        self._confluence = confluence_service or ConfluenceService(
            base_url=settings.confluence_base_url,
            token=settings.confluence_token,
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
        force_refresh: bool = False,
    ) -> Path:
        """Run the full pipeline and return the path to ``domain_context.md``.

        Args:
            repo: GitHub repo in ``org/name`` format.
            jira_project: Jira project key (e.g. ``CLOSE``). Used to fetch
                bug/incident tickets for Phase 3.
            confluence_queries: List of domain keywords for Confluence search
                (e.g. ``["signoff", "checklist", "authorization"]``).
            force_refresh: When True, re-run all phases even if cached files exist.

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

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            f1 = executor.submit(_cached, "repo_analysis.md", lambda: self._mine_repo(repo))
            f2 = executor.submit(_cached, "confluence_rules.md", lambda: self._mine_confluence(confluence_queries or []))
            f3 = executor.submit(_cached, "jira_patterns.md", lambda: self._mine_jira(jira_project))
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
        self._final_output.write_text(domain_context, encoding="utf-8")
        logger.info("Domain context written to %s", self._final_output)

        return self._final_output

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

def load_domain_context(path: Optional[Path] = None) -> str:
    """Return the contents of domain_context.md, or '' if the file does not exist."""
    p = path or _FINAL_OUTPUT
    try:
        return p.read_text(encoding="utf-8") if p.exists() else ""
    except Exception:
        return ""
