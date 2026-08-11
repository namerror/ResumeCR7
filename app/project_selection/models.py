from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from app.job_focus_generation.models import JobFocus
from app.resume_evidence.models import ProjectSkills


class StrictSchemaModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ProjectJobContext(StrictSchemaModel):
    title: str
    description: str | None = None
    job_focus: JobFocus | None = None


class ProjectCandidate(StrictSchemaModel):
    id: str
    name: str
    summary: str
    skills: ProjectSkills


class RankedProject(StrictSchemaModel):
    project_id: str
    score: float
    method: Literal["baseline", "llm"]


class ProjectSelectionResult(StrictSchemaModel):
    selected_project_ids: list[str] # ids of selected projects, also ranked by relevance
    ranked_projects: list[RankedProject]
    details: dict[str, Any] | None = None


class ProjectOutputTokenBudget(StrictSchemaModel):
    base: int = 900
    per_candidate: int = 40
    per_prompt_1k_chars: int = 40
    min: int = 1200
    max: int | None = None

    @field_validator("base", "per_candidate", "per_prompt_1k_chars", "min")
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
    def validate_range(self) -> "ProjectOutputTokenBudget":
        if self.max is not None and self.max < self.min:
            raise ValueError("output token budget max must be greater than or equal to min")
        return self


class ProjectSelectRequest(StrictSchemaModel):
    context: ProjectJobContext
    candidates: list[ProjectCandidate]
    method: Literal["baseline", "llm"] | None = None
    top_n: int | None = None
    dev_mode: bool | None = None
    llm_model: str | None = None
    llm_max_output_tokens: int | None = None
    llm_output_token_budget: ProjectOutputTokenBudget | None = None
