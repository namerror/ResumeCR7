# entry point for resume generation

import argparse
import json
import logging
import os
from pathlib import Path
from typing import Any

from app.config import settings
from app.runtime_data import bootstrap_runtime_data
from app.resume_evidence import (
    EducationFile,
    ExperienceFile,
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
    generate_experience_bullet_points,
    generate_project_bullet_points,
)
from app.resume_generation.cache import ResumeGenerationStageCache
from app.resume_generation.job_focus import derive_job_focus
from app.resume_generation.latex import write_resume_latex_artifact
from app.resume_generation.models import (
    IntermediateResumeResult,
    JobFocusResult,
    JobTarget,
    ResumeSelectionContext,
)
from app.resume_generation.pdf import render_latex_pdf
from app.resume_generation.selection import generate_selection_context
from app.resume_generation.token_usage import ResumeGenerationTokenUsageMonitor, TokenUsage

DEFAULT_RESUME_RESULT_ARTIFACT_PATH = settings.resume_result_artifact_path
DEFAULT_RESUME_RUN_MANIFEST_ARTIFACT_PATH = settings.resume_run_manifest_artifact_path
logger = logging.getLogger("resume_generation")


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


def _select_resume_experience(
    experience: ExperienceFile,
    *,
    top_n: int | None,
) -> ExperienceFile:
    active_records = [item for item in experience.experience if item.active]
    if top_n is not None:
        active_records = active_records[:top_n]
    return ExperienceFile(schema_version=experience.schema_version, experience=active_records)


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
    artifact_path = write_resume_latex_artifact(
        resume_result,
        config.resume_output.path,
    )
    logger.info(
        "resume_generation_latex_artifact_written",
        extra={
            "event": "resume_generation_latex_artifact_written",
            "path": str(artifact_path),
        },
    )
    return artifact_path


def write_resume_pdf_from_config(
    tex_path: Path | str,
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
        tex_path,
        config.resume_output.pdf_path,
        timeout_seconds=config.resume_output.pdf_timeout_seconds,
    )
    logger.info(
        "resume_generation_pdf_artifact_written",
        extra={
            "event": "resume_generation_pdf_artifact_written",
            "path": str(artifact_path),
        },
    )
    return artifact_path


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
    latex_path = write_resume_latex_from_config(resume_result)
    write_resume_pdf_from_config(latex_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
