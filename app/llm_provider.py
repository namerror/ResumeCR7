from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml

from app.config import (
    get_openai_api_key,
    get_qwen_api_key,
    get_qwen_base_url,
    settings,
)


LLMProvider = Literal["openai", "qwen"]
LLMStage = Literal[
    "skill_selection",
    "project_selection",
    "job_focus_generation",
    "bulletpoints_generation",
    "link_scanning",
]

QWEN_DEFAULT_MODELS: dict[LLMStage, str] = {
    "skill_selection": "qwen3.6-flash",
    "project_selection": "qwen3.6-flash",
    "job_focus_generation": "qwen3.7-plus",
    "bulletpoints_generation": "qwen3.7-plus",
    "link_scanning": "qwen3.7-plus",
}

OPENAI_DEFAULT_MODELS = {
    "gpt-5-nano",
    "gpt-5-mini",
    "gpt-5.6-terra",
}


@dataclass(frozen=True)
class ResolvedLLMProvider:
    provider: LLMProvider
    api_key: str
    model: str
    base_url: str | None = None

    @property
    def api_key_setting_name(self) -> str:
        if self.provider == "qwen":
            return "QWEN_API_KEY or DASHSCOPE_API_KEY"
        return "OPENAI_API_KEY"

    def client_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {"api_key": self.api_key}
        if self.base_url is not None:
            kwargs["base_url"] = self.base_url
        return kwargs

    def metadata(self) -> dict[str, Any]:
        metadata: dict[str, Any] = {"provider": self.provider, "model": self.model}
        if self.base_url is not None:
            metadata["base_url"] = self.base_url
        return metadata


def resolve_llm_provider_config(
    *,
    stage: LLMStage,
    requested_model: str | None,
    default_openai_model: str,
    config_path: Path | str | None = None,
) -> ResolvedLLMProvider:
    provider = resolve_llm_provider(config_path=config_path)
    if provider == "qwen":
        model = _resolve_qwen_model(stage=stage, requested_model=requested_model)
        return ResolvedLLMProvider(
            provider="qwen",
            api_key=get_qwen_api_key(config_path=config_path),
            model=model,
            base_url=get_qwen_base_url(config_path=config_path),
        )

    return ResolvedLLMProvider(
        provider="openai",
        api_key=get_openai_api_key(config_path=config_path),
        model=requested_model if requested_model is not None else default_openai_model,
    )


def resolve_llm_provider(config_path: Path | str | None = None) -> LLMProvider:
    if "LLM_PROVIDER" in os.environ or settings.LLM_PROVIDER != "openai":
        return _normalize_provider(settings.LLM_PROVIDER)

    raw_provider = _load_llm_provider_from_generation_config(
        Path(config_path) if config_path is not None else settings.generation_config_path
    )
    if raw_provider is not None:
        return raw_provider
    return _normalize_provider(settings.LLM_PROVIDER)


def apply_provider_response_options(
    kwargs: dict[str, Any],
    provider_config: ResolvedLLMProvider,
) -> None:
    if provider_config.provider == "qwen":
        extra_body = kwargs.setdefault("extra_body", {})
        if isinstance(extra_body, dict):
            extra_body.setdefault("enable_thinking", False)


def _resolve_qwen_model(*, stage: LLMStage, requested_model: str | None) -> str:
    if requested_model is None or requested_model in OPENAI_DEFAULT_MODELS:
        return QWEN_DEFAULT_MODELS[stage]
    return requested_model


def _load_llm_provider_from_generation_config(config_path: Path) -> LLMProvider | None:
    if not config_path.exists():
        return None

    with config_path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle)

    if not isinstance(payload, dict):
        return None

    raw_provider = payload.get("llm_provider")
    if raw_provider is None:
        return None
    return _normalize_provider(raw_provider)


def _normalize_provider(value: object) -> LLMProvider:
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"openai", "qwen"}:
            return normalized  # type: ignore[return-value]
    raise ValueError("llm_provider must be either 'openai' or 'qwen'")
