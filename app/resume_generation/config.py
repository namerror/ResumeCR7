from __future__ import annotations

import os
import tempfile
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


def default_generation_config_payload() -> dict[str, Any]:
    return ResumeGenerationConfig(schema_version=1).model_dump(mode="python")


def merge_generation_config_defaults(payload: dict[str, Any]) -> dict[str, Any]:
    return _deep_fill_missing(payload, default_generation_config_payload())


def load_generation_config_payload(
    path: Path | str | None = None,
    *,
    fill_defaults: bool = False,
) -> dict[str, Any]:
    payload = _load_yaml_mapping(resolve_generation_config_path(path))
    if fill_defaults:
        payload = merge_generation_config_defaults(payload)
    ResumeGenerationConfig.model_validate(payload)
    return payload


def load_generation_config(path: Path | str | None = None) -> ResumeGenerationConfig:
    return ResumeGenerationConfig.model_validate(
        _load_yaml_mapping(resolve_generation_config_path(path))
    )


def load_job_target(path: Path | str | None = None) -> JobTarget:
    return JobTarget.model_validate(_load_yaml_mapping(resolve_job_target_path(path)))


def write_job_target_payload(
    payload: dict[str, Any],
    path: Path | str | None = None,
) -> JobTarget:
    resolved_path = resolve_job_target_path(path)
    validated = JobTarget.model_validate(payload)
    _write_yaml_atomic(resolved_path, validated.model_dump(mode="python"))
    return validated


def ensure_generation_config_defaults(path: Path | str | None = None) -> ResumeGenerationConfig:
    resolved_path = resolve_generation_config_path(path)
    if resolved_path.exists():
        payload = _load_yaml_mapping(resolved_path)
    else:
        payload = {"schema_version": 1}

    merged_payload = merge_generation_config_defaults(payload)
    validated = ResumeGenerationConfig.model_validate(merged_payload)
    if payload != merged_payload or not resolved_path.exists():
        write_generation_config_payload(merged_payload, resolved_path)
    return validated


def write_generation_config_payload(
    payload: dict[str, Any],
    path: Path | str | None = None,
) -> ResumeGenerationConfig:
    resolved_path = resolve_generation_config_path(path)
    validated = ResumeGenerationConfig.model_validate(payload)
    _write_yaml_atomic(resolved_path, validated.model_dump(mode="python"))
    return validated


def _deep_fill_missing(payload: dict[str, Any], defaults: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for key, default_value in defaults.items():
        if key not in payload:
            merged[key] = _copy_yaml_value(default_value)
            continue
        current_value = payload[key]
        if isinstance(current_value, dict) and isinstance(default_value, dict):
            merged[key] = _deep_fill_missing(current_value, default_value)
        else:
            merged[key] = _copy_yaml_value(current_value)

    for key, current_value in payload.items():
        if key not in defaults:
            merged[key] = _copy_yaml_value(current_value)

    return merged


def _copy_yaml_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _copy_yaml_value(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_copy_yaml_value(child) for child in value]
    return value


def _write_yaml_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_file_path: str | None = None

    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            yaml.safe_dump(payload, handle, sort_keys=False)
            temp_file_path = handle.name

        if temp_file_path is None:
            raise RuntimeError(f"Failed to create temporary file for {path}")

        os.replace(temp_file_path, path)
    finally:
        if temp_file_path is not None and os.path.exists(temp_file_path):
            os.unlink(temp_file_path)
