from contextlib import asynccontextmanager
import logging
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from app import __version__
from pydantic import ValidationError

from app.skill_selection.models import SkillSelectRequest, SkillSelectResponse
from app.config import settings
from app.skill_selection.selector import select_skills_service
from app.metrics import metrics
from app.logging_config import setup_logging
from app.runtime_data import bootstrap_runtime_data
from app.project_selection.models import ProjectSelectRequest, ProjectSelectionResult
from app.project_selection.service import record_project_selection_error, select_projects_service
from app.bulletpoints_generation.models import (
    BulletGenerationRequest,
    BulletGenerationResponse,
)
from app.bulletpoints_generation.llm_client import DEFAULT_BULLET_OUTPUT_TOKEN_BUDGET
from app.bulletpoints_generation.service import (
    BulletPointGenerationError,
    generate_bulletpoints_service_async,
    record_bulletpoint_generation_error,
)
from app.link_scanning.models import LinkScanRequest, LinkScanResponse
from app.link_scanning.service import LinkScanningError, scan_link_evidence_service
from app.job_focus_generation.models import JobFocusRequest, JobFocusResponse
from app.job_focus_generation.service import (
    JobFocusGenerationError,
    derive_job_focus_service,
    record_job_focus_generation_error,
)
from app.resume_evidence import load_registered_evidence
from app.resume_evidence.api import router as resume_evidence_router
from app.resume_generation.api import router as resume_generation_router


logger = logging.getLogger("app_main")

DESKTOP_CORS_ORIGINS = [
    "http://127.0.0.1:5173",
    "http://localhost:5173",
    "http://127.0.0.1:4173",
    "http://localhost:4173",
    "tauri://localhost",
    "http://tauri.localhost",
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    bootstrap_runtime_data(
        data_dir=settings.RESUMECR7_DATA_DIR,
        evidence_root=settings.RESUME_EVIDENCE_ROOT,
        generation_root=settings.RESUME_GENERATION_ROOT,
        artifacts_root=settings.resume_generation_artifacts_root,
        log_dir=settings.RESUMECR7_LOG_DIR,
    )
    setup_logging(settings.LOG_LEVEL, log_path=settings.log_file_path)
    app.state.resume_evidence = load_registered_evidence()
    yield


app = FastAPI(title="ResumeCR7 Resume Engine", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=DESKTOP_CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(resume_evidence_router)
app.include_router(resume_generation_router)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "version": __version__,
        "service": "resumecr7-resume-engine",
        "dev_mode": settings.DEV_MODE,
        "skill_selection": {
            "method": settings.SKILL_METHOD,
            "top_n": settings.SKILL_TOP_N,
            "baseline_filter": settings.SKILL_BASELINE_FILTER,
            "llm_model": settings.SKILL_LLM_MODEL,
            "llm_max_output_tokens": settings.SKILL_LLM_MAX_OUTPUT_TOKENS,
        },
        "project_selection": {
            "method": settings.PROJ_METHOD,
            "top_n": settings.PROJ_TOP_N,
            "llm_model": settings.PROJ_LLM_MODEL,
            "llm_output_token_budget": None,
        },
        "bulletpoints_generation": {
            "llm_model": settings.BULLETPOINTS_LLM_MODEL,
            "llm_output_token_budget": DEFAULT_BULLET_OUTPUT_TOKEN_BUDGET.model_dump(),
            "default_count": settings.BULLETPOINTS_DEFAULT_COUNT,
        },
        "job_focus_generation": {
            "llm_model": settings.JOB_FOCUS_LLM_MODEL,
            "llm_max_output_tokens": settings.JOB_FOCUS_LLM_MAX_OUTPUT_TOKENS,
        },
        "link_scanning": {
            "enabled": settings.LINK_SCANNING_ENABLED,
            "llm_model": settings.LINK_SCANNING_LLM_MODEL,
            "llm_max_output_tokens": settings.LINK_SCANNING_LLM_MAX_OUTPUT_TOKENS,
            "default_highlight_count": settings.LINK_SCANNING_DEFAULT_HIGHLIGHT_COUNT,
            "max_tokens_per_highlight": settings.LINK_SCANNING_MAX_TOKENS_PER_HIGHLIGHT,
        },
        "paths": {
            "data_dir": str(settings.RESUMECR7_DATA_DIR),
            "resume_evidence_root": str(settings.RESUME_EVIDENCE_ROOT),
            "resume_generation_root": str(settings.RESUME_GENERATION_ROOT),
            "log_file": str(settings.log_file_path),
        },
    }


@app.get("/metrics-lite")
async def get_metrics():
    return {
        "requests_total": metrics.requests_total,
        "errors_total": metrics.errors_total,
        "total_tokens": metrics.total_tokens,
        "avg_latency_ms": round(metrics.avg_latency_ms(), 3),
        "method_usage": metrics.method_usage,
        "subsystems": metrics.subsystem_snapshots(),
    }


@app.post("/select-skills", response_model=SkillSelectResponse)
async def select_skills(payload: SkillSelectRequest) -> SkillSelectResponse:
    logger.info(
        "app_content_stage_request",
        extra={
            "event": "app_content_stage_request",
            "stage": "skill_selection",
            "endpoint": "/select-skills",
            "source": "http",
            "llm_max_output_tokens": payload.llm_max_output_tokens,
        },
    )
    try:
        return select_skills_service(payload)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))


@app.post("/generate-bulletpoints", response_model=BulletGenerationResponse)
async def generate_bulletpoints(payload: BulletGenerationRequest) -> BulletGenerationResponse:
    logger.info(
        "app_content_stage_request",
        extra={
            "event": "app_content_stage_request",
            "stage": f"{payload.evidence_type}_bullet_points",
            "endpoint": "/generate-bulletpoints",
            "source": "http",
            "evidence_type": payload.evidence_type,
            "evidence_id": payload.evidence_id,
            "requested_llm_max_output_tokens": payload.llm_max_output_tokens,
            "llm_output_token_budget": (
                payload.llm_output_token_budget.model_dump()
                if payload.llm_output_token_budget is not None
                else None
            ),
        },
    )
    try:
        return await generate_bulletpoints_service_async(payload)
    except ValueError as ve:
        record_bulletpoint_generation_error()
        raise HTTPException(status_code=400, detail=str(ve))
    except BulletPointGenerationError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@app.post("/derive-job-focus", response_model=JobFocusResponse)
async def derive_job_focus(payload: JobFocusRequest) -> JobFocusResponse:
    logger.info(
        "app_content_stage_request",
        extra={
            "event": "app_content_stage_request",
            "stage": "job_focus_generation",
            "endpoint": "/derive-job-focus",
            "source": "http",
            "llm_max_output_tokens": payload.llm_max_output_tokens,
        },
    )
    try:
        return derive_job_focus_service(payload)
    except ValueError as ve:
        record_job_focus_generation_error()
        raise HTTPException(status_code=400, detail=str(ve))
    except JobFocusGenerationError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


def _link_scan_log_extra(payload: LinkScanRequest, endpoint: str) -> dict[str, Any]:
    return {
        "event": "app_content_stage_request",
        "stage": "link_scanning",
        "endpoint": endpoint,
        "source": "http",
        "evidence_type": payload.evidence_type,
        "evidence_id": payload.evidence.id,
    }


@app.post("/enrich-link-evidence", response_model=LinkScanResponse)
async def enrich_link_evidence(payload: LinkScanRequest) -> LinkScanResponse:
    logger.info(
        "app_content_stage_request",
        extra=_link_scan_log_extra(payload, "/enrich-link-evidence"),
    )
    try:
        return scan_link_evidence_service(payload)
    except LinkScanningError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@app.post("/select-projects", response_model=ProjectSelectionResult)
async def select_projects(payload: dict[str, Any]) -> ProjectSelectionResult:
    logger.info(
        "app_content_stage_request",
        extra={
            "event": "app_content_stage_request",
            "stage": "project_selection",
            "endpoint": "/select-projects",
            "source": "http",
            "requested_llm_max_output_tokens": (
                payload.get("llm_max_output_tokens") if isinstance(payload, dict) else None
            ),
            "llm_output_token_budget": (
                payload.get("llm_output_token_budget") if isinstance(payload, dict) else None
            ),
        },
    )
    try:
        request = ProjectSelectRequest.model_validate(payload)
        return select_projects_service(request)
    except ValidationError as ve:
        method = payload.get("method") if isinstance(payload, dict) else None
        record_project_selection_error(method if isinstance(method, str) else "invalid")
        raise HTTPException(status_code=400, detail=str(ve))
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
