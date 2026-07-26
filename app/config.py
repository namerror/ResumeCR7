from pathlib import Path
from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.data_paths import resolve_default_data_dir


SkillSelectionMethod = Literal["baseline", "embeddings", "llm"]
ProjectSelectionMethod = Literal["baseline", "llm"]

_REPO_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    SKILL_TOP_N: int = 10
    SKILL_METHOD: SkillSelectionMethod = "baseline"
    SKILL_BASELINE_FILTER: bool = False
    PROJ_TOP_N: int | None = None
    PROJ_METHOD: ProjectSelectionMethod = "llm"
    DEV_MODE: bool = True
    LOG_LEVEL: str = "INFO"
    RESUMECR7_PACKAGED: bool = False
    RESUMECR7_DATA_DIR: Path | None = None
    RESUME_EVIDENCE_ROOT: Path | None = None
    RESUME_GENERATION_ROOT: Path | None = None
    RESUMECR7_LOG_DIR: Path | None = None

    # Embedding-related settings, only relevant if SKILL_METHOD=embeddings
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_BATCH_SIZE: int = 100
    # EMBEDDING_DIMENSIONS: int = 1024 # Optionally reduce dimensionality

    # LLM-related settings, split by subsystem so selection methods can be tuned independently.
    SKILL_LLM_MODEL: str = "gpt-5-mini"
    SKILL_LLM_MAX_OUTPUT_TOKENS: int = 1200
    PROJ_LLM_MODEL: str = "gpt-5-mini"
    JOB_FOCUS_LLM_MODEL: str = "gpt-5-mini"
    JOB_FOCUS_LLM_MAX_OUTPUT_TOKENS: int = 1200
    BULLETPOINTS_LLM_MODEL: str = "gpt-5-mini"
    BULLETPOINTS_DEFAULT_COUNT: int = 3
    LINK_SCANNING_ENABLED: bool = False
    LINK_SCANNING_LLM_MODEL: str = "gpt-5-mini"
    LINK_SCANNING_LLM_MAX_OUTPUT_TOKENS: int = 1200
    LINK_SCANNING_DEFAULT_HIGHLIGHT_COUNT: int = 6
    LINK_SCANNING_MAX_TOKENS_PER_HIGHLIGHT: int = 120

    OPENAI_API_KEY: str = "" # This should be set in the .env file or environment variable

    @model_validator(mode="after")
    def resolve_data_roots(self) -> "Settings":
        if self.RESUMECR7_DATA_DIR is None:
            self.RESUMECR7_DATA_DIR = resolve_default_data_dir(
                repo_root=_REPO_ROOT,
                packaged=self.RESUMECR7_PACKAGED,
            )
        if self.RESUME_EVIDENCE_ROOT is None:
            self.RESUME_EVIDENCE_ROOT = self.RESUMECR7_DATA_DIR / "resume_evidence"
        if self.RESUME_GENERATION_ROOT is None:
            self.RESUME_GENERATION_ROOT = self.RESUMECR7_DATA_DIR / "resume_generation"
        if self.RESUMECR7_LOG_DIR is None:
            self.RESUMECR7_LOG_DIR = self.RESUMECR7_DATA_DIR / "logs"
        return self

    @property
    def generation_config_path(self) -> Path:
        return self.RESUME_GENERATION_ROOT / "config.yaml"

    @property
    def job_target_path(self) -> Path:
        return self.RESUME_GENERATION_ROOT / "job_target.yaml"

    @property
    def resume_generation_artifacts_root(self) -> Path:
        return self.RESUME_GENERATION_ROOT / "artifacts"

    @property
    def resume_result_artifact_path(self) -> Path:
        return self.resume_generation_artifacts_root / "resume_result.json"

    @property
    def resume_run_manifest_artifact_path(self) -> Path:
        return self.resume_generation_artifacts_root / "resume_run_manifest.json"

    @property
    def resume_tex_artifact_path(self) -> Path:
        return self.resume_generation_artifacts_root / "resume.tex"

    @property
    def resume_pdf_artifact_path(self) -> Path:
        return self.resume_generation_artifacts_root / "resume.pdf"

    @property
    def log_file_path(self) -> Path:
        return self.RESUMECR7_LOG_DIR / "resumecr7.log"

    @field_validator("SKILL_METHOD", "PROJ_METHOD", mode="before")
    @classmethod
    def normalize_method(cls, value: str) -> str:
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @field_validator("BULLETPOINTS_DEFAULT_COUNT")
    @classmethod
    def validate_bulletpoints_default_count(cls, value: int) -> int:
        if value < 1 or value > 10:
            raise ValueError("BULLETPOINTS_DEFAULT_COUNT must be between 1 and 10")
        return value

    @field_validator(
        "SKILL_LLM_MAX_OUTPUT_TOKENS",
        "JOB_FOCUS_LLM_MAX_OUTPUT_TOKENS",
        "LINK_SCANNING_LLM_MAX_OUTPUT_TOKENS",
    )
    @classmethod
    def validate_llm_max_output_tokens(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("LLM max output tokens must be greater than 0")
        return value

    @field_validator(
        "LINK_SCANNING_DEFAULT_HIGHLIGHT_COUNT",
        "LINK_SCANNING_MAX_TOKENS_PER_HIGHLIGHT",
    )
    @classmethod
    def validate_positive_link_scanning_ints(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("Link scanning counts and token budgets must be greater than 0")
        return value


settings = Settings()
