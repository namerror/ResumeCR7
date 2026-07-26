from __future__ import annotations

import logging
import time

from app.config import settings
from app.metrics import metrics
from app.project_selection.models import ProjectSelectRequest, ProjectSelectionResult
from app.project_selection.selector import select_projects

logger = logging.getLogger("project_selector")

METRICS_SUBSYSTEM = "project_selection"


def _effective_method(requested_method: str, result: ProjectSelectionResult) -> str:
    details = result.details
    if isinstance(details, dict):
        fallback_method = details.get("_fallback_method")
        if isinstance(fallback_method, str) and fallback_method:
            return fallback_method

        llm_meta = details.get("_project_llm")
        if isinstance(llm_meta, dict) and llm_meta.get("fallback") == "baseline":
            return "baseline"

    if result.ranked_projects:
        return result.ranked_projects[0].method

    return requested_method


def _extract_total_tokens(result: ProjectSelectionResult) -> int:
    details = result.details
    if not isinstance(details, dict):
        return 0

    llm_meta = details.get("_project_llm")
    if not isinstance(llm_meta, dict):
        return 0

    try:
        return int(llm_meta.get("total_tokens", 0) or 0)
    except (TypeError, ValueError):
        return 0


def _extract_project_llm_metadata(result: ProjectSelectionResult) -> dict | None:
    details = result.details
    if not isinstance(details, dict):
        return None
    llm_meta = details.get("_project_llm")
    return llm_meta if isinstance(llm_meta, dict) else None


def record_project_selection_error(method: str = "invalid") -> None:
    metrics.inc_request(method=method, subsystem=METRICS_SUBSYSTEM)
    metrics.inc_error(subsystem=METRICS_SUBSYSTEM)


def select_projects_service(req: ProjectSelectRequest) -> ProjectSelectionResult:
    method = req.method or settings.PROJ_METHOD
    top_n = req.top_n if req.top_n is not None else settings.PROJ_TOP_N
    dev_mode = req.dev_mode if req.dev_mode is not None else settings.DEV_MODE
    if req.llm_max_output_tokens is not None and req.llm_max_output_tokens <= 0:
        raise ValueError("llm_max_output_tokens must be greater than 0")

    start = time.perf_counter()
    request_counted = False

    try:
        result = select_projects(
            context=req.context,
            candidates=req.candidates,
            method=method,
            top_n=top_n,
            dev_mode=dev_mode,
            llm_model=req.llm_model,
            llm_max_output_tokens=req.llm_max_output_tokens,
            llm_output_token_budget=req.llm_output_token_budget,
        )

        latency_ms = (time.perf_counter() - start) * 1000.0
        effective_method = _effective_method(method, result)
        llm_metadata = _extract_project_llm_metadata(result)
        metrics.inc_request(method=effective_method, subsystem=METRICS_SUBSYSTEM)
        request_counted = True
        metrics.observe_tokens(_extract_total_tokens(result), subsystem=METRICS_SUBSYSTEM)
        metrics.observe_latency_ms(latency_ms, subsystem=METRICS_SUBSYSTEM)

        logger.info(
            "select_projects",
            extra={
                "event": "select_projects",
                "subsystem": METRICS_SUBSYSTEM,
                "job_title": req.context.title,
                "method": effective_method,
                "requested_method": method,
                "top_n": top_n,
                "latency_ms": round(latency_ms, 3),
                "candidate_count": len(req.candidates),
                "selected_count": len(result.selected_project_ids),
                "requested_llm_max_output_tokens": req.llm_max_output_tokens,
                "resolved_llm_max_output_tokens": (
                    llm_metadata.get("resolved_llm_max_output_tokens")
                    if llm_metadata is not None
                    else None
                ),
                "llm_output_token_budget_mode": (
                    llm_metadata.get("llm_output_token_budget_mode")
                    if llm_metadata is not None
                    else None
                ),
                "llm_output_token_budget": (
                    req.llm_output_token_budget.model_dump()
                    if req.llm_output_token_budget is not None
                    else None
                ),
            },
        )

        return result

    except Exception:
        if not request_counted:
            metrics.inc_request(method=method, subsystem=METRICS_SUBSYSTEM)
        metrics.inc_error(subsystem=METRICS_SUBSYSTEM)
        logger.exception(
            "select_projects_failed",
            extra={
                "event": "select_projects_failed",
                "subsystem": METRICS_SUBSYSTEM,
                "job_title": req.context.title,
                "method": method,
                "requested_llm_max_output_tokens": req.llm_max_output_tokens,
            },
        )
        raise
