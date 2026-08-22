from __future__ import annotations

import yaml

from app import llm_provider
from app.config import QWEN_DEFAULT_BASE_URL


def test_qwen_defaults_cover_all_llm_stages():
    assert llm_provider.QWEN_DEFAULT_MODELS == {
        "skill_selection": "qwen3.7-flash",
        "project_selection": "qwen3.7-flash",
        "job_focus_generation": "qwen3.7-plus",
        "bulletpoints_generation": "qwen3.7-plus",
        "link_scanning": "qwen3.7-plus",
    }


def test_resolve_llm_cache_identity_tracks_provider_model_and_base_url(
    monkeypatch,
    tmp_path,
):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("QWEN_BASE_URL", raising=False)
    monkeypatch.setattr(llm_provider.settings, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(llm_provider.settings, "QWEN_BASE_URL", QWEN_DEFAULT_BASE_URL)

    openai_config = tmp_path / "openai.yaml"
    openai_config.write_text(
        yaml.safe_dump({"schema_version": 1, "llm_provider": "openai"}),
        encoding="utf-8",
    )
    qwen_config = tmp_path / "qwen.yaml"
    qwen_config.write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "llm_provider": "qwen",
                "qwen": {"base_url": "https://qwen.example/compatible-mode/v1"},
            }
        ),
        encoding="utf-8",
    )

    openai_identity = llm_provider.resolve_llm_cache_identity(
        stage="skill_selection",
        requested_model="gpt-5-nano",
        default_openai_model="gpt-5-nano",
        config_path=openai_config,
    )
    qwen_identity = llm_provider.resolve_llm_cache_identity(
        stage="skill_selection",
        requested_model="gpt-5-nano",
        default_openai_model="gpt-5-nano",
        config_path=qwen_config,
    )

    assert openai_identity == {"provider": "openai", "model": "gpt-5-nano"}
    assert qwen_identity == {
        "provider": "qwen",
        "model": "qwen3.7-flash",
        "base_url": "https://qwen.example/compatible-mode/v1",
    }
    assert openai_identity != qwen_identity


def test_apply_qwen_response_options_uses_reasoning_effort_none():
    kwargs = {}
    llm_provider.apply_provider_response_options(
        kwargs,
        llm_provider.ResolvedLLMProvider(
            provider="qwen",
            api_key="test-key",
            model="qwen3.7-plus",
            base_url=QWEN_DEFAULT_BASE_URL,
        ),
    )

    assert kwargs == {"reasoning": {"effort": "none"}}
