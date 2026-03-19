from __future__ import annotations

import os

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # full = todas las capas | demo = MCP/light — ver docs/DEMO-MCP-GUIDE.md
    analyzer_profile: str = Field(
        default="full",
        validation_alias=AliasChoices("PR_ANALYZER_PROFILE", "ANALYZER_PROFILE"),
    )

    github_token: str = ""
    jira_url: str = ""
    jira_username: str = ""
    jira_api_token: str = ""
    local_repo_path: str = ""
    anthropic_api_key: str = ""

    # AI reporter — OpenAI (direct) / OpenRouter / Anthropic / Ollama (first available).
    # AI runs when ai_enabled=True OR any of openai_api_key, openrouter_api_key is set.
    ai_enabled: bool = False
    ai_model: str = "llama3.1"                          # Ollama model name
    openai_api_key: str = ""                            # direct OpenAI API; use with openai_model e.g. gpt-4o-mini
    openai_model: str = "gpt-4o-mini"                  # cheap, fast; good rate limits
    openrouter_api_key: str = ""                         # set this to enable report/coverage/quality via OpenRouter
    openrouter_model: str = "google/gemma-3-27b-it:free"  # free model; auto-falls back if rate-limited
    openrouter_delay_seconds: float = 5.0                # delay before/after each OpenRouter call (sequential spacing)
    openrouter_batch_delay_seconds: float = 12.0         # extra delay between PRs in batch (strictly sequential)
    openrouter_429_backoff_seconds: float = 60.0         # when 429: wait this long before one retry (no quick retries)
    openrouter_light_mode: bool = False                 # if True: 1 LLM call/PR (coverage only); skip report + quality score to avoid 429

    # External coverage providers (optional)
    codecov_token: str = ""
    sonar_token: str = ""
    sonar_url: str = "https://sonarcloud.io"
    sonar_project_key: str = ""  # defaults to org_repo if empty

    # Optional: require API key for remote MCP SSE (set MCP_AUTH_SECRET; clients use Authorization: Bearer <secret> or X-API-Key: <secret>)
    mcp_auth_secret: str = ""

    # Confluence integration (optional — feature disabled when absent)
    confluence_base_url: str = ""   # e.g. https://yourcompany.atlassian.net/wiki
    confluence_token: str = ""      # Atlassian personal access token

    # Comma-separated path substrings → "legacy surface" in PR reports (case-insensitive)
    legacy_path_segments: str = (
        "legacy,deprecated,/v1/,v0/,old-client,__legacy__,/archive/"
    )

    # Second LLM call: workflow analysis from Jira (ticket+epic), Confluence, repo README/docs + diff
    contextual_workflow_analysis_enabled: bool = True

    # Injected into PR heuristics + workflow LLM; relative paths resolve vs project root (parent of src/) then cwd
    domain_context_path: str = "domain_context.md"
    domain_knowledge_dir: str = "domain_knowledge"

    # Repo-wide signals (MVP): pre-scan with ``scan_repo_signals`` → JSON; PR report section (off by default — large JSON, secondary to ticket/production review)
    repo_signals_json_path: str = ""  # if set, load this file instead of only <repo_path>/artifacts/repo_signals.json
    repo_behavior_report_enabled: bool = False

    # DomainKnowledgePipeline.build() defaults when args omitted (optional)
    domain_build_repo_path: str = ""  # local clone to scan for §10 appendix
    domain_build_repo_signals_json: str = ""  # or use precomputed JSON path for §10

    # Risk: each hard domain signal (from domain_context §2/§5/§6) adds up to this many points
    domain_hard_signal_points: int = 2
    domain_hard_signal_points_cap: int = 8
    # If any hard heuristic marks invariant_violation, floor risk at HIGH
    domain_force_high_on_hard_invariant: bool = True

    # Behavior Verifier: keep hard invariant/failure signals only when diff shows behavior change (guard removed / bypass)
    domain_verify_behavior_before_hard: bool = True

    # Evidence resolution: after workflow LLM + DOMAIN_STRUCT merge, dismiss false-positive hard heuristics when DOMAIN_STRUCT says NONE
    domain_evidence_validation_enabled: bool = True
    # When True, dismiss hard invariant heuristics that contradict an empty/NONE VIOLATED_INVARIANTS block
    domain_evidence_dismiss_on_llm_no_violations: bool = True
    # Optional: if workflow narrative matches "safe" phrases, strengthen dismissal (extra false-positive risk)
    domain_evidence_narrative_dismissal: bool = False
    # Points weight for uncertain signals (future use; 0.5 = half contribution)
    domain_evidence_uncertain_weight: float = 0.5

    @model_validator(mode="after")
    def _apply_demo_profile(self) -> "Settings":
        """When PR_ANALYZER_PROFILE=demo, lighten defaults for MCP demos unless env explicitly sets a key."""
        if (self.analyzer_profile or "").strip().lower() != "demo":
            return self

        # Field name -> proposed value (only applied if no env var override)
        demo_env = {
            "OPENROUTER_LIGHT_MODE": ("openrouter_light_mode", True),
            "CONTEXTUAL_WORKFLOW_ANALYSIS_ENABLED": ("contextual_workflow_analysis_enabled", False),
            "DOMAIN_EVIDENCE_VALIDATION_ENABLED": ("domain_evidence_validation_enabled", False),
            "REPO_BEHAVIOR_REPORT_ENABLED": ("repo_behavior_report_enabled", False),
        }
        for env_key, (attr, value) in demo_env.items():
            if env_key not in os.environ:
                object.__setattr__(self, attr, value)

        # Snappier demo if not overridden
        if "OPENROUTER_DELAY_SECONDS" not in os.environ:
            object.__setattr__(self, "openrouter_delay_seconds", min(self.openrouter_delay_seconds, 2.0))

        return self


settings = Settings()
