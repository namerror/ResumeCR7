from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from app.job_focus_generation.models import JobFocus
from app.resume_evidence.models import ExperienceRecord, ProjectRecord


class StrictSchemaModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class BulletJobContext(StrictSchemaModel):
    title: str
    description: str | None = None
    job_focus: JobFocus | None = None

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("title must not be empty")
        return normalized

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip()


class BulletCountRange(StrictSchemaModel):
    min: int
    max: int

    @model_validator(mode="after")
    def validate_range(self) -> "BulletCountRange":
        if self.min < 1:
            raise ValueError("bullet_count_range.min must be greater than or equal to 1")
        if self.max > 10:
            raise ValueError("bullet_count_range.max must be less than or equal to 10")
        if self.min > self.max:
            raise ValueError("bullet_count_range.min must be less than or equal to max")
        return self


class BulletOutputTokenBudget(StrictSchemaModel):
    base: int = 900
    per_bullet: int = 550
    per_highlight: int = 35
    per_evidence_1k_chars: int = 80
    min: int = 1800
    max: int | None = None

    @field_validator(
        "base",
        "per_bullet",
        "per_highlight",
        "per_evidence_1k_chars",
        "min",
    )
    @classmethod
    def validate_non_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("output token budget values must be greater than or equal to 0")
        return value

    @field_validator("max")
    @classmethod
    def validate_optional_max(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            raise ValueError("output token budget max must be greater than 0")
        return value

    @model_validator(mode="after")
    def validate_range(self) -> "BulletOutputTokenBudget":
        if self.max is not None and self.max < self.min:
            raise ValueError("output token budget max must be greater than or equal to min")
        return self


class BulletGenerationRequest(StrictSchemaModel):
    context: BulletJobContext
    project: ProjectRecord | None = None
    experience: ExperienceRecord | None = None
    bullet_count_range: BulletCountRange | None = None
    dev_mode: bool | None = None
    llm_model: str | None = None
    llm_max_output_tokens: int | None = None
    llm_output_token_budget: BulletOutputTokenBudget | None = None

    @model_validator(mode="after")
    def validate_single_evidence_record(self) -> "BulletGenerationRequest":
        evidence_count = int(self.project is not None) + int(self.experience is not None)
        if evidence_count != 1:
            raise ValueError("Exactly one of project or experience must be provided")
        return self

    @property
    def evidence_type(self) -> Literal["project", "experience"]:
        return "project" if self.project is not None else "experience"

    @property
    def evidence_id(self) -> str:
        if self.project is not None:
            return self.project.id
        if self.experience is not None:
            return self.experience.id
        raise ValueError("Exactly one of project or experience must be provided")

    @field_validator("llm_model")
    @classmethod
    def validate_llm_model(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("llm_model must not be empty")
        return normalized

    @field_validator("llm_max_output_tokens")
    @classmethod
    def validate_llm_max_output_tokens(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            raise ValueError("llm_max_output_tokens must be greater than 0")
        return value


class BulletGenerationResponse(StrictSchemaModel):
    bullet_points: list[str]
    details: dict[str, Any] | None = None
