from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

import yaml

from app.resume_evidence.models import (
    EducationFile,
    ExperienceFile,
    ProjectsFile,
    SkillsFile,
    UserInfoFile,
)
from app.resume_generation.config import (
    default_generation_config_payload,
    ensure_generation_config_defaults,
    load_job_target,
)
from app.resume_generation.models import JobTarget, ResumeGenerationConfig


EVIDENCE_SCHEMA_REGISTRY = {
    "education": EducationFile,
    "experience": ExperienceFile,
    "projects": ProjectsFile,
    "skills": SkillsFile,
    "user": UserInfoFile,
}


def bootstrap_runtime_data(
    *,
    data_dir: Path,
    evidence_root: Path,
    generation_root: Path,
    artifacts_root: Path,
    log_dir: Path,
) -> None:
    for directory in (
        data_dir,
        evidence_root,
        generation_root,
        artifacts_root,
        log_dir,
    ):
        directory.mkdir(parents=True, exist_ok=True)

    for schema_name, path in _default_evidence_paths(evidence_root).items():
        _write_default_yaml_if_missing(
            path,
            _default_evidence_payload(schema_name),
            validator=lambda payload, schema_name=schema_name: EVIDENCE_SCHEMA_REGISTRY[
                schema_name
            ].model_validate(payload),
        )

    _write_default_yaml_if_missing(
        generation_root / "config.yaml",
        default_generation_config_payload(),
        validator=ResumeGenerationConfig.model_validate,
    )
    _write_default_yaml_if_missing(
        generation_root / "job_target.yaml",
        {
            "schema_version": 1,
            "title": "Target Job Title",
            "description": None,
        },
        validator=JobTarget.model_validate,
    )

    ensure_generation_config_defaults(generation_root / "config.yaml")
    load_job_target(generation_root / "job_target.yaml")


def _default_evidence_payload(schema_name: str) -> dict[str, Any]:
    if schema_name == "education":
        return {"schema_version": 1, "education": []}
    if schema_name == "experience":
        return {"schema_version": 1, "experience": []}
    if schema_name == "projects":
        return {"schema_version": 1, "projects": []}
    if schema_name == "skills":
        return {
            "schema_version": 1,
            "skills": {
                "technology": [],
                "programming": [],
                "concepts": [],
            },
        }
    if schema_name == "user":
        return {
            "schema_version": 1,
            "name": "Your Name",
            "email": "you@example.com",
            "phone": "Your Phone",
        }

    supported_schemas = ", ".join(sorted(EVIDENCE_SCHEMA_REGISTRY))
    raise ValueError(
        f"Unsupported evidence schema '{schema_name}'. Supported schemas: {supported_schemas}"
    )


def _default_evidence_paths(evidence_root: Path) -> dict[str, Path]:
    return {
        "education": evidence_root / "education.yaml",
        "experience": evidence_root / "experience.yaml",
        "projects": evidence_root / "projects.yaml",
        "skills": evidence_root / "skills.yaml",
        "user": evidence_root / "user.yaml",
    }


def _write_default_yaml_if_missing(
    path: Path,
    payload: dict[str, Any],
    *,
    validator: Any,
) -> None:
    if path.exists():
        return

    validator(payload)
    _write_yaml_atomic(path, payload)


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

        os.replace(temp_file_path, path)
    finally:
        if temp_file_path is not None and os.path.exists(temp_file_path):
            os.unlink(temp_file_path)
