"""PR_ANALYZER_PROFILE=demo applies light defaults when env keys are unset."""

from __future__ import annotations

import importlib
import sys

import pytest

pytest.importorskip("pydantic_settings")


def test_demo_profile_sets_light_defaults(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("# empty — env only\n", encoding="utf-8")
    monkeypatch.setenv("PR_ANALYZER_PROFILE", "demo")
    for key in (
        "OPENROUTER_LIGHT_MODE",
        "CONTEXTUAL_WORKFLOW_ANALYSIS_ENABLED",
        "DOMAIN_EVIDENCE_VALIDATION_ENABLED",
        "REPO_BEHAVIOR_REPORT_ENABLED",
        "OPENROUTER_DELAY_SECONDS",
    ):
        monkeypatch.delenv(key, raising=False)

    if "src.config" in sys.modules:
        importlib.reload(sys.modules["src.config"])
    else:
        import src.config  # noqa: F401

    from src import config as cfg

    assert cfg.settings.analyzer_profile.lower() == "demo"
    assert cfg.settings.openrouter_light_mode is True
    assert cfg.settings.contextual_workflow_analysis_enabled is False
    assert cfg.settings.domain_evidence_validation_enabled is False
    assert cfg.settings.repo_behavior_report_enabled is False
    assert cfg.settings.openrouter_delay_seconds <= 2.0


def test_demo_profile_respects_explicit_openrouter_light_off(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("# empty\n", encoding="utf-8")
    monkeypatch.setenv("PR_ANALYZER_PROFILE", "demo")
    monkeypatch.setenv("OPENROUTER_LIGHT_MODE", "false")
    for key in (
        "CONTEXTUAL_WORKFLOW_ANALYSIS_ENABLED",
        "DOMAIN_EVIDENCE_VALIDATION_ENABLED",
        "REPO_BEHAVIOR_REPORT_ENABLED",
        "OPENROUTER_DELAY_SECONDS",
    ):
        monkeypatch.delenv(key, raising=False)

    importlib.reload(sys.modules["src.config"])
    from src import config as cfg

    assert cfg.settings.openrouter_light_mode is False
