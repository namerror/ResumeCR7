from __future__ import annotations

import logging
import time
from typing import Any

from app.bulletpoints_generation.llm_client import (
    BulletPointLLMClientError,
    generate_bulletpoints_with_llm,
    generate_bulletpoints_with_llm_async,
)
from app.bulletpoints_generation.models import (
    BulletCountRange,
    BulletGenerationRequest,
    BulletGenerationResponse,
)
from app.config import settings
from app.metrics import metrics

logger = logging.getLogger("bulletpoints_generator")

METRICS_SUBSYSTEM = "bulletpoints_generation"


class BulletPointGenerationError(RuntimeError):
    """Raised when bullet-point generation cannot complete."""


def effective_bullet_count_range(requested: BulletCountRange | None) -> BulletCountRange:
    if requested is not None:
        return requested
    default_count = settings.BULLETPOINTS_DEFAULT_COUNT
    return BulletCountRange(min=default_count, max=default_count)


def _extract_total_tokens(result_metadata: dict[str, Any] | None) -> int:
    if not isinstance(result_metadata, dict):
        return 0
    try:
        return int(result_metadata.get("total_tokens", 0) or 0)
    except (TypeError, ValueError):
        return 0


def record_bulletpoint_generation_error(method: str = "llm") -> None:
    metrics.inc_request(method=method, subsystem=METRICS_SUBSYSTEM)
    metrics.inc_error(subsystem=METRICS_SUBSYSTEM)


def generate_bulletpoints_service(req: BulletGenerationRequest) -> BulletGenerationResponse:
    dev_mode = req.dev_mode if req.dev_mode is not None else settings.DEV_MODE
    count_range = effective_bullet_count_range(req.bullet_count_range)
    start = time.perf_counter()
    request_counted = False
    llm_metadata: dict[str, Any] | None = None

    try:
        llm_result = generate_bulletpoints_with_llm(
            context=req.context,
            project=req.project,
            experience=req.experience,
            count_range=count_range,
            model=req.llm_model,
            max_output_tokens=req.llm_max_output_tokens,
            output_token_budget=req.llm_output_token_budget,
        )
        llm_metadata = llm_result.metadata

        latency_ms = (time.perf_counter() - start) * 1000.0
        metrics.inc_request(method="llm", subsystem=METRICS_SUBSYSTEM)
        request_counted = True
        metrics.observe_tokens(_extract_total_tokens(llm_metadata), subsystem=METRICS_SUBSYSTEM)
        metrics.observe_latency_ms(latency_ms, subsystem=METRICS_SUBSYSTEM)

        logger.info(
            "generate_bulletpoints",
            extra={
                "event": "generate_bulletpoints",
                "subsystem": METRICS_SUBSYSTEM,
                "job_title": req.context.title,
                "evidence_type": req.evidence_type,
                "evidence_id": req.evidence_id,
                "method": "llm",
                "latency_ms": round(latency_ms, 3),
                "bullet_count": len(llm_result.bullet_points),
                "requested_llm_max_output_tokens": req.llm_max_output_tokens,
                "resolved_llm_max_output_tokens": (
                    llm_metadata.get("resolved_llm_max_output_tokens")
                    if isinstance(llm_metadata, dict)
                    else None
                ),
                "llm_output_token_budget_mode": (
                    llm_metadata.get("llm_output_token_budget_mode")
                    if isinstance(llm_metadata, dict)
                    else None
                ),
            },
        )

        details: dict[str, Any] | None = None
        if dev_mode:
            details = {
                "method": "llm",
                "requested_count_range": (
                    req.bullet_count_range.model_dump()
                    if req.bullet_count_range is not None
                    else None
                ),
                "effective_count_range": count_range.model_dump(),
                "evidence_type": req.evidence_type,
                "_bulletpoints_llm": llm_metadata,
            }

        return BulletGenerationResponse(
            bullet_points=llm_result.bullet_points,
            details=details,
        )

    except BulletPointLLMClientError as exc:
        if not request_counted:
            metrics.inc_request(method="llm", subsystem=METRICS_SUBSYSTEM)
        metrics.inc_error(subsystem=METRICS_SUBSYSTEM)
        llm_metadata = exc.metadata
        logger.warning(
            "generate_bulletpoints_failed",
            extra={
                "event": "generate_bulletpoints_failed",
                "subsystem": METRICS_SUBSYSTEM,
                "job_title": req.context.title,
                "evidence_type": req.evidence_type,
                "evidence_id": req.evidence_id,
                "method": "llm",
                "error": str(exc),
                "requested_llm_max_output_tokens": req.llm_max_output_tokens,
                "resolved_llm_max_output_tokens": (
                    llm_metadata.get("resolved_llm_max_output_tokens")
                    if isinstance(llm_metadata, dict)
                    else None
                ),
                "llm_output_token_budget_mode": (
                    llm_metadata.get("llm_output_token_budget_mode")
                    if isinstance(llm_metadata, dict)
                    else None
                ),
            },
        )
        raise BulletPointGenerationError(str(exc)) from exc


async def generate_bulletpoints_service_async(
    req: BulletGenerationRequest,
) -> BulletGenerationResponse:
    dev_mode = req.dev_mode if req.dev_mode is not None else settings.DEV_MODE
    count_range = effective_bullet_count_range(req.bullet_count_range)
    start = time.perf_counter()
    request_counted = False
    llm_metadata: dict[str, Any] | None = None

    try:
        llm_result = await generate_bulletpoints_with_llm_async(
            context=req.context,
            project=req.project,
            experience=req.experience,
            count_range=count_range,
            model=req.llm_model,
            max_output_tokens=req.llm_max_output_tokens,
            output_token_budget=req.llm_output_token_budget,
        )
        llm_metadata = llm_result.metadata

        latency_ms = (time.perf_counter() - start) * 1000.0
        metrics.inc_request(method="llm", subsystem=METRICS_SUBSYSTEM)
        request_counted = True
        metrics.observe_tokens(_extract_total_tokens(llm_metadata), subsystem=METRICS_SUBSYSTEM)
        metrics.observe_latency_ms(latency_ms, subsystem=METRICS_SUBSYSTEM)

        logger.info(
            "generate_bulletpoints",
            extra={
                "event": "generate_bulletpoints",
                "subsystem": METRICS_SUBSYSTEM,
                "job_title": req.context.title,
                "evidence_type": req.evidence_type,
                "evidence_id": req.evidence_id,
                "method": "llm",
                "latency_ms": round(latency_ms, 3),
                "bullet_count": len(llm_result.bullet_points),
                "requested_llm_max_output_tokens": req.llm_max_output_tokens,
                "resolved_llm_max_output_tokens": (
                    llm_metadata.get("resolved_llm_max_output_tokens")
                    if isinstance(llm_metadata, dict)
                    else None
                ),
                "llm_output_token_budget_mode": (
                    llm_metadata.get("llm_output_token_budget_mode")
                    if isinstance(llm_metadata, dict)
                    else None
                ),
            },
        )

        details: dict[str, Any] | None = None
        if dev_mode:
            details = {
                "method": "llm",
                "requested_count_range": (
                    req.bullet_count_range.model_dump()
                    if req.bullet_count_range is not None
                    else None
                ),
                "effective_count_range": count_range.model_dump(),
                "evidence_type": req.evidence_type,
                "_bulletpoints_llm": llm_metadata,
            }

        return BulletGenerationResponse(
            bullet_points=llm_result.bullet_points,
            details=details,
        )

    except BulletPointLLMClientError as exc:
        if not request_counted:
            metrics.inc_request(method="llm", subsystem=METRICS_SUBSYSTEM)
        metrics.inc_error(subsystem=METRICS_SUBSYSTEM)
        llm_metadata = exc.metadata
        logger.warning(
            "generate_bulletpoints_failed",
            extra={
                "event": "generate_bulletpoints_failed",
                "subsystem": METRICS_SUBSYSTEM,
                "job_title": req.context.title,
                "evidence_type": req.evidence_type,
                "evidence_id": req.evidence_id,
                "method": "llm",
                "error": str(exc),
                "requested_llm_max_output_tokens": req.llm_max_output_tokens,
                "resolved_llm_max_output_tokens": (
                    llm_metadata.get("resolved_llm_max_output_tokens")
                    if isinstance(llm_metadata, dict)
                    else None
                ),
                "llm_output_token_budget_mode": (
                    llm_metadata.get("llm_output_token_budget_mode")
                    if isinstance(llm_metadata, dict)
                    else None
                ),
            },
        )
        raise BulletPointGenerationError(str(exc)) from exc
