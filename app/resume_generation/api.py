from __future__ import annotations

import ipaddress
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import field_validator, model_validator

from app.config import settings
from app.link_scanning.service import LinkScanningError
from app.resume_evidence import load_registered_evidence
from app.resume_generation.config import (
    load_generation_config,
    load_generation_config_payload,
    load_job_target,
    merge_generation_config_defaults,
    resolve_generation_config_path,
    resolve_job_target_path,
    write_generation_config_payload,
    write_job_target_payload,
)
from app.resume_generation.enrich import run_link_evidence_enrichment
from app.resume_generation.latex import (
    copy_resume_latex_to_user_output,
    resolve_resume_user_latex_output_path,
)
from app.resume_generation.main import (
    resolve_resume_result_artifact_path,
    resolve_resume_run_manifest_artifact_path,
    run_resume_generation_pipeline_async,
    write_resume_latex_from_config,
)
from app.resume_generation.models import (
    BulletCountRangeConfig,
    IntermediateResumeResult,
    JobTarget,
    ResumeGenerationConfig,
    StrictSchemaModel,
)
from app.resume_generation.pdf import (
    LatexPdfRenderError,
    copy_resume_pdf_to_user_output,
    render_latex_pdf,
    resolve_resume_user_pdf_output_path,
)
from app.resume_generation.selection import ResumeGenerationError
from app.resume_generation.status import (
    ResumeGenerationStatusSnapshot,
    resume_generation_status_store,
)

router = APIRouter(prefix="/resume-generation", tags=["resume-generation"])


class ResumeLinkEnrichmentRequest(StrictSchemaModel):
    evidence_type: Literal["projects", "experience", "all"] = "all"
    evidence_id: str | None = None
    dry_run: bool = False
    dev_mode: bool | None = None
    llm_model: str | None = None
    llm_max_output_tokens: int | None = None
    highlight_count: int | None = None
    max_tokens_per_highlight: int | None = None

    @field_validator("llm_model")
    @classmethod
    def validate_llm_model(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("llm_model must not be empty")
        return normalized

    @field_validator("evidence_id")
    @classmethod
    def validate_evidence_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("evidence_id must not be empty")
        return normalized

    @field_validator(
        "llm_max_output_tokens",
        "highlight_count",
        "max_tokens_per_highlight",
    )
    @classmethod
    def validate_positive_int(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            raise ValueError("value must be greater than 0")
        return value


class ResumeLinkEnrichmentRecordResponse(StrictSchemaModel):
    evidence_type: Literal["project", "experience"]
    evidence_id: str
    name: str
    scanned: bool
    added_highlights: list[str]
    skipped_reason: str | None = None
    details: dict[str, Any] | None = None


class ResumeLinkEnrichmentResponse(StrictSchemaModel):
    dry_run: bool
    scanned_count: int
    total_added_highlights: int
    updated_paths: list[str]
    records: list[ResumeLinkEnrichmentRecordResponse]


class ResumeTexGenerationRequest(StrictSchemaModel):
    job_target: JobTarget | None = None


class ResumeTexGenerationResponse(StrictSchemaModel):
    run_id: str
    resume_result: IntermediateResumeResult
    resume_result_path: str
    manifest_path: str
    tex_path: str
    artifact_tex_path: str
    tex_content: str


class ResumePdfGenerationRequest(StrictSchemaModel):
    pass


class ConfigSkillSelectionValues(StrictSchemaModel):
    top_n: int | None = None

    @field_validator("top_n")
    @classmethod
    def validate_top_n(cls, value: int | None) -> int | None:
        if value is not None and value < 0:
            raise ValueError("top_n must be greater than or equal to 0")
        return value


class ConfigProjectSelectionValues(StrictSchemaModel):
    top_n: int | None = None

    @field_validator("top_n")
    @classmethod
    def validate_top_n(cls, value: int | None) -> int | None:
        if value is not None and value < 0:
            raise ValueError("top_n must be greater than or equal to 0")
        return value


class ConfigExperienceSelectionValues(StrictSchemaModel):
    top_n: int | None = None

    @field_validator("top_n")
    @classmethod
    def validate_top_n(cls, value: int | None) -> int | None:
        if value is not None and value < 0:
            raise ValueError("top_n must be greater than or equal to 0")
        return value


class ConfigLinkScanningValues(StrictSchemaModel):
    highlight_count: int | None = None
    max_tokens_per_highlight: int | None = None

    @field_validator("highlight_count", "max_tokens_per_highlight")
    @classmethod
    def validate_positive_int(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            raise ValueError("value must be greater than 0")
        return value


class ConfigResumeOutputValues(StrictSchemaModel):
    output_dir: str | None = None

    @field_validator("output_dir")
    @classmethod
    def validate_output_dir(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("resume_output.output_dir must not be empty")
        return normalized


class ConfigOpenAIPatch(StrictSchemaModel):
    api_key: str | None = None
    clear_api_key: bool = False

    @field_validator("api_key")
    @classmethod
    def validate_api_key(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("api_key must not be empty; use clear_api_key to remove it")
        return normalized

    @model_validator(mode="after")
    def validate_clear_or_replace(self) -> "ConfigOpenAIPatch":
        if self.clear_api_key and "api_key" in self.model_fields_set:
            raise ValueError("Provide either api_key or clear_api_key, not both")
        return self


class ConfigQwenPatch(StrictSchemaModel):
    api_key: str | None = None
    clear_api_key: bool = False
    base_url: str | None = None

    @field_validator("api_key")
    @classmethod
    def validate_api_key(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("api_key must not be empty; use clear_api_key to remove it")
        return normalized

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().rstrip("/")
        if not normalized:
            raise ValueError("qwen.base_url must not be empty")
        return normalized

    @model_validator(mode="after")
    def validate_clear_or_replace(self) -> "ConfigQwenPatch":
        if self.clear_api_key and "api_key" in self.model_fields_set:
            raise ValueError("Provide either api_key or clear_api_key, not both")
        return self


class ConfigGitHubPatch(StrictSchemaModel):
    token: str | None = None
    clear_token: bool = False

    @field_validator("token")
    @classmethod
    def validate_token(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("token must not be empty; use clear_token to remove it")
        return normalized

    @model_validator(mode="after")
    def validate_clear_or_replace(self) -> "ConfigGitHubPatch":
        if self.clear_token and "token" in self.model_fields_set:
            raise ValueError("Provide either token or clear_token, not both")
        return self


class ResumeGenerationConfigPatch(StrictSchemaModel):
    llm_provider: Literal["openai", "qwen"] | None = None
    bullet_point_generation_strategy: Literal["section_batch", "per_record"] | None = None
    skill_selection: ConfigSkillSelectionValues | None = None
    project_selection: ConfigProjectSelectionValues | None = None
    experience_selection: ConfigExperienceSelectionValues | None = None
    link_scanning: ConfigLinkScanningValues | None = None
    resume_output: ConfigResumeOutputValues | None = None
    bullet_count_range: BulletCountRangeConfig | None = None
    openai: ConfigOpenAIPatch | None = None
    qwen: ConfigQwenPatch | None = None
    github: ConfigGitHubPatch | None = None

    @field_validator("llm_provider", mode="before")
    @classmethod
    def normalize_llm_provider(cls, value: str | None) -> str | None:
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @field_validator("bullet_point_generation_strategy", mode="before")
    @classmethod
    def normalize_bullet_point_generation_strategy(
        cls,
        value: str | None,
    ) -> str | None:
        if isinstance(value, str):
            return value.strip().lower()
        return value


class ConfigDisplayDefaults(StrictSchemaModel):
    skill_selection_top_n: str
    project_selection_top_n: str
    experience_selection_top_n: str
    link_scanning_highlight_count: str
    link_scanning_max_tokens_per_highlight: str
    bullet_count_range: str


class ConfigDefaultValues(StrictSchemaModel):
    skill_selection_top_n: int
    project_selection_top_n: int | None
    experience_selection_top_n: int | None
    link_scanning_highlight_count: int
    link_scanning_max_tokens_per_highlight: int
    bullet_count_range: BulletCountRangeConfig


class ConfigResumeOutputResponse(StrictSchemaModel):
    output_dir: str
    tex_path: str
    pdf_path: str
    artifact_tex_path: str
    artifact_pdf_path: str


class ResumeGenerationConfigResponse(StrictSchemaModel):
    schema_version: Literal[1]
    config_path: str
    llm_provider: Literal["openai", "qwen"]
    bullet_point_generation_strategy: Literal["section_batch", "per_record"]
    skill_selection: ConfigSkillSelectionValues
    project_selection: ConfigProjectSelectionValues
    experience_selection: ConfigExperienceSelectionValues
    link_scanning: ConfigLinkScanningValues
    resume_output: ConfigResumeOutputResponse
    bullet_count_range: BulletCountRangeConfig | None
    openai_api_key_configured: bool
    openai_api_key_saved: bool
    openai_api_key_source: Literal["environment", "config", "none"]
    qwen_api_key_configured: bool
    qwen_api_key_saved: bool
    qwen_api_key_source: Literal["environment", "config", "none"]
    qwen_base_url: str
    github_token_configured: bool
    github_token_saved: bool
    github_token_source: Literal["environment", "config", "none"]
    display_defaults: ConfigDisplayDefaults
    default_values: ConfigDefaultValues


class JobTargetResponse(StrictSchemaModel):
    schema_version: Literal[1]
    title: str
    description: str | None
    job_target_path: str


@router.get("/status", response_model=ResumeGenerationStatusSnapshot)
async def get_resume_generation_status() -> ResumeGenerationStatusSnapshot:
    return resume_generation_status_store.snapshot()


def _validation_error(exc: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


@router.get("/config", response_model=ResumeGenerationConfigResponse)
async def get_resume_generation_config() -> ResumeGenerationConfigResponse:
    try:
        payload = load_generation_config_payload(fill_defaults=True)
        config = ResumeGenerationConfig.model_validate(payload)
    except (FileNotFoundError, TypeError, ValueError) as exc:
        raise _validation_error(exc) from exc
    return _config_response(config)


@router.patch("/config", response_model=ResumeGenerationConfigResponse)
async def patch_resume_generation_config(
    request: Request,
    payload: ResumeGenerationConfigPatch,
) -> ResumeGenerationConfigResponse:
    if (
        _patch_changes_openai_key(payload)
        or _patch_changes_qwen_key(payload)
        or _patch_changes_github_token(payload)
    ) and not _is_secure_config_request(request):
        raise HTTPException(
            status_code=403,
            detail="Secret updates require HTTPS or a local loopback request.",
        )

    try:
        current_payload = load_generation_config_payload(fill_defaults=True)
        updated_payload = _apply_config_patch(current_payload, payload)
        config = write_generation_config_payload(updated_payload)
    except (FileNotFoundError, TypeError, ValueError) as exc:
        raise _validation_error(exc) from exc
    return _config_response(config)


@router.get("/job-target", response_model=JobTargetResponse)
async def get_resume_generation_job_target() -> JobTargetResponse:
    try:
        job_target = load_job_target()
    except (FileNotFoundError, TypeError, ValueError) as exc:
        raise _validation_error(exc) from exc
    return _job_target_response(job_target)


@router.put("/job-target", response_model=JobTargetResponse)
async def put_resume_generation_job_target(payload: JobTarget) -> JobTargetResponse:
    try:
        job_target = write_job_target_payload(payload.model_dump(mode="python"))
    except (FileNotFoundError, TypeError, ValueError) as exc:
        raise _validation_error(exc) from exc
    return _job_target_response(job_target)


@router.post("/enrich-link-evidence", response_model=ResumeLinkEnrichmentResponse)
async def enrich_resume_link_evidence(
    request: Request,
    payload: ResumeLinkEnrichmentRequest | None = None,
) -> ResumeLinkEnrichmentResponse:
    effective_payload = payload or ResumeLinkEnrichmentRequest()
    try:
        result = run_link_evidence_enrichment(
            evidence_type=effective_payload.evidence_type,
            evidence_id=effective_payload.evidence_id,
            dry_run=effective_payload.dry_run,
            dev_mode=effective_payload.dev_mode,
            llm_model=effective_payload.llm_model,
            llm_max_output_tokens=effective_payload.llm_max_output_tokens,
            highlight_count=effective_payload.highlight_count,
            max_tokens_per_highlight=effective_payload.max_tokens_per_highlight,
        )
    except LinkScanningError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except (FileNotFoundError, TypeError, ValueError) as exc:
        raise _validation_error(exc) from exc

    if result.updated_paths:
        request.app.state.resume_evidence = load_registered_evidence()

    return ResumeLinkEnrichmentResponse(
        dry_run=result.dry_run,
        scanned_count=result.scanned_count,
        total_added_highlights=result.total_added_highlights,
        updated_paths=list(result.updated_paths),
        records=[
            ResumeLinkEnrichmentRecordResponse(
                evidence_type=record.evidence_type,
                evidence_id=record.evidence_id,
                name=record.name,
                scanned=record.scanned,
                added_highlights=list(record.added_highlights),
                skipped_reason=record.skipped_reason,
                details=record.details,
            )
            for record in result.records
        ],
    )


def _apply_config_patch(
    current_payload: dict[str, Any],
    patch: ResumeGenerationConfigPatch,
) -> dict[str, Any]:
    updated = merge_generation_config_defaults(current_payload)

    if "llm_provider" in patch.model_fields_set:
        updated["llm_provider"] = patch.llm_provider

    if "bullet_point_generation_strategy" in patch.model_fields_set:
        updated["bullet_point_generation_strategy"] = (
            patch.bullet_point_generation_strategy
        )

    if patch.skill_selection is not None:
        fields = patch.skill_selection.model_fields_set
        if "top_n" in fields:
            updated["skill_selection"]["top_n"] = patch.skill_selection.top_n

    if patch.project_selection is not None:
        fields = patch.project_selection.model_fields_set
        if "top_n" in fields:
            updated["project_selection"]["top_n"] = patch.project_selection.top_n

    if patch.experience_selection is not None:
        fields = patch.experience_selection.model_fields_set
        if "top_n" in fields:
            updated["experience_selection"]["top_n"] = patch.experience_selection.top_n

    if patch.link_scanning is not None:
        fields = patch.link_scanning.model_fields_set
        if "highlight_count" in fields:
            updated["link_scanning"]["highlight_count"] = patch.link_scanning.highlight_count
        if "max_tokens_per_highlight" in fields:
            updated["link_scanning"]["max_tokens_per_highlight"] = (
                patch.link_scanning.max_tokens_per_highlight
            )

    if patch.resume_output is not None:
        updated.setdefault("resume_output", {})
        fields = patch.resume_output.model_fields_set
        if "output_dir" in fields:
            updated["resume_output"]["output_dir"] = patch.resume_output.output_dir

    if "bullet_count_range" in patch.model_fields_set:
        bullet_range = (
            patch.bullet_count_range.model_dump(mode="python")
            if patch.bullet_count_range is not None
            else None
        )
        updated["project_bullet_point_generation"]["bullet_count_range"] = bullet_range
        updated["experience_bullet_point_generation"]["bullet_count_range"] = bullet_range

    if patch.openai is not None:
        updated.setdefault("openai", {})
        if patch.openai.clear_api_key:
            updated["openai"]["api_key"] = None
        elif "api_key" in patch.openai.model_fields_set:
            updated["openai"]["api_key"] = patch.openai.api_key

    if patch.qwen is not None:
        updated.setdefault("qwen", {})
        if patch.qwen.clear_api_key:
            updated["qwen"]["api_key"] = None
        elif "api_key" in patch.qwen.model_fields_set:
            updated["qwen"]["api_key"] = patch.qwen.api_key
        if "base_url" in patch.qwen.model_fields_set:
            updated["qwen"]["base_url"] = patch.qwen.base_url

    if patch.github is not None:
        updated.setdefault("github", {})
        if patch.github.clear_token:
            updated["github"]["token"] = None
        elif "token" in patch.github.model_fields_set:
            updated["github"]["token"] = patch.github.token

    return updated


def _config_response(
    config: ResumeGenerationConfig,
) -> ResumeGenerationConfigResponse:
    openai_source = _openai_api_key_source(config)
    qwen_source = _qwen_api_key_source(config)
    github_source = _github_token_source(config)
    return ResumeGenerationConfigResponse(
        schema_version=1,
        config_path=str(resolve_generation_config_path()),
        llm_provider=config.llm_provider,
        bullet_point_generation_strategy=config.bullet_point_generation_strategy,
        skill_selection=ConfigSkillSelectionValues(
            top_n=config.skill_selection.top_n,
        ),
        project_selection=ConfigProjectSelectionValues(
            top_n=config.project_selection.top_n,
        ),
        experience_selection=ConfigExperienceSelectionValues(
            top_n=config.experience_selection.top_n,
        ),
        link_scanning=ConfigLinkScanningValues(
            highlight_count=config.link_scanning.highlight_count,
            max_tokens_per_highlight=config.link_scanning.max_tokens_per_highlight,
        ),
        resume_output=ConfigResumeOutputResponse(
            output_dir=config.resume_output.output_dir,
            tex_path=str(resolve_resume_user_latex_output_path(config.resume_output.output_dir)),
            pdf_path=str(resolve_resume_user_pdf_output_path(config.resume_output.output_dir)),
            artifact_tex_path=str(settings.resume_tex_artifact_path),
            artifact_pdf_path=str(settings.resume_pdf_artifact_path),
        ),
        bullet_count_range=config.project_bullet_point_generation.bullet_count_range,
        openai_api_key_configured=openai_source != "none",
        openai_api_key_saved=bool(config.openai.api_key),
        openai_api_key_source=openai_source,
        qwen_api_key_configured=qwen_source != "none",
        qwen_api_key_saved=bool(config.qwen.api_key),
        qwen_api_key_source=qwen_source,
        qwen_base_url=config.qwen.base_url,
        github_token_configured=github_source != "none",
        github_token_saved=bool(config.github.token),
        github_token_source=github_source,
        display_defaults=_config_display_defaults(),
        default_values=_config_default_values(),
    )


def _config_display_defaults() -> ConfigDisplayDefaults:
    default_bullet_count = settings.BULLETPOINTS_DEFAULT_COUNT
    project_top_n_default = (
        "unlimited (default)"
        if settings.PROJ_TOP_N is None
        else f"{settings.PROJ_TOP_N} (default)"
    )
    return ConfigDisplayDefaults(
        skill_selection_top_n=f"{settings.SKILL_TOP_N} (default)",
        project_selection_top_n=project_top_n_default,
        experience_selection_top_n="unlimited (default)",
        link_scanning_highlight_count=(
            f"{settings.LINK_SCANNING_DEFAULT_HIGHLIGHT_COUNT} (default)"
        ),
        link_scanning_max_tokens_per_highlight=(
            f"{settings.LINK_SCANNING_MAX_TOKENS_PER_HIGHLIGHT} (default)"
        ),
        bullet_count_range=f"{default_bullet_count} to {default_bullet_count} (default)",
    )


def _config_default_values() -> ConfigDefaultValues:
    default_bullet_count = settings.BULLETPOINTS_DEFAULT_COUNT
    return ConfigDefaultValues(
        skill_selection_top_n=settings.SKILL_TOP_N,
        project_selection_top_n=settings.PROJ_TOP_N,
        experience_selection_top_n=None,
        link_scanning_highlight_count=settings.LINK_SCANNING_DEFAULT_HIGHLIGHT_COUNT,
        link_scanning_max_tokens_per_highlight=settings.LINK_SCANNING_MAX_TOKENS_PER_HIGHLIGHT,
        bullet_count_range=BulletCountRangeConfig(
            min=default_bullet_count,
            max=default_bullet_count,
        ),
    )


def _openai_api_key_source(
    config: ResumeGenerationConfig,
) -> Literal["environment", "config", "none"]:
    if getattr(settings, "OPENAI_API_KEY", "").strip():
        return "environment"
    if config.openai.api_key:
        return "config"
    return "none"


def _qwen_api_key_source(
    config: ResumeGenerationConfig,
) -> Literal["environment", "config", "none"]:
    if getattr(settings, "QWEN_API_KEY", "").strip():
        return "environment"
    if getattr(settings, "DASHSCOPE_API_KEY", "").strip():
        return "environment"
    if config.qwen.api_key:
        return "config"
    return "none"


def _github_token_source(
    config: ResumeGenerationConfig,
) -> Literal["environment", "config", "none"]:
    if getattr(settings, "RESUMECR7_GITHUB_TOKEN", "").strip():
        return "environment"
    if getattr(settings, "GITHUB_TOKEN", "").strip():
        return "environment"
    if config.github.token:
        return "config"
    return "none"


def _job_target_response(job_target: JobTarget) -> JobTargetResponse:
    return JobTargetResponse(
        schema_version=job_target.schema_version,
        title=job_target.title,
        description=job_target.description,
        job_target_path=str(resolve_job_target_path()),
    )


def _patch_changes_openai_key(payload: ResumeGenerationConfigPatch) -> bool:
    if payload.openai is None:
        return False
    return payload.openai.clear_api_key or "api_key" in payload.openai.model_fields_set


def _patch_changes_qwen_key(payload: ResumeGenerationConfigPatch) -> bool:
    if payload.qwen is None:
        return False
    return payload.qwen.clear_api_key or "api_key" in payload.qwen.model_fields_set


def _patch_changes_github_token(payload: ResumeGenerationConfigPatch) -> bool:
    if payload.github is None:
        return False
    return payload.github.clear_token or "token" in payload.github.model_fields_set


def _is_secure_config_request(request: Request) -> bool:
    if request.url.scheme == "https":
        return True
    host = request.url.hostname
    if host is None:
        return False
    if host == "localhost" or host == "testserver":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


@router.post("/tex", response_model=ResumeTexGenerationResponse)
async def generate_resume_tex(
    payload: ResumeTexGenerationRequest | None = None,
) -> ResumeTexGenerationResponse:
    effective_payload = payload or ResumeTexGenerationRequest()
    run_id = resume_generation_status_store.start_run(operation="tex")
    try:
        if effective_payload.job_target is None:
            resume_result = await run_resume_generation_pipeline_async(
                status_reporter=resume_generation_status_store.reporter(),
            )
        else:
            resume_result = await run_resume_generation_pipeline_async(
                job_target_override=effective_payload.job_target,
                status_reporter=resume_generation_status_store.reporter(),
            )
        resume_generation_status_store.update_stage(
            "latex_rendering",
            "running",
            "Rendering .tex",
        )
        tex_path = write_resume_latex_from_config(resume_result)
        resume_generation_status_store.update_stage(
            "latex_rendering",
            "succeeded",
            "Done",
        )
        tex_content = tex_path.read_text(encoding="utf-8")
        resume_generation_status_store.complete_run()
    except ResumeGenerationError as exc:
        resume_generation_status_store.fail_run(str(exc))
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except (FileNotFoundError, TypeError, ValueError) as exc:
        resume_generation_status_store.fail_run(str(exc))
        raise _validation_error(exc) from exc
    except Exception as exc:
        resume_generation_status_store.fail_run(str(exc))
        raise

    return ResumeTexGenerationResponse(
        run_id=run_id,
        resume_result=resume_result,
        resume_result_path=str(resolve_resume_result_artifact_path()),
        manifest_path=str(resolve_resume_run_manifest_artifact_path()),
        tex_path=str(tex_path),
        artifact_tex_path=str(settings.resume_tex_artifact_path),
        tex_content=tex_content,
    )


@router.post("/pdf", response_class=Response)
async def generate_resume_pdf(
    _payload: ResumePdfGenerationRequest | None = None,
) -> Response:
    try:
        config = load_generation_config(resolve_generation_config_path())
        artifact_tex_path = settings.resume_tex_artifact_path
        artifact_pdf_path = render_latex_pdf(
            artifact_tex_path,
            settings.resume_pdf_artifact_path,
            timeout_seconds=config.resume_output.pdf_timeout_seconds,
        )
        pdf_path = copy_resume_pdf_to_user_output(
            artifact_pdf_path,
            config.resume_output.output_dir,
        )
        tex_path = copy_resume_latex_to_user_output(
            artifact_tex_path,
            config.resume_output.output_dir,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except LatexPdfRenderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise _validation_error(exc) from exc

    return Response(
        content=pdf_path.read_bytes(),
        media_type="application/pdf",
        headers={
            "X-ResumeCR7-Tex-Path": str(tex_path),
            "X-ResumeCR7-Pdf-Path": str(pdf_path),
            "X-ResumeCR7-Artifact-Tex-Path": str(artifact_tex_path),
            "X-ResumeCR7-Artifact-Pdf-Path": str(artifact_pdf_path),
            "Content-Disposition": f'attachment; filename="{pdf_path.name}"',
        },
    )
