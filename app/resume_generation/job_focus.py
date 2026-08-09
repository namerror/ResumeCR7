from __future__ import annotations

import asyncio
from typing import Any

import httpx

from app.config import settings
from app.job_focus_generation.models import JobFocusResponse
from app.resume_generation.cache import ResumeGenerationStageCache
from app.resume_generation.models import JobFocusResult, JobTarget, ResumeGenerationConfig
from app.resume_generation.selection import (
    _cached_post_json_async,
    _cached_post_json,
    _exclude_none,
    open_async_stage_client,
    open_stage_client,
)
from app.resume_generation.token_usage import ResumeGenerationTokenUsageMonitor

JOB_FOCUS_PROMPT_SCHEMA_VERSION = 1


def _job_focus_dev_mode(payload: dict[str, Any]) -> bool:
    return bool(payload.get("dev_mode", settings.DEV_MODE))


def _job_focus_cache_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "prompt_schema_version": JOB_FOCUS_PROMPT_SCHEMA_VERSION,
        "title": payload.get("title"),
        "description": payload.get("description"),
        "llm_model": payload.get("llm_model", settings.JOB_FOCUS_LLM_MODEL),
    }


def _job_focus_fetch_payload(payload: dict[str, Any]) -> dict[str, Any]:
    fetch_payload = dict(payload)
    fetch_payload["dev_mode"] = True
    return fetch_payload


def _shape_job_focus_response(
    response_data: dict[str, Any],
    *,
    payload: dict[str, Any],
) -> dict[str, Any]:
    shaped: dict[str, Any] = {"job_focus": response_data.get("job_focus")}
    if _job_focus_dev_mode(payload):
        details = response_data.get("details")
        if details is not None:
            shaped["details"] = details
    return shaped


def derive_job_focus(
    *,
    config: ResumeGenerationConfig,
    job_target: JobTarget,
    cache: ResumeGenerationStageCache | None = None,
    token_usage_monitor: ResumeGenerationTokenUsageMonitor | None = None,
    stage_response_records: list[dict[str, Any]] | None = None,
) -> JobFocusResult:
    focus_config = _exclude_none(config.job_focus_generation)
    payload = {
        "title": job_target.title,
        "description": job_target.description,
        **focus_config,
    }
    payload = {key: value for key, value in payload.items() if value is not None}

    with open_stage_client(config, httpx.Client) as client:
        response = _cached_post_json(
            cache=cache,
            stage="job_focus_generation",
            client=client,
            endpoint="/derive-job-focus",
            payload=payload,
            cache_payload=_job_focus_cache_payload(payload),
            fetch_payload=_job_focus_fetch_payload(payload),
            token_usage_monitor=token_usage_monitor,
            stage_response_records=stage_response_records,
        )

    if cache is not None:
        response = _shape_job_focus_response(response, payload=payload)

    return JobFocusResponse.model_validate(response).job_focus


async def derive_job_focus_async(
    *,
    config: ResumeGenerationConfig,
    job_target: JobTarget,
    cache: ResumeGenerationStageCache | None = None,
    stage_response_records: list[dict[str, Any]] | None = None,
    semaphore: asyncio.Semaphore | None = None,
) -> JobFocusResult:
    focus_config = _exclude_none(config.job_focus_generation)
    payload = {
        "title": job_target.title,
        "description": job_target.description,
        **focus_config,
    }
    payload = {key: value for key, value in payload.items() if value is not None}

    async with open_async_stage_client(config, httpx.AsyncClient) as client:
        if semaphore is None:
            response = await _cached_post_json_async(
                cache=cache,
                stage="job_focus_generation",
                client=client,
                endpoint="/derive-job-focus",
                payload=payload,
                cache_payload=_job_focus_cache_payload(payload),
                fetch_payload=_job_focus_fetch_payload(payload),
                token_usage_monitor=None,
                stage_response_records=stage_response_records,
            )
        else:
            async with semaphore:
                response = await _cached_post_json_async(
                    cache=cache,
                    stage="job_focus_generation",
                    client=client,
                    endpoint="/derive-job-focus",
                    payload=payload,
                    cache_payload=_job_focus_cache_payload(payload),
                    fetch_payload=_job_focus_fetch_payload(payload),
                    token_usage_monitor=None,
                    stage_response_records=stage_response_records,
                )

    if cache is not None:
        response = _shape_job_focus_response(response, payload=payload)

    return JobFocusResponse.model_validate(response).job_focus
