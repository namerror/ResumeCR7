from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import httpx

from app.config import settings
from app.llm_provider import resolve_llm_cache_identity
from app.resume_evidence.models import ExperienceRecord, ProjectRecord
from app.resume_generation.cache import ResumeGenerationStageCache
from app.resume_generation.models import (
    ExperienceBulletPointResult,
    JobFocusResult,
    JobTarget,
    ProjectBulletPointResult,
    ResumeGenerationConfig,
)
from app.resume_generation.selection import (
    _cached_post_json_async,
    _cached_post_json,
    _exclude_none,
    open_async_stage_client,
    open_stage_client,
)
from app.resume_generation.token_usage import ResumeGenerationTokenUsageMonitor, TokenUsage


@dataclass
class _ProjectBulletTaskResult:
    result: ProjectBulletPointResult
    stage_response_records: list[dict[str, Any]]


@dataclass
class _ExperienceBulletTaskResult:
    result: ExperienceBulletPointResult
    stage_response_records: list[dict[str, Any]]


@dataclass
class ResumeSectionBulletPointResults:
    project_bullet_points: list[ProjectBulletPointResult]
    experience_bullet_points: list[ExperienceBulletPointResult]


def _effective_bullet_count_range(payload: dict[str, Any]) -> tuple[int, int]:
    count_range = payload.get("bullet_count_range")
    if isinstance(count_range, dict):
        min_count = count_range.get("min")
        max_count = count_range.get("max")
        if isinstance(min_count, int) and isinstance(max_count, int):
            return min_count, max_count

    default_count = settings.BULLETPOINTS_DEFAULT_COUNT
    return default_count, default_count


def _bullet_count_matches_request(
    response_data: dict[str, Any],
    *,
    payload: dict[str, Any],
) -> bool:
    bullet_points = response_data.get("bullet_points")
    if not isinstance(bullet_points, list):
        return False

    min_count, max_count = _effective_bullet_count_range(payload)
    return min_count <= len(bullet_points) <= max_count


def _bullet_dev_mode(payload: dict[str, Any]) -> bool:
    return bool(payload.get("dev_mode", settings.DEV_MODE))


def _bullet_cache_payload(
    payload: dict[str, Any],
    *,
    evidence_type: str,
    config_path: Path | str | None = None,
) -> dict[str, Any]:
    evidence_payload = payload.get(evidence_type)
    return {
        "context": payload.get("context"),
        "evidence_type": evidence_type,
        evidence_type: evidence_payload,
        "llm_model": payload.get("llm_model", settings.BULLETPOINTS_LLM_MODEL),
        "llm_provider": _bullet_llm_cache_identity(payload, config_path=config_path),
    }


def _bullet_llm_cache_identity(
    payload: dict[str, Any],
    *,
    config_path: Path | str | None = None,
) -> dict[str, Any]:
    return resolve_llm_cache_identity(
        stage="bulletpoints_generation",
        requested_model=_string_or_none(payload.get("llm_model")),
        default_openai_model=settings.BULLETPOINTS_LLM_MODEL,
        config_path=config_path,
    )


def _string_or_none(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _bullet_fetch_payload(payload: dict[str, Any]) -> dict[str, Any]:
    fetch_payload = dict(payload)
    fetch_payload["dev_mode"] = True
    return fetch_payload


def _shape_bullet_response(
    response_data: dict[str, Any],
    *,
    payload: dict[str, Any],
) -> dict[str, Any]:
    shaped = {"bullet_points": response_data.get("bullet_points", [])}
    if _bullet_dev_mode(payload):
        details = response_data.get("details")
        if details is not None:
            shaped["details"] = details
    return shaped


def _resume_section_bullet_cache_payload(
    payload: dict[str, Any],
    *,
    config_path: Path | str | None = None,
) -> dict[str, Any]:
    return {
        "strategy": "section_batch",
        "context": payload.get("context"),
        "projects": payload.get("projects"),
        "experiences": payload.get("experiences"),
        "project_bullet_count_range": payload.get("project_bullet_count_range"),
        "experience_bullet_count_range": payload.get("experience_bullet_count_range"),
        "llm_model": payload.get("llm_model", settings.BULLETPOINTS_LLM_MODEL),
        "llm_provider": _bullet_llm_cache_identity(payload, config_path=config_path),
    }


def _resume_section_bullet_fetch_payload(payload: dict[str, Any]) -> dict[str, Any]:
    fetch_payload = dict(payload)
    fetch_payload["dev_mode"] = True
    return fetch_payload


def _section_bullet_counts_match_request(
    response_data: dict[str, Any],
    *,
    payload: dict[str, Any],
) -> bool:
    project_results = response_data.get("project_bullet_points")
    experience_results = response_data.get("experience_bullet_points")
    if not isinstance(project_results, list) or not isinstance(experience_results, list):
        return False

    project_ids = [
        project.get("id")
        for project in payload.get("projects", [])
        if isinstance(project, dict)
    ]
    experience_ids = [
        experience.get("id")
        for experience in payload.get("experiences", [])
        if isinstance(experience, dict)
    ]
    if not _section_records_match_request(
        project_results,
        id_field="project_id",
        expected_ids=project_ids,
        count_range=_effective_bullet_count_range(
            {"bullet_count_range": payload.get("project_bullet_count_range")}
        ),
    ):
        return False
    return _section_records_match_request(
        experience_results,
        id_field="experience_id",
        expected_ids=experience_ids,
        count_range=_effective_bullet_count_range(
            {"bullet_count_range": payload.get("experience_bullet_count_range")}
        ),
    )


def _section_records_match_request(
    records: list[Any],
    *,
    id_field: str,
    expected_ids: list[Any],
    count_range: tuple[int, int],
) -> bool:
    min_count, max_count = count_range
    if len(records) != len(expected_ids):
        return False
    expected_id_set = set(expected_ids)
    seen_ids: set[str] = set()
    for record in records:
        if not isinstance(record, dict):
            return False
        record_id = record.get(id_field)
        bullet_points = record.get("bullet_points")
        if not isinstance(record_id, str) or record_id not in expected_id_set:
            return False
        if record_id in seen_ids:
            return False
        if not isinstance(bullet_points, list):
            return False
        if len(bullet_points) < min_count or len(bullet_points) > max_count:
            return False
        seen_ids.add(record_id)
    return seen_ids == expected_id_set


def _shape_resume_section_bullet_response(
    response_data: dict[str, Any],
    *,
    payload: dict[str, Any],
) -> dict[str, Any]:
    shaped = {
        "project_bullet_points": response_data.get("project_bullet_points", []),
        "experience_bullet_points": response_data.get("experience_bullet_points", []),
    }
    if _bullet_dev_mode(payload):
        details = response_data.get("details")
        if details is not None:
            shaped["details"] = details
    return shaped


def _resume_section_bullet_payload(
    *,
    selected_projects: Iterable[ProjectRecord],
    experience: Iterable[ExperienceRecord],
    config: ResumeGenerationConfig,
    job_target: JobTarget,
    job_focus: JobFocusResult | None,
) -> dict[str, Any]:
    project_config = _exclude_none(config.project_bullet_point_generation)
    experience_config = _exclude_none(config.experience_bullet_point_generation)
    context_payload: dict[str, Any] = {"title": job_target.title}
    if job_focus is not None:
        context_payload["job_focus"] = job_focus.model_dump()
    else:
        context_payload["description"] = job_target.description

    payload: dict[str, Any] = {
        "context": context_payload,
        "projects": [project.model_dump() for project in selected_projects],
        "experiences": [
            item.model_dump()
            for item in experience
            if item.active
        ],
    }
    if "bullet_count_range" in project_config:
        payload["project_bullet_count_range"] = project_config["bullet_count_range"]
    if "bullet_count_range" in experience_config:
        payload["experience_bullet_count_range"] = experience_config[
            "bullet_count_range"
        ]

    for key in (
        "dev_mode",
        "llm_model",
        "llm_max_output_tokens",
        "llm_output_token_budget",
    ):
        if key in project_config:
            payload[key] = project_config[key]

    return payload


def _section_results_from_response(
    response: dict[str, Any],
) -> ResumeSectionBulletPointResults:
    return ResumeSectionBulletPointResults(
        project_bullet_points=[
            ProjectBulletPointResult(
                project_id=item["project_id"],
                bullet_points=item["bullet_points"],
                details=response.get("details"),
            )
            for item in response.get("project_bullet_points", [])
            if isinstance(item, dict)
        ],
        experience_bullet_points=[
            ExperienceBulletPointResult(
                experience_id=item["experience_id"],
                bullet_points=item["bullet_points"],
                details=response.get("details"),
            )
            for item in response.get("experience_bullet_points", [])
            if isinstance(item, dict)
        ],
    )


def _token_usage_from_stage_record(record: dict[str, Any]) -> TokenUsage:
    return TokenUsage(
        prompt_tokens=int(record.get("prompt_tokens", 0) or 0),
        completion_tokens=int(record.get("completion_tokens", 0) or 0),
        total_tokens=int(record.get("total_tokens", 0) or 0),
        api_calls=int(record.get("api_calls", 0) or 0),
        latency_ms=float(record.get("latency_ms", 0.0) or 0.0),
    )


def _merge_async_stage_records(
    *,
    records: list[dict[str, Any]],
    token_usage_monitor: ResumeGenerationTokenUsageMonitor | None,
    stage_response_records: list[dict] | None,
) -> None:
    for record in records:
        stage = record.get("stage")
        if isinstance(stage, str) and token_usage_monitor is not None:
            token_usage_monitor.observe(stage, _token_usage_from_stage_record(record))
        if stage_response_records is not None:
            stage_response_records.append(record)


async def _gather_bullet_tasks_cancel_on_error(*awaitables: Any) -> list[Any]:
    tasks = [asyncio.create_task(awaitable) for awaitable in awaitables]
    try:
        done, pending = await asyncio.wait(
            tasks,
            return_when=asyncio.FIRST_EXCEPTION,
        )
        for task in done:
            error = task.exception()
            if error is not None:
                for pending_task in pending:
                    pending_task.cancel()
                if pending:
                    await asyncio.gather(*pending, return_exceptions=True)
                raise error
        if pending:
            await asyncio.gather(*pending)
        return [task.result() for task in tasks]
    except BaseException:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise


def generate_resume_section_bullet_points(
    *,
    selected_projects: Iterable[ProjectRecord],
    experience: Iterable[ExperienceRecord],
    config: ResumeGenerationConfig,
    job_target: JobTarget,
    job_focus: JobFocusResult | None = None,
    cache: ResumeGenerationStageCache | None = None,
    token_usage_monitor: ResumeGenerationTokenUsageMonitor | None = None,
    stage_response_records: list[dict] | None = None,
    config_path: Path | str | None = None,
) -> ResumeSectionBulletPointResults:
    payload = _resume_section_bullet_payload(
        selected_projects=selected_projects,
        experience=experience,
        config=config,
        job_target=job_target,
        job_focus=job_focus,
    )
    if not payload["projects"] and not payload["experiences"]:
        return ResumeSectionBulletPointResults(
            project_bullet_points=[],
            experience_bullet_points=[],
        )
    with open_stage_client(config, httpx.Client) as client:
        response = _cached_post_json(
            cache=cache,
            stage="resume_section_bullet_points",
            client=client,
            endpoint="/generate-resume-section-bulletpoints",
            payload=payload,
            cache_payload=_resume_section_bullet_cache_payload(
                payload,
                config_path=config_path,
            ),
            fetch_payload=_resume_section_bullet_fetch_payload(payload),
            should_use_cached=lambda data, request_payload=payload: (
                _section_bullet_counts_match_request(
                    data,
                    payload=request_payload,
                )
            ),
            token_usage_monitor=token_usage_monitor,
            stage_response_records=stage_response_records,
        )
        if cache is not None:
            response = _shape_resume_section_bullet_response(response, payload=payload)
        return _section_results_from_response(response)


async def generate_resume_section_bullet_points_async(
    *,
    selected_projects: Iterable[ProjectRecord],
    experience: Iterable[ExperienceRecord],
    config: ResumeGenerationConfig,
    job_target: JobTarget,
    job_focus: JobFocusResult | None = None,
    cache: ResumeGenerationStageCache | None = None,
    token_usage_monitor: ResumeGenerationTokenUsageMonitor | None = None,
    stage_response_records: list[dict] | None = None,
    semaphore: asyncio.Semaphore | None = None,
    config_path: Path | str | None = None,
) -> ResumeSectionBulletPointResults:
    payload = _resume_section_bullet_payload(
        selected_projects=selected_projects,
        experience=experience,
        config=config,
        job_target=job_target,
        job_focus=job_focus,
    )
    if not payload["projects"] and not payload["experiences"]:
        return ResumeSectionBulletPointResults(
            project_bullet_points=[],
            experience_bullet_points=[],
        )
    async with open_async_stage_client(config, httpx.AsyncClient) as client:
        if semaphore is None:
            response = await _cached_post_json_async(
                cache=cache,
                stage="resume_section_bullet_points",
                client=client,
                endpoint="/generate-resume-section-bulletpoints",
                payload=payload,
                cache_payload=_resume_section_bullet_cache_payload(
                    payload,
                    config_path=config_path,
                ),
                fetch_payload=_resume_section_bullet_fetch_payload(payload),
                should_use_cached=lambda data, request_payload=payload: (
                    _section_bullet_counts_match_request(
                        data,
                        payload=request_payload,
                    )
                ),
                token_usage_monitor=token_usage_monitor,
                stage_response_records=stage_response_records,
            )
        else:
            async with semaphore:
                response = await _cached_post_json_async(
                    cache=cache,
                    stage="resume_section_bullet_points",
                    client=client,
                    endpoint="/generate-resume-section-bulletpoints",
                    payload=payload,
                    cache_payload=_resume_section_bullet_cache_payload(
                        payload,
                        config_path=config_path,
                    ),
                    fetch_payload=_resume_section_bullet_fetch_payload(payload),
                    should_use_cached=lambda data, request_payload=payload: (
                        _section_bullet_counts_match_request(
                            data,
                            payload=request_payload,
                        )
                    ),
                    token_usage_monitor=token_usage_monitor,
                    stage_response_records=stage_response_records,
                )
        if cache is not None:
            response = _shape_resume_section_bullet_response(response, payload=payload)
        return _section_results_from_response(response)


def generate_project_bullet_points(
    *,
    selected_projects: Iterable[ProjectRecord],
    config: ResumeGenerationConfig,
    job_target: JobTarget,
    job_focus: JobFocusResult | None = None,
    cache: ResumeGenerationStageCache | None = None,
    token_usage_monitor: ResumeGenerationTokenUsageMonitor | None = None,
    stage_response_records: list[dict] | None = None,
    config_path: Path | str | None = None,
) -> list[ProjectBulletPointResult]:
    bullet_config = _exclude_none(config.project_bullet_point_generation)

    results: list[ProjectBulletPointResult] = []
    with open_stage_client(config, httpx.Client) as client:
        for project in selected_projects:
            context_payload: dict[str, Any] = {"title": job_target.title}
            if job_focus is not None:
                context_payload["job_focus"] = job_focus.model_dump()
            else:
                context_payload["description"] = job_target.description
            payload = {
                "context": context_payload,
                "project": project.model_dump(),
                **bullet_config,
            }
            response = _cached_post_json(
                cache=cache,
                stage="project_bullet_points",
                client=client,
                endpoint="/generate-bulletpoints",
                payload=payload,
                cache_payload=_bullet_cache_payload(
                    payload,
                    evidence_type="project",
                    config_path=config_path,
                ),
                fetch_payload=_bullet_fetch_payload(payload),
                namespace=project.id,
                should_use_cached=lambda data, request_payload=payload: (
                    _bullet_count_matches_request(data, payload=request_payload)
                ),
                token_usage_monitor=token_usage_monitor,
                stage_response_records=stage_response_records,
            )
            if cache is not None:
                response = _shape_bullet_response(response, payload=payload)
            results.append(
                ProjectBulletPointResult(
                    project_id=project.id,
                    bullet_points=response["bullet_points"],
                    details=response.get("details"),
                )
            )

    return results


async def generate_project_bullet_points_async(
    *,
    selected_projects: Iterable[ProjectRecord],
    config: ResumeGenerationConfig,
    job_target: JobTarget,
    job_focus: JobFocusResult | None = None,
    cache: ResumeGenerationStageCache | None = None,
    token_usage_monitor: ResumeGenerationTokenUsageMonitor | None = None,
    stage_response_records: list[dict] | None = None,
    semaphore: asyncio.Semaphore | None = None,
    llm_semaphore: asyncio.Semaphore | None = None,
    config_path: Path | str | None = None,
) -> list[ProjectBulletPointResult]:
    bullet_config = _exclude_none(config.project_bullet_point_generation)
    projects = list(selected_projects)
    if not projects:
        return []
    request_semaphore = semaphore or asyncio.Semaphore(
        config.concurrency.bullet_point_requests
    )

    async def fetch_project(
        client: httpx.AsyncClient,
        project: ProjectRecord,
    ) -> _ProjectBulletTaskResult:
        async with request_semaphore:
            if llm_semaphore is not None and llm_semaphore is not request_semaphore:
                async with llm_semaphore:
                    return await _fetch_project_without_limit(client, project)
            return await _fetch_project_without_limit(client, project)

    async def _fetch_project_without_limit(
        client: httpx.AsyncClient,
        project: ProjectRecord,
    ) -> _ProjectBulletTaskResult:
        context_payload: dict[str, Any] = {"title": job_target.title}
        if job_focus is not None:
            context_payload["job_focus"] = job_focus.model_dump()
        else:
            context_payload["description"] = job_target.description
        payload = {
            "context": context_payload,
            "project": project.model_dump(),
            **bullet_config,
        }
        local_stage_records: list[dict[str, Any]] = []
        response = await _cached_post_json_async(
            cache=cache,
            stage="project_bullet_points",
            client=client,
            endpoint="/generate-bulletpoints",
            payload=payload,
            cache_payload=_bullet_cache_payload(
                payload,
                evidence_type="project",
                config_path=config_path,
            ),
            fetch_payload=_bullet_fetch_payload(payload),
            namespace=project.id,
            should_use_cached=lambda data, request_payload=payload: (
                _bullet_count_matches_request(data, payload=request_payload)
            ),
            token_usage_monitor=None,
            stage_response_records=local_stage_records,
        )
        if cache is not None:
            response = _shape_bullet_response(response, payload=payload)
        return _ProjectBulletTaskResult(
            result=ProjectBulletPointResult(
                project_id=project.id,
                bullet_points=response["bullet_points"],
                details=response.get("details"),
            ),
            stage_response_records=local_stage_records,
        )

    async with open_async_stage_client(config, httpx.AsyncClient) as client:
        task_results = await _gather_bullet_tasks_cancel_on_error(
            *(fetch_project(client, project) for project in projects)
        )

    results: list[ProjectBulletPointResult] = []
    for task_result in task_results:
        results.append(task_result.result)
        _merge_async_stage_records(
            records=task_result.stage_response_records,
            token_usage_monitor=token_usage_monitor,
            stage_response_records=stage_response_records,
        )

    return results


def generate_experience_bullet_points(
    *,
    experience: Iterable[ExperienceRecord],
    config: ResumeGenerationConfig,
    job_target: JobTarget,
    job_focus: JobFocusResult | None = None,
    cache: ResumeGenerationStageCache | None = None,
    token_usage_monitor: ResumeGenerationTokenUsageMonitor | None = None,
    stage_response_records: list[dict] | None = None,
    config_path: Path | str | None = None,
) -> list[ExperienceBulletPointResult]:
    bullet_config = _exclude_none(config.experience_bullet_point_generation)

    results: list[ExperienceBulletPointResult] = []
    with open_stage_client(config, httpx.Client) as client:
        for item in experience:
            if not item.active:
                continue
            context_payload: dict[str, Any] = {"title": job_target.title}
            if job_focus is not None:
                context_payload["job_focus"] = job_focus.model_dump()
            else:
                context_payload["description"] = job_target.description
            payload = {
                "context": context_payload,
                "experience": item.model_dump(),
                **bullet_config,
            }
            response = _cached_post_json(
                cache=cache,
                stage="experience_bullet_points",
                client=client,
                endpoint="/generate-bulletpoints",
                payload=payload,
                cache_payload=_bullet_cache_payload(
                    payload,
                    evidence_type="experience",
                    config_path=config_path,
                ),
                fetch_payload=_bullet_fetch_payload(payload),
                namespace=item.id,
                should_use_cached=lambda data, request_payload=payload: (
                    _bullet_count_matches_request(data, payload=request_payload)
                ),
                token_usage_monitor=token_usage_monitor,
                stage_response_records=stage_response_records,
            )
            if cache is not None:
                response = _shape_bullet_response(response, payload=payload)
            results.append(
                ExperienceBulletPointResult(
                    experience_id=item.id,
                    bullet_points=response["bullet_points"],
                    details=response.get("details"),
                )
            )

    return results


async def generate_experience_bullet_points_async(
    *,
    experience: Iterable[ExperienceRecord],
    config: ResumeGenerationConfig,
    job_target: JobTarget,
    job_focus: JobFocusResult | None = None,
    cache: ResumeGenerationStageCache | None = None,
    token_usage_monitor: ResumeGenerationTokenUsageMonitor | None = None,
    stage_response_records: list[dict] | None = None,
    semaphore: asyncio.Semaphore | None = None,
    llm_semaphore: asyncio.Semaphore | None = None,
    config_path: Path | str | None = None,
) -> list[ExperienceBulletPointResult]:
    bullet_config = _exclude_none(config.experience_bullet_point_generation)
    active_experience = [item for item in experience if item.active]
    if not active_experience:
        return []
    request_semaphore = semaphore or asyncio.Semaphore(
        config.concurrency.bullet_point_requests
    )

    async def fetch_experience(
        client: httpx.AsyncClient,
        item: ExperienceRecord,
    ) -> _ExperienceBulletTaskResult:
        async with request_semaphore:
            if llm_semaphore is not None and llm_semaphore is not request_semaphore:
                async with llm_semaphore:
                    return await _fetch_experience_without_limit(client, item)
            return await _fetch_experience_without_limit(client, item)

    async def _fetch_experience_without_limit(
        client: httpx.AsyncClient,
        item: ExperienceRecord,
    ) -> _ExperienceBulletTaskResult:
        context_payload: dict[str, Any] = {"title": job_target.title}
        if job_focus is not None:
            context_payload["job_focus"] = job_focus.model_dump()
        else:
            context_payload["description"] = job_target.description
        payload = {
            "context": context_payload,
            "experience": item.model_dump(),
            **bullet_config,
        }
        local_stage_records: list[dict[str, Any]] = []
        response = await _cached_post_json_async(
            cache=cache,
            stage="experience_bullet_points",
            client=client,
            endpoint="/generate-bulletpoints",
            payload=payload,
            cache_payload=_bullet_cache_payload(
                payload,
                evidence_type="experience",
                config_path=config_path,
            ),
            fetch_payload=_bullet_fetch_payload(payload),
            namespace=item.id,
            should_use_cached=lambda data, request_payload=payload: (
                _bullet_count_matches_request(data, payload=request_payload)
            ),
            token_usage_monitor=None,
            stage_response_records=local_stage_records,
        )
        if cache is not None:
            response = _shape_bullet_response(response, payload=payload)
        return _ExperienceBulletTaskResult(
            result=ExperienceBulletPointResult(
                experience_id=item.id,
                bullet_points=response["bullet_points"],
                details=response.get("details"),
            ),
            stage_response_records=local_stage_records,
        )

    async with open_async_stage_client(config, httpx.AsyncClient) as client:
        task_results = await _gather_bullet_tasks_cancel_on_error(
            *(fetch_experience(client, item) for item in active_experience)
        )

    results: list[ExperienceBulletPointResult] = []
    for task_result in task_results:
        results.append(task_result.result)
        _merge_async_stage_records(
            records=task_result.stage_response_records,
            token_usage_monitor=token_usage_monitor,
            stage_response_records=stage_response_records,
        )

    return results
