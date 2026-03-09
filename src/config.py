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

    # AI reporter — OpenRouter (preferred) or Ollama (local fallback).
    # AI runs when ai_enabled=True OR openrouter_api_key is set (no need for both).
    ai_enabled: bool = False
    ai_model: str = "llama3.1"                          # Ollama model name
    openrouter_api_key: str = ""                         # set this to enable report/coverage/quality via OpenRouter
    openrouter_model: str = "google/gemma-3-27b-it:free"  # free model; auto-falls back if rate-limited
    openrouter_delay_seconds: float = 2.0                # delay between requests to avoid 429 (batch runs)

    # External coverage providers (optional)
    codecov_token: str = ""
    sonar_token: str = ""
    sonar_url: str = "https://sonarcloud.io"
    sonar_project_key: str = ""  # defaults to org_repo if empty


settings = Settings()
