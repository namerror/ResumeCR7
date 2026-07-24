from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import field_validator

from app.link_scanning.service import LinkScanningError
from app.resume_evidence import load_registered_evidence
from app.resume_generation.config import load_generation_config, resolve_generation_config_path
from app.resume_generation.enrich import run_link_evidence_enrichment
from app.resume_generation.latex import resolve_resume_latex_output_path
from app.resume_generation.main import (
    resolve_resume_result_artifact_path,
    resolve_resume_run_manifest_artifact_path,
    run_resume_generation_pipeline,
    write_resume_latex_from_config,
)
from app.resume_generation.models import (
    IntermediateResumeResult,
    JobTarget,
    StrictSchemaModel,
)
from app.resume_generation.pdf import LatexPdfRenderError, render_latex_pdf
from app.resume_generation.selection import ResumeGenerationError

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
    resume_result: IntermediateResumeResult
    resume_result_path: str
    manifest_path: str
    tex_path: str
    tex_content: str


class ResumePdfGenerationRequest(StrictSchemaModel):
    pass


def _validation_error(exc: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


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


@router.post("/tex", response_model=ResumeTexGenerationResponse)
async def generate_resume_tex(
    payload: ResumeTexGenerationRequest | None = None,
) -> ResumeTexGenerationResponse:
    effective_payload = payload or ResumeTexGenerationRequest()
    try:
        if effective_payload.job_target is None:
            resume_result = run_resume_generation_pipeline()
        else:
            resume_result = run_resume_generation_pipeline(
                job_target_override=effective_payload.job_target,
            )
        tex_path = write_resume_latex_from_config(resume_result)
        tex_content = tex_path.read_text(encoding="utf-8")
    except ResumeGenerationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except (FileNotFoundError, TypeError, ValueError) as exc:
        raise _validation_error(exc) from exc

    return ResumeTexGenerationResponse(
        resume_result=resume_result,
        resume_result_path=str(resolve_resume_result_artifact_path()),
        manifest_path=str(resolve_resume_run_manifest_artifact_path()),
        tex_path=str(tex_path),
        tex_content=tex_content,
    )


@router.post("/pdf", response_class=Response)
async def generate_resume_pdf(
    _payload: ResumePdfGenerationRequest | None = None,
) -> Response:
    try:
        config = load_generation_config(resolve_generation_config_path())
        tex_path = resolve_resume_latex_output_path(config.resume_output.path)
        pdf_path = render_latex_pdf(
            tex_path,
            config.resume_output.pdf_path,
            timeout_seconds=config.resume_output.pdf_timeout_seconds,
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
            "Content-Disposition": f'attachment; filename="{pdf_path.name}"',
        },
    )
