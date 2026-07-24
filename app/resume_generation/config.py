from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from app.config import settings
from app.resume_generation.models import JobTarget, ResumeGenerationConfig


DEFAULT_GENERATION_CONFIG_PATH = settings.generation_config_path
DEFAULT_JOB_TARGET_PATH = settings.job_target_path


def resolve_generation_config_path(path: Path | str | None = None) -> Path:
    return Path(path) if path is not None else settings.generation_config_path


def resolve_job_target_path(path: Path | str | None = None) -> Path:
    return Path(path) if path is not None else settings.job_target_path


def _load_yaml_mapping(path: Path | str) -> dict[str, Any]:
    yaml_path = Path(path)
    with yaml_path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)

    if not isinstance(data, dict):
        raise ValueError(f"Expected YAML mapping in {yaml_path}")
    return data


def load_generation_config(path: Path | str | None = None) -> ResumeGenerationConfig:
    return ResumeGenerationConfig.model_validate(_load_yaml_mapping(resolve_generation_config_path(path)))


def load_job_target(path: Path | str | None = None) -> JobTarget:
    return JobTarget.model_validate(_load_yaml_mapping(resolve_job_target_path(path)))
