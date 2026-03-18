from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

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

    # Domain knowledge pipeline output — injected into system prompt when present
    domain_context_path: str = "domain_context.md"
    domain_knowledge_dir: str = "domain_knowledge"


settings = Settings()
