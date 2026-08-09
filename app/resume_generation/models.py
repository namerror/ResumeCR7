from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.config import settings
from app.job_focus_generation.models import JobFocus as JobFocusResult
from app.resume_evidence.models import ProjectRecord


class StrictSchemaModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class GenerationAppConfig(StrictSchemaModel):
    base_url: str = "http://127.0.0.1:8000"
    timeout_seconds: float = 600.0

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        normalized = value.strip().rstrip("/")
        if not normalized:
            raise ValueError("base_url must not be empty")
        return normalized

    @field_validator("timeout_seconds")
    @classmethod
    def validate_timeout(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("timeout_seconds must be greater than 0")
        return value


class SkillSelectionConfig(StrictSchemaModel):
    method: Literal["baseline", "embeddings", "llm"] | None = "llm"
    top_n: int | None = 20
    baseline_filter: bool | None = False
    dev_mode: bool | None = True
    llm_model: str | None = "gpt-5-nano"
    llm_max_output_tokens: int | None = None

    @field_validator("top_n")
    @classmethod
    def validate_top_n(cls, value: int | None) -> int | None:
        if value is not None and value < 0:
            raise ValueError("top_n must be greater than or equal to 0")
        return value

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


class ProjectOutputTokenBudgetConfig(StrictSchemaModel):
    base: int = 900
    per_candidate: int = 40
    per_prompt_1k_chars: int = 40
    min: int = 1200
    max: int | None = None

    @field_validator("base", "per_candidate", "per_prompt_1k_chars", "min")
    @classmethod
    def validate_non_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("llm_output_token_budget values must be greater than or equal to 0")
        return value

    @field_validator("max")
    @classmethod
    def validate_optional_max(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            raise ValueError("llm_output_token_budget.max must be greater than 0")
        return value

    @model_validator(mode="after")
    def validate_range(self) -> "ProjectOutputTokenBudgetConfig":
        if self.max is not None and self.max < self.min:
            raise ValueError("llm_output_token_budget.max must be greater than or equal to min")
        return self


class ProjectSelectionConfig(StrictSchemaModel):
    method: Literal["baseline", "llm"] | None = "llm"
    top_n: int | None = None
    dev_mode: bool | None = True
    llm_model: str | None = "gpt-5-nano"
    llm_max_output_tokens: int | None = None
    llm_output_token_budget: ProjectOutputTokenBudgetConfig | None = None

    @field_validator("top_n")
    @classmethod
    def validate_top_n(cls, value: int | None) -> int | None:
        if value is not None and value < 0:
            raise ValueError("top_n must be greater than or equal to 0")
        return value

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


class ExperienceSelectionConfig(StrictSchemaModel):
    top_n: int | None = None

    @field_validator("top_n")
    @classmethod
    def validate_top_n(cls, value: int | None) -> int | None:
        if value is not None and value < 0:
            raise ValueError("top_n must be greater than or equal to 0")
        return value


class BulletOutputTokenBudgetConfig(StrictSchemaModel):
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
            raise ValueError("llm_output_token_budget values must be greater than or equal to 0")
        return value

    @field_validator("max")
    @classmethod
    def validate_optional_max(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            raise ValueError("llm_output_token_budget.max must be greater than 0")
        return value

    @model_validator(mode="after")
    def validate_range(self) -> "BulletOutputTokenBudgetConfig":
        if self.max is not None and self.max < self.min:
            raise ValueError("llm_output_token_budget.max must be greater than or equal to min")
        return self


class BulletCountRangeConfig(StrictSchemaModel):
    min: int
    max: int

    @field_validator("min")
    @classmethod
    def validate_min(cls, value: int) -> int:
        if value < 1:
            raise ValueError("bullet_count_range.min must be greater than or equal to 1")
        return value

    @field_validator("max")
    @classmethod
    def validate_max(cls, value: int) -> int:
        if value > 10:
            raise ValueError("bullet_count_range.max must be less than or equal to 10")
        return value

    @model_validator(mode="after")
    def validate_range(self) -> "BulletCountRangeConfig":
        if self.min > self.max:
            raise ValueError("bullet_count_range.min must be less than or equal to max")
        return self


class BulletPointGenerationConfig(StrictSchemaModel):
    bullet_count_range: BulletCountRangeConfig | None = None
    dev_mode: bool | None = True
    llm_model: str | None = "gpt-5-mini"
    llm_max_output_tokens: int | None = None
    llm_output_token_budget: BulletOutputTokenBudgetConfig | None = Field(
        default_factory=BulletOutputTokenBudgetConfig
    )

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


class JobFocusGenerationConfig(StrictSchemaModel):
    dev_mode: bool | None = True
    llm_model: str | None = "gpt-5-mini"
    llm_max_output_tokens: int | None = 1200

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


class LinkScanningConfig(StrictSchemaModel):
    enabled: bool = False
    dev_mode: bool | None = True
    llm_model: str | None = "gpt-5.6-terra"
    llm_max_output_tokens: int | None = None
    highlight_count: int | None = 6
    max_tokens_per_highlight: int | None = 500

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

    @field_validator("highlight_count")
    @classmethod
    def validate_highlight_count(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            raise ValueError("highlight_count must be greater than 0")
        return value

    @field_validator("max_tokens_per_highlight")
    @classmethod
    def validate_max_tokens_per_highlight(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            raise ValueError("max_tokens_per_highlight must be greater than 0")
        return value


class ResumeGenerationCacheConfig(StrictSchemaModel):
    enabled: bool = True
    path: str | None = None
    force_refresh: bool = False

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("cache.path must not be empty when provided")
        return normalized


class ResumeGenerationConcurrencyConfig(StrictSchemaModel):
    bullet_point_requests: int = 3

    @field_validator("bullet_point_requests")
    @classmethod
    def validate_bullet_point_requests(cls, value: int) -> int:
        if value < 1:
            raise ValueError("concurrency.bullet_point_requests must be greater than or equal to 1")
        if value > 10:
            raise ValueError("concurrency.bullet_point_requests must be less than or equal to 10")
        return value


def _default_resume_output_dir() -> str:
    return str(settings.resume_generation_output_root)


class ResumeOutputConfig(StrictSchemaModel):
    output_dir: str = Field(default_factory=_default_resume_output_dir)
    path: str | None = None
    pdf_path: str | None = None
    render_pdf: bool = False
    pdf_timeout_seconds: float = 60.0

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_output_paths(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        migrated = dict(data)
        output_dir = str(migrated.get("output_dir") or "").strip()
        if output_dir:
            return migrated

        legacy_candidates = [
            str(migrated.get("path") or "").strip(),
            str(migrated.get("pdf_path") or "").strip(),
        ]
        artifact_root = settings.resume_generation_artifacts_root.resolve(strict=False)
        for candidate in legacy_candidates:
            if not candidate:
                continue
            candidate_parent = Path(candidate).expanduser().parent
            if candidate_parent.resolve(strict=False) == artifact_root:
                continue
            migrated["output_dir"] = str(candidate_parent)
            return migrated
        return migrated

    @field_validator("output_dir")
    @classmethod
    def validate_output_dir(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("resume_output.output_dir must not be empty")
        output_dir = Path(normalized).expanduser()
        artifact_root = settings.resume_generation_artifacts_root.resolve(strict=False)
        resolved_output_dir = output_dir.resolve(strict=False)
        if resolved_output_dir == artifact_root or resolved_output_dir.is_relative_to(
            artifact_root
        ):
            raise ValueError(
                "resume_output.output_dir must be outside the internal artifacts directory"
            )
        return str(output_dir)

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("pdf_path")
    @classmethod
    def validate_pdf_path(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("pdf_timeout_seconds")
    @classmethod
    def validate_pdf_timeout_seconds(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("pdf_timeout_seconds must be greater than 0")
        return value


class OpenAIConfig(StrictSchemaModel):
    api_key: str | None = None

    @field_validator("api_key")
    @classmethod
    def validate_api_key(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class QwenConfig(StrictSchemaModel):
    api_key: str | None = None
    base_url: str = Field(default_factory=lambda: settings.QWEN_BASE_URL)

    @field_validator("api_key")
    @classmethod
    def validate_api_key(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        normalized = value.strip().rstrip("/")
        if not normalized:
            raise ValueError("qwen.base_url must not be empty")
        return normalized


class GitHubConfig(StrictSchemaModel):
    token: str | None = None

    @field_validator("token")
    @classmethod
    def validate_token(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class ResumeGenerationConfig(StrictSchemaModel):
    schema_version: Literal[1]
    llm_provider: Literal["openai", "qwen"] = Field(
        default_factory=lambda: settings.LLM_PROVIDER
    )
    openai: OpenAIConfig = Field(default_factory=OpenAIConfig)
    qwen: QwenConfig = Field(default_factory=QwenConfig)
    github: GitHubConfig = Field(default_factory=GitHubConfig)
    app: GenerationAppConfig = Field(default_factory=GenerationAppConfig)
    skill_selection: SkillSelectionConfig = Field(default_factory=SkillSelectionConfig)
    project_selection: ProjectSelectionConfig = Field(default_factory=ProjectSelectionConfig)
    experience_selection: ExperienceSelectionConfig = Field(
        default_factory=ExperienceSelectionConfig
    )
    job_focus_generation: JobFocusGenerationConfig = Field(
        default_factory=JobFocusGenerationConfig
    )
    link_scanning: LinkScanningConfig = Field(default_factory=LinkScanningConfig)
    project_bullet_point_generation: BulletPointGenerationConfig = Field(
        default_factory=BulletPointGenerationConfig
    )
    experience_bullet_point_generation: BulletPointGenerationConfig = Field(
        default_factory=BulletPointGenerationConfig
    )
    concurrency: ResumeGenerationConcurrencyConfig = Field(
        default_factory=ResumeGenerationConcurrencyConfig
    )
    cache: ResumeGenerationCacheConfig = Field(default_factory=ResumeGenerationCacheConfig)
    resume_output: ResumeOutputConfig = Field(default_factory=ResumeOutputConfig)

    @model_validator(mode="before")
    @classmethod
    def reject_legacy_bullet_point_generation(cls, data: Any) -> Any:
        if isinstance(data, dict) and "bullet_point_generation" in data:
            raise ValueError(
                "bullet_point_generation has been replaced by "
                "project_bullet_point_generation and "
                "experience_bullet_point_generation"
            )
        return data

    @field_validator("llm_provider", mode="before")
    @classmethod
    def normalize_llm_provider(cls, value: str) -> str:
        if isinstance(value, str):
            return value.strip().lower()
        return value


class JobTarget(StrictSchemaModel):
    schema_version: Literal[1]
    title: str
    description: str | None = None

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


class SkillSelectionResult(StrictSchemaModel):
    technology: list[str]
    programming: list[str]
    concepts: list[str]
    details: dict[str, Any] | None = None


class RankedProjectResult(StrictSchemaModel):
    project_id: str
    score: float
    method: Literal["baseline", "llm"]


class ProjectSelectionResult(StrictSchemaModel):
    selected_project_ids: list[str]
    ranked_projects: list[RankedProjectResult]
    details: dict[str, Any] | None = None


class ResumeSelectionContext(StrictSchemaModel):
    job_target: JobTarget
    selected_skills: SkillSelectionResult
    project_selection: ProjectSelectionResult
    selected_projects: list[ProjectRecord]
    config_path: Path
    job_target_path: Path
    evidence_paths: dict[str, Path]


class ProjectBulletPointResult(StrictSchemaModel):
    project_id: str
    bullet_points: list[str]
    details: dict[str, Any] | None = None


class ExperienceBulletPointResult(StrictSchemaModel):
    experience_id: str
    bullet_points: list[str]
    details: dict[str, Any] | None = None


class ResumeTopSection(StrictSchemaModel):
    name: str
    phone: str
    email: str
    github: str | None = None
    website: str | None = None
    linkedin: str | None = None


class ResumeEducationItem(StrictSchemaModel):
    name: str
    degree: str
    grade: str
    start: str
    end: str | None = None
    location: str
    relevant_coursework: list[str]


class ResumeExperienceItem(StrictSchemaModel):
    name: str
    role: str
    bullet_points: list[str]
    skills: list[str]
    location: str
    start: str
    end: str | None = None


class ResumeProjectItem(StrictSchemaModel):
    name: str
    bullet_points: list[str]
    skills: list[str]
    links: list[str]


class ResumeSkillsSection(StrictSchemaModel):
    technology: list[str]
    programming: list[str]
    concepts: list[str]


class IntermediateResumeResult(StrictSchemaModel):
    top: ResumeTopSection
    education: list[ResumeEducationItem]
    experience: list[ResumeExperienceItem]
    projects: list[ResumeProjectItem]
    skills: ResumeSkillsSection


class LinkScanHighlight(StrictSchemaModel):
    text: str
    source_url: str


class ProjectLinkScanResult(StrictSchemaModel):
    project_id: str
    added_highlights: list[LinkScanHighlight]
    details: dict[str, Any] | None = None
