# app/skill_selection/selector.py
from __future__ import annotations
import logging
import time

from app.config import settings
from app.metrics import metrics
from app.skill_selection.models import SkillSelectRequest, SkillSelectResponse
from app.skill_selection.scoring.baseline import baseline_select_skills
from app.skill_selection.scoring.embeddings import embedding_select_skills
from app.skill_selection.scoring.llm import llm_select_skills
from app.skill_selection.baseline_filter import select_with_baseline_filter

logger = logging.getLogger("skill_selector")


def _focus_job_text(job_text: str | None, job_focus: object | None) -> str | None:
    if job_focus is None:
        return job_text

    focus_parts: list[str] = []
    for field_name in (
        "summary",
        "required_skills",
        "preferred_skills",
        "responsibilities",
        "domain_emphasis",
    ):
        value = getattr(job_focus, field_name, None)
        if isinstance(value, str):
            focus_parts.append(value)
        elif isinstance(value, list):
            focus_parts.extend(item for item in value if isinstance(item, str))

    focus_text = "\n".join(part.strip() for part in focus_parts if part.strip())
    if not focus_text:
        return job_text
    if job_text:
        return f"{focus_text}\n{job_text}"
    return focus_text


def _effective_method(requested_method: str, meta: dict | None) -> str:
    """Return the method that produced the response after fallback handling."""
    if not isinstance(meta, dict):
        return requested_method

    fallback_method = meta.get("_fallback_method")
    if isinstance(fallback_method, str) and fallback_method:
        return fallback_method

    llm_meta = meta.get("_llm")
    if isinstance(llm_meta, dict) and llm_meta.get("fallback") == "baseline":
        return "baseline"

    return requested_method


def _extract_total_tokens(meta: dict | None) -> int:
    if not isinstance(meta, dict):
        return 0

    llm_meta = meta.get("_llm")
    if not isinstance(llm_meta, dict):
        return 0

    try:
        return int(llm_meta.get("total_tokens", 0) or 0)
    except (TypeError, ValueError):
        return 0


def _call_scorer(
    *,
    method: str,
    job_role: str,
    job_text: str | None,
    job_focus: object | None,
    technology: list[str],
    programming: list[str],
    concepts: list[str],
    top_n: int | None,
    dev_mode: bool,
    llm_model: str | None,
    llm_max_output_tokens: int | None,
) -> tuple[dict, dict | None]:
    if method == "baseline":
        return baseline_select_skills(
            job_role=job_role,
            job_text=_focus_job_text(job_text, job_focus),
            technology=technology,
            programming=programming,
            concepts=concepts,
            top_n=top_n,
            dev_mode=dev_mode,
        )
    if method == "embeddings":
        return embedding_select_skills(
            job_role=job_role,
            job_text=_focus_job_text(job_text, job_focus),
            technology=technology,
            programming=programming,
            concepts=concepts,
            top_n=top_n,
            dev_mode=dev_mode,
        )
    if method == "llm":
        return llm_select_skills(
            job_role=job_role,
            job_text=job_text,
            job_focus=job_focus,
            technology=technology,
            programming=programming,
            concepts=concepts,
            top_n=top_n,
            dev_mode=True,
            llm_model=llm_model,
            llm_max_output_tokens=llm_max_output_tokens,
        )

    raise ValueError(f"Unsupported skill selection method: {method}")


def select_skills_service(req: SkillSelectRequest) -> SkillSelectResponse:
    method = req.method.lower() if req.method is not None else settings.SKILL_METHOD.lower()
    top_n = req.top_n if req.top_n is not None else settings.SKILL_TOP_N
    dev_mode = req.dev_mode if req.dev_mode is not None else settings.DEV_MODE
    baseline_filter = (
        req.baseline_filter if req.baseline_filter is not None else settings.SKILL_BASELINE_FILTER
    )
    if req.llm_max_output_tokens is not None and req.llm_max_output_tokens <= 0:
        raise ValueError("llm_max_output_tokens must be greater than 0")

    start = time.perf_counter()
    request_counted = False

    try:
        if baseline_filter and method in {"embeddings", "llm"}:
            selected, meta = select_with_baseline_filter(
                method=method,
                req=req,
                top_n=top_n,
            )
        else:
            selected, meta = _call_scorer(
                method=method,
                job_role=req.job_role,
                job_text=req.job_text,
                job_focus=req.job_focus,
                technology=req.technology,
                programming=req.programming,
                concepts=req.concepts,
                top_n=top_n,
                dev_mode=dev_mode,
                llm_model=req.llm_model,
                llm_max_output_tokens=req.llm_max_output_tokens,
            )

        latency_ms = (time.perf_counter() - start) * 1000.0
        effective_method = _effective_method(method, meta)
        metrics.inc_request(method=effective_method)
        request_counted = True
        metrics.observe_tokens(_extract_total_tokens(meta))
        metrics.observe_latency_ms(latency_ms)

        logger.info(
            "select_skills",
            extra={
                "event": "select_skills",
                "subsystem": "skill_selection",
                "role": req.job_role,
                "method": effective_method,
                "requested_method": method,
                "baseline_filter": bool(baseline_filter),
                "top_n": top_n,
                "llm_max_output_tokens": req.llm_max_output_tokens,
                "latency_ms": round(latency_ms, 3),
                "category_counts": {k: len(v) for k, v in selected.items()},
            },
        )

        return SkillSelectResponse(
            technology=selected.get("technology", []),
            programming=selected.get("programming", []),
            concepts=selected.get("concepts", []),
            details=meta if dev_mode else None,
        )

    except Exception:
        if not request_counted:
            metrics.inc_request(method=method)
        metrics.inc_error()
        logger.exception(
            "select_skills_failed",
            extra={
                "event": "select_skills_failed",
                "subsystem": "skill_selection",
                "role": req.job_role,
                "method": method,
                "llm_max_output_tokens": req.llm_max_output_tokens,
            },
        )
        raise
