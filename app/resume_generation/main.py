# entry point for resume generation

import argparse
import asyncio
import json
import logging
import os
import re
from pathlib import Path
from typing import Any

from app.config import settings
from app.bulletpoints_generation.metric_guidance import build_metric_opportunity_notes
from app.runtime_data import bootstrap_runtime_data
from app.resume_evidence import (
    EducationFile,
    ExperienceFile,
    ExperienceRecord,
    ProjectRecord,
    UserInfoFile,
    load_registered_evidence,
)
from app.resume_generation.config import (
    load_generation_config,
    load_job_target,
    resolve_generation_config_path,
    resolve_job_target_path,
)
from app.resume_generation.assembly import assemble_intermediate_resume_result
from app.resume_generation.bullet_points import (
    generate_experience_bullet_points_async,
    generate_experience_bullet_points,
    generate_project_bullet_points_async,
    generate_project_bullet_points,
    generate_resume_section_bullet_points,
    generate_resume_section_bullet_points_async,
)
from app.resume_generation.cache import ResumeGenerationStageCache
from app.resume_generation.job_focus import derive_job_focus, derive_job_focus_async
from app.resume_generation.latex import (
    copy_resume_latex_to_user_output,
    write_resume_latex_artifact,
)
from app.resume_generation.models import (
    IntermediateResumeResult,
    JobFocusResult,
    JobTarget,
    ResumeSelectionContext,
)
from app.resume_generation.pdf import copy_resume_pdf_to_user_output, render_latex_pdf
from app.resume_generation.selection import (
    _selection_context_sources,
    generate_project_selection_async,
    generate_selection_context,
    generate_skill_selection_async,
)
from app.resume_generation.status import GenerationStatusReporter, MetricOpportunityNote
from app.resume_generation.tailoring import build_tailoring_audit
from app.resume_generation.token_usage import ResumeGenerationTokenUsageMonitor, TokenUsage

DEFAULT_RESUME_RESULT_ARTIFACT_PATH = settings.resume_result_artifact_path
DEFAULT_RESUME_RUN_MANIFEST_ARTIFACT_PATH = settings.resume_run_manifest_artifact_path
logger = logging.getLogger("resume_generation")
_RESUME_DATE_PATTERN = re.compile(r"^\s*(\d{4})(?:-(\d{1,2})(?:-(\d{1,2}))?)?\s*$")
_RESUME_MONTH_DATE_PATTERN = re.compile(
    r"^\s*([A-Za-z]{3,9})\.?\s+(\d{4})\s*$",
    re.IGNORECASE,
)
_RESUME_CURRENT_DATE_VALUES = {"current", "ongoing", "present"}
_RESUME_MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}


def resolve_resume_result_artifact_path(path: Path | str | None = None) -> Path:
    return Path(path) if path is not None else settings.resume_result_artifact_path


def resolve_resume_run_manifest_artifact_path(path: Path | str | None = None) -> Path:
    return Path(path) if path is not None else settings.resume_run_manifest_artifact_path


def _token_usage_extra(usage: TokenUsage) -> dict[str, int | float]:
    return {
        "prompt_tokens": usage.prompt_tokens,
        "completion_tokens": usage.completion_tokens,
        "total_tokens": usage.total_tokens,
        "api_calls": usage.api_calls,
        "latency_ms": round(usage.latency_ms, 3),
    }


def _report_generation_status(
    reporter: GenerationStatusReporter | None,
    stage_id: str,
    status: str,
    message: str | None = None,
    job_focus: JobFocusResult | None = None,
    metric_notes: list[MetricOpportunityNote] | None = None,
) -> None:
    if reporter is not None:
        if metric_notes is None:
            reporter(stage_id, status, message, job_focus)
        else:
            reporter(stage_id, status, message, job_focus, metric_notes)


def _build_status_metric_notes(
    *,
    projects: list[ProjectRecord],
    experiences: list[ExperienceRecord],
) -> list[MetricOpportunityNote]:
    return [
        MetricOpportunityNote.model_validate(note)
        for note in build_metric_opportunity_notes(
            projects=projects,
            experiences=experiences,
        )
    ]


def _observe_stage_response_records(
    *,
    records: list[dict[str, Any]],
    token_usage_monitor: ResumeGenerationTokenUsageMonitor,
    stage_response_records: list[dict[str, Any]],
) -> None:
    for record in records:
        stage = record.get("stage")
        if isinstance(stage, str):
            token_usage_monitor.observe(
                stage,
                TokenUsage(
                    prompt_tokens=int(record.get("prompt_tokens", 0) or 0),
                    completion_tokens=int(record.get("completion_tokens", 0) or 0),
                    total_tokens=int(record.get("total_tokens", 0) or 0),
                    api_calls=int(record.get("api_calls", 0) or 0),
                    latency_ms=float(record.get("latency_ms", 0.0) or 0.0),
                ),
            )
        stage_response_records.append(record)


async def _gather_resume_generation_tasks(*awaitables: Any) -> list[Any]:
    tasks = [asyncio.create_task(awaitable) for awaitable in awaitables]
    return await _wait_resume_generation_tasks_cancel_on_error(tasks)


async def _wait_resume_generation_tasks_cancel_on_error(
    tasks: list[asyncio.Task[Any]],
) -> list[Any]:
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


def _select_resume_experience(
    experience: ExperienceFile,
    *,
    top_n: int | None,
) -> ExperienceFile:
    active_records = sorted(
        (item for item in experience.experience if item.active),
        key=_experience_order_key,
    )
    if top_n is not None:
        active_records = active_records[:top_n]
    return ExperienceFile(schema_version=experience.schema_version, experience=active_records)


def _experience_order_key(
    item: ExperienceRecord,
) -> tuple[tuple[int, int, int, str], tuple[int, int, int, str]]:
    return (
        _resume_date_desc_key(item.end, none_is_latest=True, missing_parts_latest=True),
        _resume_date_asc_key(item.start, missing_parts_latest=False),
    )


def _resume_date_asc_key(
    value: str,
    *,
    missing_parts_latest: bool,
) -> tuple[int, int, int, str]:
    parsed = _resume_date_parts(
        value,
        missing_parts_latest=missing_parts_latest,
    )
    if parsed is None:
        return (9999, 12, 31, value.strip().lower())
    return (*parsed, "")


def _resume_date_desc_key(
    value: str | None,
    *,
    none_is_latest: bool,
    missing_parts_latest: bool,
) -> tuple[int, int, int, str]:
    if value is None:
        sentinel = 9999 if none_is_latest else -9999
        return (-sentinel, -12, -31, "")

    if none_is_latest and _is_resume_current_date(value):
        return (-9999, -12, -31, "")

    parsed = _resume_date_parts(
        value,
        missing_parts_latest=missing_parts_latest,
    )
    if parsed is None:
        return (0, 0, 0, value.strip().lower())
    year, month, day = parsed
    return (-year, -month, -day, "")


def _resume_date_parts(
    value: str,
    *,
    missing_parts_latest: bool,
) -> tuple[int, int, int] | None:
    match = _RESUME_DATE_PATTERN.match(value)
    if match is not None:
        month_default = 12 if missing_parts_latest else 1
        day_default = 31 if missing_parts_latest else 1
        year, month, day = match.groups()
        return (
            int(year),
            int(month) if month is not None else month_default,
            int(day) if day is not None else day_default,
        )

    month_match = _RESUME_MONTH_DATE_PATTERN.match(value)
    if month_match is None:
        return None

    month_name, year = month_match.groups()
    month = _RESUME_MONTHS.get(month_name.strip(".").lower())
    if month is None:
        return None

    return (
        int(year),
        month,
        31 if missing_parts_latest else 1,
    )


def _is_resume_current_date(value: str) -> bool:
    return value.strip().lower().strip(".") in _RESUME_CURRENT_DATE_VALUES


def write_resume_result_artifact(
    resume_result: IntermediateResumeResult,
    path: Path | str | None = None,
) -> Path:
    artifact_path = resolve_resume_result_artifact_path(path)
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = artifact_path.with_suffix(artifact_path.suffix + ".tmp")
    tmp_path.write_text(
        resume_result.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp_path, artifact_path)
    return artifact_path


def write_resume_run_manifest_artifact(
    manifest: dict[str, Any],
    path: Path | str | None = None,
) -> Path:
    artifact_path = resolve_resume_run_manifest_artifact_path(path)
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = artifact_path.with_suffix(artifact_path.suffix + ".tmp")
    tmp_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp_path, artifact_path)
    return artifact_path


def build_resume_run_manifest(
    *,
    config_path: Path | str,
    job_target_path: Path | str,
    job_target_source: str,
    context: ResumeSelectionContext,
    job_focus: JobFocusResult,
    stage_response_records: list[dict[str, Any]],
    token_usage_monitor: ResumeGenerationTokenUsageMonitor,
    resume_result_artifact_path: Path | str,
    resume_result: IntermediateResumeResult,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "inputs": {
            "config_path": str(config_path),
            "job_target_path": str(job_target_path),
            "job_target_source": job_target_source,
            "job_target": context.job_target.model_dump(mode="json"),
            "evidence_paths": {
                schema_name: str(path)
                for schema_name, path in sorted(context.evidence_paths.items())
            },
        },
        "artifacts": {
            "resume_result": str(resume_result_artifact_path),
        },
        "selection": {
            "skills": context.selected_skills.model_dump(),
            "project_selection": context.project_selection.model_dump(),
            "selected_project_ids": [project.id for project in context.selected_projects],
        },
        "job_focus": job_focus.model_dump(),
        "tailoring_audit": build_tailoring_audit(
            resume_result=resume_result,
            job_focus=job_focus,
        ),
        "stage_responses": stage_response_records,
        "token_usage": token_usage_monitor.summary(),
    }


def run_resume_generation_pipeline(
    *,
    config_path: Path | str | None = None,
    job_target_path: Path | str | None = None,
    job_target_override: JobTarget | None = None,
    evidence_paths: dict[str, Path | str] | None = None,
    resume_result_artifact_path: Path | str | None = None,
    resume_run_manifest_artifact_path: Path | str | None = None,
) -> IntermediateResumeResult:
    resolved_config_path = resolve_generation_config_path(config_path)
    resolved_job_target_path = resolve_job_target_path(job_target_path)
    resolved_result_artifact_path = resolve_resume_result_artifact_path(
        resume_result_artifact_path
    )
    resolved_manifest_artifact_path = resolve_resume_run_manifest_artifact_path(
        resume_run_manifest_artifact_path
    )
    logger.info(
        "resume_generation_pipeline_start",
        extra={
            "event": "resume_generation_pipeline_start",
            "config_path": str(resolved_config_path),
            "job_target_path": str(resolved_job_target_path),
        },
    )
    config = load_generation_config(resolved_config_path)
    job_target_source = "request" if job_target_override is not None else "file"
    job_target = job_target_override
    if job_target is None:
        job_target = load_job_target(resolved_job_target_path)
    loaded_evidence = load_registered_evidence(evidence_paths)
    cache = ResumeGenerationStageCache.from_config(
        config.cache,
        config_path=resolved_config_path,
    )
    token_usage_monitor = ResumeGenerationTokenUsageMonitor()
    stage_response_records: list[dict[str, Any]] = []

    _user_info = loaded_evidence.get("user")
    if not isinstance(_user_info, UserInfoFile):
        raise TypeError("Loaded evidence did not include a valid user info file")

    _education = loaded_evidence.get("education")
    if not isinstance(_education, EducationFile):
        raise TypeError("Loaded evidence did not include a valid education file")

    _experience = loaded_evidence.get("experience")
    if not isinstance(_experience, ExperienceFile):
        raise TypeError("Loaded evidence did not include a valid experience file")

    logger.info(
        "resume_generation_stage_start",
        extra={"event": "resume_generation_stage_start", "stage": "job_focus_generation"},
    )
    job_focus = derive_job_focus(
        config=config,
        job_target=job_target,
        cache=cache,
        token_usage_monitor=token_usage_monitor,
        stage_response_records=stage_response_records,
    )
    logger.info(
        "resume_generation_stage_complete",
        extra={
            "event": "resume_generation_stage_complete",
            "stage": "job_focus_generation",
            **_token_usage_extra(
                token_usage_monitor.stage_total("job_focus_generation")
            ),
        },
    )

    logger.info(
        "resume_generation_stage_start",
        extra={"event": "resume_generation_stage_start", "stage": "selection"},
    )
    # selection context includes skills and projects ranked by relevance to the job target.
    context = generate_selection_context(
        loaded_evidence=loaded_evidence,
        config=config,
        job_target=job_target,
        config_path=resolved_config_path,
        job_target_path=resolved_job_target_path,
        evidence_paths=evidence_paths,
        cache=cache,
        token_usage_monitor=token_usage_monitor,
        stage_response_records=stage_response_records,
        job_focus=job_focus,
    )
    logger.info(
        "resume_generation_stage_complete",
        extra={
            "event": "resume_generation_stage_complete",
            "stage": "selection",
            "selected_project_count": len(context.selected_projects),
            **_token_usage_extra(
                token_usage_monitor.combined_total(
                    ("skill_selection", "project_selection")
                )
            ),
        },
    )

    # TODO: other info like publications etc. will come in the future

    # TODO: optionally re-rank project skills with LLM (not the skills themselves), this is ranked per project, priortizing skills that are more relevant to the job target. This should be done with a separate reranking API instead of the one used for regular skill ranking

    selected_experience = _select_resume_experience(
        _experience,
        top_n=config.experience_selection.top_n,
    )

    if config.bullet_point_generation_strategy == "section_batch":
        logger.info(
            "resume_generation_stage_start",
            extra={
                "event": "resume_generation_stage_start",
                "stage": "resume_section_bullet_points",
                "project_count": len(context.selected_projects),
                "experience_count": len(selected_experience.experience),
            },
        )
        section_bullet_points = generate_resume_section_bullet_points(
            selected_projects=context.selected_projects,
            experience=selected_experience.experience,
            config=config,
            job_target=job_target,
            job_focus=job_focus,
            cache=cache,
            token_usage_monitor=token_usage_monitor,
            stage_response_records=stage_response_records,
        )
        bullet_points = section_bullet_points.project_bullet_points
        experience_bullet_points = section_bullet_points.experience_bullet_points
        logger.info(
            "resume_generation_stage_complete",
            extra={
                "event": "resume_generation_stage_complete",
                "stage": "resume_section_bullet_points",
                "project_result_count": len(bullet_points),
                "experience_result_count": len(experience_bullet_points),
                **_token_usage_extra(
                    token_usage_monitor.stage_total("resume_section_bullet_points")
                ),
            },
        )
    else:
        logger.info(
            "resume_generation_stage_start",
            extra={
                "event": "resume_generation_stage_start",
                "stage": "project_bullet_points",
                "project_count": len(context.selected_projects),
            },
        )
        bullet_points = generate_project_bullet_points(
            selected_projects=context.selected_projects,
            config=config,
            job_target=job_target,
            job_focus=job_focus,
            cache=cache,
            token_usage_monitor=token_usage_monitor,
            stage_response_records=stage_response_records,
        )
        logger.info(
            "resume_generation_stage_complete",
            extra={
                "event": "resume_generation_stage_complete",
                "stage": "project_bullet_points",
                "result_count": len(bullet_points),
                **_token_usage_extra(
                    token_usage_monitor.stage_total("project_bullet_points")
                ),
            },
        )

        logger.info(
            "resume_generation_stage_start",
            extra={
                "event": "resume_generation_stage_start",
                "stage": "experience_bullet_points",
                "experience_count": len(selected_experience.experience),
            },
        )
        experience_bullet_points = generate_experience_bullet_points(
            experience=selected_experience.experience,
            config=config,
            job_target=job_target,
            job_focus=job_focus,
            cache=cache,
            token_usage_monitor=token_usage_monitor,
            stage_response_records=stage_response_records,
        )
        logger.info(
            "resume_generation_stage_complete",
            extra={
                "event": "resume_generation_stage_complete",
                "stage": "experience_bullet_points",
                "result_count": len(experience_bullet_points),
                **_token_usage_extra(
                    token_usage_monitor.stage_total("experience_bullet_points")
                ),
            },
        )

    # TODO: optionally overall content validation

    logger.info(
        "resume_generation_stage_start",
        extra={"event": "resume_generation_stage_start", "stage": "assembly"},
    )
    resume_result = assemble_intermediate_resume_result(
        user_info=_user_info,
        education=_education,
        experience=selected_experience,
        selection_context=context,
        selected_projects=context.selected_projects,
        project_bullet_points=bullet_points,
        experience_bullet_points=experience_bullet_points,
        job_focus=job_focus,
    )
    logger.info(
        "resume_generation_stage_complete",
        extra={
            "event": "resume_generation_stage_complete",
            "stage": "assembly",
            **_token_usage_extra(TokenUsage()),
        },
    )

    artifact_path = write_resume_result_artifact(
        resume_result,
        resolved_result_artifact_path,
    )
    logger.info(
        "resume_generation_artifact_written",
        extra={
            "event": "resume_generation_artifact_written",
            "path": str(artifact_path),
        },
    )
    manifest = build_resume_run_manifest(
        config_path=resolved_config_path,
        job_target_path=resolved_job_target_path,
        job_target_source=job_target_source,
        context=context,
        job_focus=job_focus,
        stage_response_records=stage_response_records,
        token_usage_monitor=token_usage_monitor,
        resume_result_artifact_path=artifact_path,
        resume_result=resume_result,
    )
    manifest_path = write_resume_run_manifest_artifact(
        manifest,
        resolved_manifest_artifact_path,
    )
    logger.info(
        "resume_generation_artifact_written",
        extra={
            "event": "resume_generation_artifact_written",
            "path": str(manifest_path),
        },
    )

    logger.info(
        "resume_generation_token_usage_summary",
        extra={
            "event": "resume_generation_token_usage_summary",
            **token_usage_monitor.summary(),
        },
    )

    logger.info(
        "resume_generation_pipeline_complete",
        extra={"event": "resume_generation_pipeline_complete"},
    )

    return resume_result


async def run_resume_generation_pipeline_async(
    *,
    config_path: Path | str | None = None,
    job_target_path: Path | str | None = None,
    job_target_override: JobTarget | None = None,
    evidence_paths: dict[str, Path | str] | None = None,
    resume_result_artifact_path: Path | str | None = None,
    resume_run_manifest_artifact_path: Path | str | None = None,
    status_reporter: GenerationStatusReporter | None = None,
) -> IntermediateResumeResult:
    resolved_config_path = resolve_generation_config_path(config_path)
    resolved_job_target_path = resolve_job_target_path(job_target_path)
    resolved_result_artifact_path = resolve_resume_result_artifact_path(
        resume_result_artifact_path
    )
    resolved_manifest_artifact_path = resolve_resume_run_manifest_artifact_path(
        resume_run_manifest_artifact_path
    )
    logger.info(
        "resume_generation_pipeline_start",
        extra={
            "event": "resume_generation_pipeline_start",
            "config_path": str(resolved_config_path),
            "job_target_path": str(resolved_job_target_path),
        },
    )
    config = load_generation_config(resolved_config_path)
    job_target_source = "request" if job_target_override is not None else "file"
    job_target = job_target_override
    if job_target is None:
        job_target = load_job_target(resolved_job_target_path)
    loaded_evidence = load_registered_evidence(evidence_paths)
    cache = ResumeGenerationStageCache.from_config(
        config.cache,
        config_path=resolved_config_path,
    )
    token_usage_monitor = ResumeGenerationTokenUsageMonitor()
    stage_response_records: list[dict[str, Any]] = []

    _user_info = loaded_evidence.get("user")
    if not isinstance(_user_info, UserInfoFile):
        raise TypeError("Loaded evidence did not include a valid user info file")

    _education = loaded_evidence.get("education")
    if not isinstance(_education, EducationFile):
        raise TypeError("Loaded evidence did not include a valid education file")

    _experience = loaded_evidence.get("experience")
    if not isinstance(_experience, ExperienceFile):
        raise TypeError("Loaded evidence did not include a valid experience file")

    logger.info(
        "resume_generation_stage_start",
        extra={"event": "resume_generation_stage_start", "stage": "job_focus_generation"},
    )
    _report_generation_status(
        status_reporter,
        "job_focus_generation",
        "running",
        "Generating job focus",
    )
    (
        context_config_path,
        context_job_target_path,
        context_evidence_paths,
        projects_file,
        skills_file,
    ) = _selection_context_sources(
        loaded_evidence=loaded_evidence,
        config_path=resolved_config_path,
        job_target_path=resolved_job_target_path,
        evidence_paths=evidence_paths,
    )
    llm_semaphore = asyncio.Semaphore(config.concurrency.llm_requests)
    skill_stage_records: list[dict[str, Any]] = []
    project_stage_records: list[dict[str, Any]] = []
    job_focus_stage_records: list[dict[str, Any]] = []
    managed_tasks: list[asyncio.Task[Any]] = []

    job_focus_task = asyncio.create_task(
        derive_job_focus_async(
            config=config,
            job_target=job_target,
            cache=cache,
            stage_response_records=job_focus_stage_records,
            semaphore=llm_semaphore,
        )
    )
    managed_tasks.append(job_focus_task)

    try:
        selected_experience = _select_resume_experience(
            _experience,
            top_n=config.experience_selection.top_n,
        )
        (job_focus,) = await _wait_resume_generation_tasks_cancel_on_error(
            [job_focus_task]
        )
        _report_generation_status(
            status_reporter,
            "job_focus_generation",
            "succeeded",
            "Done",
            job_focus,
        )

        logger.info(
            "resume_generation_stage_start",
            extra={"event": "resume_generation_stage_start", "stage": "selection"},
        )
        _report_generation_status(
            status_reporter,
            "skill_selection",
            "running",
            "Selecting skills",
        )
        _report_generation_status(
            status_reporter,
            "project_selection",
            "running",
            "Selecting projects",
        )
        skill_task = asyncio.create_task(
            generate_skill_selection_async(
                config=config,
                job_target=job_target,
                skills_file=skills_file,
                cache=cache,
                stage_response_records=skill_stage_records,
                semaphore=llm_semaphore,
                job_focus=job_focus,
            )
        )
        project_task = asyncio.create_task(
            generate_project_selection_async(
                config=config,
                job_target=job_target,
                projects_file=projects_file,
                cache=cache,
                stage_response_records=project_stage_records,
                semaphore=llm_semaphore,
                job_focus=job_focus,
            )
        )
        managed_tasks.extend([skill_task, project_task])
        (project_result,) = await _wait_resume_generation_tasks_cancel_on_error(
            [project_task]
        )
        project_selection, selected_projects = project_result
        metric_notes = _build_status_metric_notes(
            projects=selected_projects,
            experiences=selected_experience.experience,
        )
        _report_generation_status(
            status_reporter,
            "project_selection",
            "succeeded",
            "Done",
            metric_notes=metric_notes,
        )

        if config.bullet_point_generation_strategy == "section_batch":
            logger.info(
                "resume_generation_stage_start",
                extra={
                    "event": "resume_generation_stage_start",
                    "stage": "resume_section_bullet_points",
                    "project_count": len(selected_projects),
                    "experience_count": len(selected_experience.experience),
                },
            )
            _report_generation_status(
                status_reporter,
                "bullet_points",
                "running",
                "Generating bullet points",
            )
            section_bullet_stage_records: list[dict[str, Any]] = []
            section_bullet_task = asyncio.create_task(
                generate_resume_section_bullet_points_async(
                    selected_projects=selected_projects,
                    experience=selected_experience.experience,
                    config=config,
                    job_target=job_target,
                    job_focus=job_focus,
                    cache=cache,
                    token_usage_monitor=None,
                    stage_response_records=section_bullet_stage_records,
                    semaphore=llm_semaphore,
                )
            )
            managed_tasks.append(section_bullet_task)
            selected_skills, section_bullet_points = (
                await _wait_resume_generation_tasks_cancel_on_error(
                    [skill_task, section_bullet_task]
                )
            )
            _report_generation_status(
                status_reporter,
                "skill_selection",
                "succeeded",
                "Done",
            )
            bullet_points = section_bullet_points.project_bullet_points
            experience_bullet_points = section_bullet_points.experience_bullet_points
            _report_generation_status(
                status_reporter,
                "bullet_points",
                "succeeded",
                "Done",
            )
            project_bullet_stage_records: list[dict[str, Any]] = []
            experience_bullet_stage_records: list[dict[str, Any]] = []
        else:
            logger.info(
                "resume_generation_stage_start",
                extra={
                    "event": "resume_generation_stage_start",
                    "stage": "project_bullet_points",
                    "project_count": len(selected_projects),
                },
            )
            logger.info(
                "resume_generation_stage_start",
                extra={
                    "event": "resume_generation_stage_start",
                    "stage": "experience_bullet_points",
                    "experience_count": len(selected_experience.experience),
                },
            )
            _report_generation_status(
                status_reporter,
                "bullet_points",
                "running",
                "Generating bullet points",
            )
            bullet_semaphore = asyncio.Semaphore(config.concurrency.bullet_point_requests)
            project_bullet_stage_records = []
            experience_bullet_stage_records = []
            project_bullet_task = asyncio.create_task(
                generate_project_bullet_points_async(
                    selected_projects=selected_projects,
                    config=config,
                    job_target=job_target,
                    job_focus=job_focus,
                    cache=cache,
                    stage_response_records=project_bullet_stage_records,
                    semaphore=bullet_semaphore,
                    llm_semaphore=llm_semaphore,
                )
            )
            experience_bullet_task = asyncio.create_task(
                generate_experience_bullet_points_async(
                    experience=selected_experience.experience,
                    config=config,
                    job_target=job_target,
                    job_focus=job_focus,
                    cache=cache,
                    stage_response_records=experience_bullet_stage_records,
                    semaphore=bullet_semaphore,
                    llm_semaphore=llm_semaphore,
                )
            )
            managed_tasks.extend([project_bullet_task, experience_bullet_task])
            selected_skills, bullet_points, experience_bullet_points = (
                await _wait_resume_generation_tasks_cancel_on_error(
                    [skill_task, project_bullet_task, experience_bullet_task]
                )
            )
            _report_generation_status(
                status_reporter,
                "skill_selection",
                "succeeded",
                "Done",
            )
            _report_generation_status(
                status_reporter,
                "bullet_points",
                "succeeded",
                "Done",
            )
            section_bullet_stage_records = []
    except BaseException:
        for task in managed_tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*managed_tasks, return_exceptions=True)
        raise

    context = ResumeSelectionContext(
        job_target=job_target,
        selected_skills=selected_skills,
        project_selection=project_selection,
        selected_projects=selected_projects,
        config_path=context_config_path,
        job_target_path=context_job_target_path,
        evidence_paths=context_evidence_paths,
    )
    _observe_stage_response_records(
        records=job_focus_stage_records,
        token_usage_monitor=token_usage_monitor,
        stage_response_records=stage_response_records,
    )
    logger.info(
        "resume_generation_stage_complete",
        extra={
            "event": "resume_generation_stage_complete",
            "stage": "job_focus_generation",
            **_token_usage_extra(
                token_usage_monitor.stage_total("job_focus_generation")
            ),
        },
    )
    _observe_stage_response_records(
        records=skill_stage_records,
        token_usage_monitor=token_usage_monitor,
        stage_response_records=stage_response_records,
    )
    _observe_stage_response_records(
        records=project_stage_records,
        token_usage_monitor=token_usage_monitor,
        stage_response_records=stage_response_records,
    )
    logger.info(
        "resume_generation_stage_complete",
        extra={
            "event": "resume_generation_stage_complete",
            "stage": "selection",
            "selected_project_count": len(context.selected_projects),
            **_token_usage_extra(
                token_usage_monitor.combined_total(
                    ("skill_selection", "project_selection")
                )
            ),
        },
    )

    if config.bullet_point_generation_strategy == "section_batch":
        _observe_stage_response_records(
            records=section_bullet_stage_records,
            token_usage_monitor=token_usage_monitor,
            stage_response_records=stage_response_records,
        )
        logger.info(
            "resume_generation_stage_complete",
            extra={
                "event": "resume_generation_stage_complete",
                "stage": "resume_section_bullet_points",
                "project_result_count": len(bullet_points),
                "experience_result_count": len(experience_bullet_points),
                **_token_usage_extra(
                    token_usage_monitor.stage_total("resume_section_bullet_points")
                ),
            },
        )
    else:
        _observe_stage_response_records(
            records=project_bullet_stage_records,
            token_usage_monitor=token_usage_monitor,
            stage_response_records=stage_response_records,
        )
        _observe_stage_response_records(
            records=experience_bullet_stage_records,
            token_usage_monitor=token_usage_monitor,
            stage_response_records=stage_response_records,
        )
        logger.info(
            "resume_generation_stage_complete",
            extra={
                "event": "resume_generation_stage_complete",
                "stage": "project_bullet_points",
                "result_count": len(bullet_points),
                **_token_usage_extra(
                    token_usage_monitor.stage_total("project_bullet_points")
                ),
            },
        )
        logger.info(
            "resume_generation_stage_complete",
            extra={
                "event": "resume_generation_stage_complete",
                "stage": "experience_bullet_points",
                "result_count": len(experience_bullet_points),
                **_token_usage_extra(
                    token_usage_monitor.stage_total("experience_bullet_points")
                ),
            },
        )

    logger.info(
        "resume_generation_stage_start",
        extra={"event": "resume_generation_stage_start", "stage": "assembly"},
    )
    _report_generation_status(
        status_reporter,
        "assembly",
        "running",
        "Assembling resume",
    )
    resume_result = assemble_intermediate_resume_result(
        user_info=_user_info,
        education=_education,
        experience=selected_experience,
        selection_context=context,
        selected_projects=context.selected_projects,
        project_bullet_points=bullet_points,
        experience_bullet_points=experience_bullet_points,
        job_focus=job_focus,
    )
    logger.info(
        "resume_generation_stage_complete",
        extra={
            "event": "resume_generation_stage_complete",
            "stage": "assembly",
            **_token_usage_extra(TokenUsage()),
        },
    )
    _report_generation_status(
        status_reporter,
        "assembly",
        "succeeded",
        "Done",
    )

    artifact_path = write_resume_result_artifact(
        resume_result,
        resolved_result_artifact_path,
    )
    logger.info(
        "resume_generation_artifact_written",
        extra={
            "event": "resume_generation_artifact_written",
            "path": str(artifact_path),
        },
    )
    manifest = build_resume_run_manifest(
        config_path=resolved_config_path,
        job_target_path=resolved_job_target_path,
        job_target_source=job_target_source,
        context=context,
        job_focus=job_focus,
        stage_response_records=stage_response_records,
        token_usage_monitor=token_usage_monitor,
        resume_result_artifact_path=artifact_path,
        resume_result=resume_result,
    )
    manifest_path = write_resume_run_manifest_artifact(
        manifest,
        resolved_manifest_artifact_path,
    )
    logger.info(
        "resume_generation_artifact_written",
        extra={
            "event": "resume_generation_artifact_written",
            "path": str(manifest_path),
        },
    )

    logger.info(
        "resume_generation_token_usage_summary",
        extra={
            "event": "resume_generation_token_usage_summary",
            **token_usage_monitor.summary(),
        },
    )

    logger.info(
        "resume_generation_pipeline_complete",
        extra={"event": "resume_generation_pipeline_complete"},
    )

    return resume_result


def write_resume_latex_from_config(
    resume_result: IntermediateResumeResult,
    *,
    config_path: Path | str | None = None,
) -> Path:
    config = load_generation_config(config_path)
    artifact_path = write_resume_latex_artifact(resume_result, settings.resume_tex_artifact_path)
    logger.info(
        "resume_generation_latex_artifact_written",
        extra={
            "event": "resume_generation_latex_artifact_written",
            "path": str(artifact_path),
        },
    )
    output_path = copy_resume_latex_to_user_output(
        artifact_path,
        config.resume_output.output_dir,
    )
    logger.info(
        "resume_generation_latex_output_written",
        extra={
            "event": "resume_generation_latex_output_written",
            "path": str(output_path),
        },
    )
    return output_path


def write_resume_pdf_from_config(
    tex_path: Path | str | None = None,
    *,
    config_path: Path | str | None = None,
) -> Path | None:
    config = load_generation_config(config_path)
    if not config.resume_output.render_pdf:
        logger.info(
            "resume_generation_pdf_render_skipped",
            extra={
                "event": "resume_generation_pdf_render_skipped",
                "reason": "disabled",
            },
        )
        return None

    artifact_path = render_latex_pdf(
        tex_path or settings.resume_tex_artifact_path,
        settings.resume_pdf_artifact_path,
        timeout_seconds=config.resume_output.pdf_timeout_seconds,
    )
    logger.info(
        "resume_generation_pdf_artifact_written",
        extra={
            "event": "resume_generation_pdf_artifact_written",
            "path": str(artifact_path),
        },
    )
    output_path = copy_resume_pdf_to_user_output(
        artifact_path,
        config.resume_output.output_dir,
    )
    logger.info(
        "resume_generation_pdf_output_written",
        extra={
            "event": "resume_generation_pdf_output_written",
            "path": str(output_path),
        },
    )
    return output_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the ResumeCR7 resume generation pipeline.")
    parser.parse_args(argv)
    bootstrap_runtime_data(
        data_dir=settings.RESUMECR7_DATA_DIR,
        evidence_root=settings.RESUME_EVIDENCE_ROOT,
        generation_root=settings.RESUME_GENERATION_ROOT,
        artifacts_root=settings.resume_generation_artifacts_root,
        log_dir=settings.RESUMECR7_LOG_DIR,
    )
    resume_result = run_resume_generation_pipeline()
    write_resume_latex_from_config(resume_result)
    write_resume_pdf_from_config(settings.resume_tex_artifact_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
