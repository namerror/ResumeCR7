from __future__ import annotations

import asyncio
import json
import logging
import subprocess
import sys
from pathlib import Path

import httpx
import pytest
import yaml
from pydantic import ValidationError

from app.bulletpoints_generation.models import BulletGenerationResponse
from app.config import settings
from app.job_focus_generation.models import JobFocus, JobFocusResponse
from app.link_scanning.models import LinkScanHighlight, LinkScanResponse
from app.main import app
from app.project_selection.models import (
    ProjectSelectionResult as AppProjectSelectionResult,
    RankedProject,
)
from app.resume_generation.status import MetricOpportunityNote, resume_generation_status_store
from app.skill_selection.models import SkillSelectResponse
from app.project_selection.llm_client import LLMProjectScoreResult
from app.skill_selection.llm_client import LLMScoreResult
from resume_generation import (
    DEFAULT_RESUME_PDF_ARTIFACT_PATH,
    DEFAULT_RESUME_TEX_ARTIFACT_PATH,
    ExperienceBulletPointResult,
    IntermediateResumeResult,
    JobTarget,
    LatexPdfPrerequisiteError,
    LatexPdfRenderError,
    ProjectBulletPointResult,
    ProjectSelectionResult,
    ResumeGenerationConfig,
    ResumeGenerationError,
    ResumeSelectionContext,
    SkillSelectionResult,
    assemble_intermediate_resume_result,
    build_skill_selection_payload,
    derive_job_focus,
    generate_experience_bullet_points,
    generate_experience_bullet_points_async,
    generate_project_bullet_points,
    generate_project_bullet_points_async,
    generate_resume_section_bullet_points,
    generate_selection_context,
    latex_escape,
    load_generation_config,
    load_job_target,
    resolve_generation_config_path,
    resolve_job_target_path,
    resolve_resume_result_artifact_path,
    resolve_resume_run_manifest_artifact_path,
    render_latex_pdf,
    render_resume_latex,
    resolve_resume_pdf_output_path,
    resolve_resume_latex_output_path,
    run_link_evidence_enrichment,
    write_resume_latex_artifact,
)
from resume_generation.cache import ResumeGenerationStageCache
import resume_generation.enrich as resume_enrich
import resume_generation.selection as resume_selection
import resume_generation.pdf as resume_pdf
from resume_generation.main import (
    _select_resume_experience,
    run_resume_generation_pipeline_async,
    run_resume_generation_pipeline,
    write_resume_latex_from_config,
    write_resume_pdf_from_config,
    write_resume_result_artifact,
)
from resume_generation.token_usage import extract_response_token_usage
from resume_evidence import load_evidence_yaml


def _write_yaml(path: Path, payload: dict) -> Path:
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def _config_payload(**overrides) -> dict:
    payload = {
        "schema_version": 1,
        "bullet_point_generation_strategy": "per_record",
        "app": {
            "base_url": "http://resumecr7.test",
            "timeout_seconds": 5,
        },
        "skill_selection": {
            "method": "llm",
            "top_n": 3,
            "baseline_filter": True,
            "dev_mode": True,
            "llm_model": "skill-model",
            "llm_max_output_tokens": 777,
        },
        "project_selection": {
            "method": "llm",
            "top_n": 2,
            "dev_mode": True,
            "llm_model": "project-model",
            "llm_max_output_tokens": 880,
        },
        "job_focus_generation": {
            "dev_mode": True,
            "llm_model": "job-focus-model",
            "llm_max_output_tokens": 770,
        },
        "link_scanning": {
            "enabled": False,
            "dev_mode": True,
            "llm_model": "link-model",
            "llm_max_output_tokens": 660,
            "highlight_count": 6,
            "max_tokens_per_highlight": 120,
        },
        "project_bullet_point_generation": {
            "bullet_count_range": {"min": 2, "max": 4},
            "dev_mode": True,
            "llm_model": "project-bullet-model",
            "llm_max_output_tokens": 990,
        },
        "experience_bullet_point_generation": {
            "bullet_count_range": {"min": 1, "max": 2},
            "dev_mode": True,
            "llm_model": "experience-bullet-model",
            "llm_max_output_tokens": 990,
        },
    }
    payload.update(overrides)
    return payload


def _job_target_payload(**overrides) -> dict:
    payload = {
        "schema_version": 1,
        "title": "Backend Engineer",
        "description": "Build Python APIs with FastAPI.",
    }
    payload.update(overrides)
    return payload


def _job_focus_payload(**overrides) -> dict:
    payload = {
        "summary": "Backend API role focused on Python services.",
        "required_skills": ["Python", "FastAPI"],
        "preferred_skills": ["Docker"],
        "responsibilities": ["Build and maintain REST APIs"],
        "domain_emphasis": ["Backend platforms"],
        "resume_relevant_constraints": ["Remote collaboration"],
        "excluded_context": ["Benefits and company culture"],
    }
    payload.update(overrides)
    return payload


def _job_focus_response(total_tokens: int = 13) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "job_focus": _job_focus_payload(),
            "details": {
                "_job_focus_llm": {
                    "prompt_tokens": 8,
                    "completion_tokens": 5,
                    "total_tokens": total_tokens,
                    "api_calls": 1,
                    "latency_ms": 75.0,
                }
            },
        },
    )


def _skills_payload() -> dict:
    return {
        "schema_version": 1,
        "skills": {
            "technology": ["FastAPI", "Django"],
            "programming": ["Python"],
            "concepts": ["API"],
        },
    }


def _user_payload() -> dict:
    return {
        "schema_version": 1,
        "name": "Example Candidate",
        "email": "candidate@example.com",
        "phone": "+1 555-0100",
        "linkedin": "https://www.linkedin.com/in/example-candidate",
        "github": "https://github.com/example-candidate",
    }


def _education_payload() -> dict:
    return {
        "schema_version": 1,
        "education": [
            {
                "id": "example-university",
                "name": "Example University",
                "degree": "Bachelor of Science in Computer Science",
                "grade": "3.8 GPA",
                "start": "2020",
                "end": "2024",
                "location": "Example City, ST",
                "relevant_coursework": ["Data Structures", "Algorithms"],
            }
        ],
    }


def _experience_payload() -> dict:
    return {
        "schema_version": 1,
        "experience": [
            {
                "id": "backend-engineer",
                "name": "Example Company",
                "role": "Backend Engineer",
                "summary": "Built backend services for internal platforms.",
                "highlights": ["Designed schema-validated APIs."],
                "active": True,
                "skills": {
                    "technology": ["FastAPI"],
                    "programming": ["Python"],
                    "concepts": ["API"],
                },
                "location": "Example City, ST",
                "start": "2024",
                "end": None,
                "links": ["https://example.com/company"],
            }
        ],
    }


def _projects_payload() -> dict:
    return {
        "schema_version": 1,
        "projects": [
            {
                "id": "active-project",
                "name": "Active Project",
                "summary": "FastAPI backend service.",
                "highlights": ["Built the service."],
                "active": True,
                "skills": {
                    "technology": ["FastAPI"],
                    "programming": ["Python"],
                    "concepts": ["API"],
                },
                "links": ["https://example.com/active"],
            },
            {
                "id": "inactive-project",
                "name": "Inactive Project",
                "summary": "Inactive frontend project.",
                "highlights": ["Built the frontend."],
                "active": False,
                "skills": {
                    "technology": ["Angular"],
                    "programming": ["JavaScript"],
                    "concepts": ["UI"],
                },
                "links": None,
            },
        ],
    }


def _loaded_evidence(
    projects_path: Path,
    skills_path: Path,
    user_path: Path | None = None,
    education_path: Path | None = None,
    experience_path: Path | None = None,
) -> dict:
    if user_path is None:
        user_path = _write_yaml(projects_path.parent / "user.yaml", _user_payload())
    if education_path is None:
        education_path = _write_yaml(
            projects_path.parent / "education.yaml",
            _education_payload(),
        )
    if experience_path is None:
        experience_path = _write_yaml(
            projects_path.parent / "experience.yaml",
            _experience_payload(),
        )
    return {
        "education": load_evidence_yaml(education_path, "education"),
        "experience": load_evidence_yaml(experience_path, "experience"),
        "projects": load_evidence_yaml(projects_path, "projects"),
        "skills": load_evidence_yaml(skills_path, "skills"),
        "user": load_evidence_yaml(user_path, "user"),
    }


@pytest.mark.parametrize(
    ("top_n", "expected_ids"),
    [
        (
            None,
            [
                "backend-engineer",
                "recent-ended-role",
                "early-start-same-end",
                "platform-engineer",
            ],
        ),
        (0, []),
        (1, ["backend-engineer"]),
        (2, ["backend-engineer", "recent-ended-role"]),
    ],
)
def test_select_resume_experience_orders_latest_experiences_first(
    tmp_path,
    top_n,
    expected_ids,
):
    def experience_record(
        *,
        record_id: str,
        active: bool,
        start: str,
        end: str | None,
    ) -> dict:
        return {
            "id": record_id,
            "name": f"{record_id} Company",
            "role": "Engineer",
            "summary": "Built platform tooling.",
            "highlights": ["Improved deployment workflows."],
            "active": active,
            "skills": {
                "technology": ["Kubernetes"],
                "programming": ["Python"],
                "concepts": ["CI/CD"],
            },
            "location": "Remote",
            "start": start,
            "end": end,
            "links": None,
        }

    experience_payload = _experience_payload()
    experience_payload["experience"].extend(
        [
            experience_record(
                record_id="inactive-role",
                active=False,
                start="2026",
                end=None,
            ),
            experience_record(
                record_id="platform-engineer",
                active=True,
                start="2023",
                end="2024",
            ),
            experience_record(
                record_id="early-start-same-end",
                active=True,
                start="2021",
                end="2024",
            ),
            experience_record(
                record_id="recent-ended-role",
                active=True,
                start="2025",
                end="2026",
            ),
        ]
    )
    experience_path = _write_yaml(tmp_path / "experience.yaml", experience_payload)
    experience_file = load_evidence_yaml(experience_path, "experience")

    result = _select_resume_experience(experience_file, top_n=top_n)

    assert [item.id for item in result.experience] == expected_ids


def test_select_resume_experience_orders_month_name_dates_chronologically(tmp_path):
    def experience_record(
        *,
        record_id: str,
        start: str,
        end: str | None,
    ) -> dict:
        return {
            "id": record_id,
            "name": f"{record_id} Company",
            "role": "Engineer",
            "summary": "Built platform tooling.",
            "highlights": ["Improved deployment workflows."],
            "active": True,
            "skills": {
                "technology": ["Kubernetes"],
                "programming": ["Python"],
                "concepts": ["CI/CD"],
            },
            "location": "Remote",
            "start": start,
            "end": end,
            "links": None,
        }

    experience_path = _write_yaml(
        tmp_path / "experience.yaml",
        {
            "schema_version": 1,
            "experience": [
                experience_record(
                    record_id="august-2025-role",
                    start="June 2025",
                    end="August 2025",
                ),
                experience_record(
                    record_id="current-later-start",
                    start="May 2026",
                    end="Present",
                ),
                experience_record(
                    record_id="current-earlier-start",
                    start="Feb 2026",
                    end=None,
                ),
                experience_record(
                    record_id="same-end-later-start",
                    start="July 2026",
                    end="August 2026",
                ),
                experience_record(
                    record_id="same-end-earlier-start",
                    start="June 2026",
                    end="August 2026",
                ),
                experience_record(
                    record_id="sept-2025-role",
                    start="June 2025",
                    end="Sept 2025",
                ),
                experience_record(
                    record_id="sep-dot-2025-role",
                    start="July 2025",
                    end="Sep. 2025",
                ),
            ],
        },
    )
    experience_file = load_evidence_yaml(experience_path, "experience")

    result = _select_resume_experience(experience_file, top_n=None)

    assert [item.id for item in result.experience] == [
        "current-earlier-start",
        "current-later-start",
        "same-end-earlier-start",
        "same-end-later-start",
        "sept-2025-role",
        "sep-dot-2025-role",
        "august-2025-role",
    ]


def _sample_intermediate_resume_result() -> IntermediateResumeResult:
    return IntermediateResumeResult.model_validate(
        {
            "top": {
                "name": "Example Candidate",
                "phone": "+1 555-0100",
                "email": "candidate_name@example.com",
                "github": "https://github.com/example-candidate",
            },
            "education": [
                {
                    "name": "Example & University",
                    "degree": "Bachelor of Science in Computer Science",
                    "grade": "3.8 GPA",
                    "start": "2020",
                    "end": "2024",
                    "location": "Example City, ST",
                    "relevant_coursework": ["Data Structures", "Algorithms"],
                }
            ],
            "experience": [
                {
                    "name": "Example Company",
                    "role": "Backend Engineer",
                    "bullet_points": ["Designed schema-validated APIs & workers."],
                    "skills": ["FastAPI", "Python"],
                    "location": "Example City, ST",
                    "start": "2024",
                    "end": None,
                }
            ],
            "projects": [
                {
                    "name": "Active Project",
                    "bullet_points": ["Generated bullet for active_project."],
                    "skills": ["FastAPI", "Python", "API"],
                    "links": ["https://example.com/active"],
                }
            ],
            "skills": {
                "technology": ["FastAPI"],
                "programming": ["Python"],
                "concepts": ["API"],
            },
        }
    )


def _install_successful_pipeline_client(monkeypatch, calls: list[dict]) -> None:
    class FakeClient:
        def __init__(self, *, base_url: str, timeout: float):
            assert base_url == "http://resumecr7.test"
            assert timeout == 5

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return None

        def post(self, endpoint: str, json: dict):
            project_id = json.get("project", {}).get("id")
            experience_id = json.get("experience", {}).get("id")
            calls.append(
                {
                    "endpoint": endpoint,
                    "project_id": project_id,
                    "experience_id": experience_id,
                    "llm_model": json.get("llm_model"),
                }
            )
            if endpoint == "/select-skills":
                return httpx.Response(
                    200,
                    json={
                        "technology": ["FastAPI"],
                        "programming": ["Python"],
                        "concepts": ["API"],
                        "details": {
                            "_llm": {
                                "prompt_tokens": 10,
                                "completion_tokens": 5,
                                "total_tokens": 15,
                                "api_calls": 1,
                                "latency_ms": 100.125,
                            }
                        },
                    },
                )
            if endpoint == "/select-projects":
                return httpx.Response(
                    200,
                    json={
                        "selected_project_ids": ["active-project"],
                        "ranked_projects": [
                            {
                                "project_id": "active-project",
                                "score": 1.0,
                                "method": "llm",
                            }
                        ],
                        "details": {
                            "_project_llm": {
                                "prompt_tokens": 20,
                                "completion_tokens": 10,
                                "total_tokens": 30,
                                "api_calls": 1,
                                "latency_ms": 200.25,
                            }
                        },
                    },
                )
            if endpoint == "/derive-job-focus":
                return _job_focus_response()
            if endpoint == "/generate-bulletpoints":
                evidence_id = project_id or experience_id
                bullet_count_range = json.get("bullet_count_range") or {}
                bullet_count = bullet_count_range.get("min", 1)
                return httpx.Response(
                    200,
                    json={
                        "bullet_points": [
                            f"Generated bullet {index} for {evidence_id}."
                            for index in range(1, bullet_count + 1)
                        ],
                        "details": {
                            "_bulletpoints_llm": {
                                "prompt_tokens": 4,
                                "completion_tokens": 3,
                                "total_tokens": 7,
                                "api_calls": 1,
                                "latency_ms": 25.0,
                            }
                        },
                    },
                )
            raise AssertionError(f"unexpected endpoint: {endpoint}")

    monkeypatch.setattr("resume_generation.selection.httpx.Client", FakeClient)
    monkeypatch.setattr("resume_generation.bullet_points.httpx.Client", FakeClient)


def test_load_generation_config_returns_typed_config(tmp_path):
    path = _write_yaml(tmp_path / "config.yaml", _config_payload())

    config = load_generation_config(path)

    assert isinstance(config, ResumeGenerationConfig)
    assert config.bullet_point_generation_strategy == "per_record"
    assert config.openai.api_key is None
    assert config.app.base_url == "http://resumecr7.test"
    assert config.skill_selection.llm_model == "skill-model"
    assert config.project_selection.llm_max_output_tokens == 880
    assert config.job_focus_generation.dev_mode is True
    assert config.job_focus_generation.llm_model == "job-focus-model"
    assert config.job_focus_generation.llm_max_output_tokens == 770
    assert config.link_scanning.enabled is False
    assert config.link_scanning.dev_mode is True
    assert config.link_scanning.llm_model == "link-model"
    assert config.link_scanning.llm_max_output_tokens == 660
    assert config.link_scanning.highlight_count == 6
    assert config.link_scanning.max_tokens_per_highlight == 120
    assert config.project_bullet_point_generation.llm_model == "project-bullet-model"
    assert config.project_bullet_point_generation.bullet_count_range is not None
    assert config.project_bullet_point_generation.bullet_count_range.min == 2
    assert (
        config.experience_bullet_point_generation.llm_model
        == "experience-bullet-model"
    )
    assert config.experience_bullet_point_generation.bullet_count_range is not None
    assert config.experience_bullet_point_generation.bullet_count_range.min == 1
    assert config.concurrency.llm_requests == 3
    assert config.concurrency.bullet_point_requests == 3
    assert config.cache.enabled is True
    assert config.cache.force_refresh is False
    assert config.resume_output.path is None
    assert config.resume_output.pdf_path is None
    assert config.resume_output.output_dir == str(settings.resume_generation_output_root)
    assert config.resume_output.render_pdf is False
    assert config.resume_output.pdf_timeout_seconds == 60.0
    assert resolve_resume_latex_output_path(config.resume_output.path) == (
        DEFAULT_RESUME_TEX_ARTIFACT_PATH
    )
    assert resolve_resume_pdf_output_path(config.resume_output.pdf_path) == (
        DEFAULT_RESUME_PDF_ARTIFACT_PATH
    )


def test_resume_generation_config_defaults_to_section_batch():
    config = ResumeGenerationConfig.model_validate({"schema_version": 1})

    assert config.bullet_point_generation_strategy == "section_batch"


def test_load_generation_config_accepts_dynamic_output_token_budgets(tmp_path):
    payload = _config_payload()
    payload["project_selection"].pop("llm_max_output_tokens")
    payload["project_selection"]["llm_output_token_budget"] = {
        "base": 800,
        "per_candidate": 50,
        "per_prompt_1k_chars": 25,
        "min": 1100,
        "max": None,
    }
    payload["project_bullet_point_generation"].pop("llm_max_output_tokens")
    payload["project_bullet_point_generation"]["llm_output_token_budget"] = {
        "base": 1000,
        "per_bullet": 400,
        "per_highlight": 20,
        "per_evidence_1k_chars": 50,
        "min": 1500,
        "max": None,
    }
    payload["experience_bullet_point_generation"].pop("llm_max_output_tokens")
    payload["experience_bullet_point_generation"]["llm_output_token_budget"] = {
        "base": 1100,
        "per_bullet": 450,
        "per_highlight": 25,
        "per_evidence_1k_chars": 60,
        "min": 1600,
        "max": 5000,
    }
    path = _write_yaml(tmp_path / "config.yaml", payload)

    config = load_generation_config(path)

    assert config.project_selection.llm_max_output_tokens is None
    assert config.project_selection.llm_output_token_budget is not None
    assert config.project_selection.llm_output_token_budget.per_candidate == 50
    assert config.project_selection.llm_output_token_budget.max is None
    assert (
        config.project_bullet_point_generation.llm_output_token_budget.per_bullet
        == 400
    )
    assert config.experience_bullet_point_generation.llm_output_token_budget.max == 5000


def test_generation_default_paths_follow_settings(monkeypatch, tmp_path):
    generation_root = tmp_path / "resume_generation"
    monkeypatch.setattr(settings, "RESUME_GENERATION_ROOT", generation_root)

    assert resolve_generation_config_path() == generation_root / "config.yaml"
    assert resolve_job_target_path() == generation_root / "job_target.yaml"
    assert (
        resolve_resume_result_artifact_path()
        == generation_root / "artifacts" / "resume_result.json"
    )
    assert (
        resolve_resume_run_manifest_artifact_path()
        == generation_root / "artifacts" / "resume_run_manifest.json"
    )
    assert resolve_resume_latex_output_path(None) == (
        generation_root / "artifacts" / "resume.tex"
    )
    assert resolve_resume_pdf_output_path(None) == (
        generation_root / "artifacts" / "resume.pdf"
    )
    assert settings.resume_generation_output_root == generation_root / "output"


def test_load_generation_config_accepts_cache_config(tmp_path):
    path = _write_yaml(
        tmp_path / "config.yaml",
        _config_payload(
            cache={
                "enabled": True,
                "path": str(tmp_path / "cache"),
                "force_refresh": True,
            }
        ),
    )

    config = load_generation_config(path)

    assert config.cache.enabled is True
    assert config.cache.path == str(tmp_path / "cache")
    assert config.cache.force_refresh is True


def test_load_generation_config_accepts_resume_output_path(tmp_path):
    output_path = tmp_path / "resume.tex"
    path = _write_yaml(
        tmp_path / "config.yaml",
        _config_payload(resume_output={"path": str(output_path)}),
    )

    config = load_generation_config(path)

    assert config.resume_output.path == str(output_path)
    assert config.resume_output.output_dir == str(tmp_path)
    assert resolve_resume_latex_output_path(config.resume_output.path) == output_path


def test_load_generation_config_defaults_blank_resume_output_path(tmp_path):
    path = _write_yaml(
        tmp_path / "config.yaml",
        _config_payload(resume_output={"path": "   "}),
    )

    config = load_generation_config(path)

    assert config.resume_output.path is None
    assert config.resume_output.output_dir == str(settings.resume_generation_output_root)
    assert resolve_resume_latex_output_path(config.resume_output.path) == (
        DEFAULT_RESUME_TEX_ARTIFACT_PATH
    )


def test_load_generation_config_accepts_pdf_resume_output_settings(tmp_path):
    tex_path = tmp_path / "resume.tex"
    pdf_path = tmp_path / "resume.pdf"
    path = _write_yaml(
        tmp_path / "config.yaml",
        _config_payload(
            resume_output={
                "path": str(tex_path),
                "pdf_path": str(pdf_path),
                "render_pdf": True,
                "pdf_timeout_seconds": 45,
            }
        ),
    )

    config = load_generation_config(path)

    assert config.resume_output.path == str(tex_path)
    assert config.resume_output.pdf_path == str(pdf_path)
    assert config.resume_output.output_dir == str(tmp_path)
    assert config.resume_output.render_pdf is True
    assert config.resume_output.pdf_timeout_seconds == 45.0
    assert resolve_resume_pdf_output_path(config.resume_output.pdf_path) == pdf_path


def test_load_generation_config_defaults_blank_pdf_resume_output_path(tmp_path):
    path = _write_yaml(
        tmp_path / "config.yaml",
        _config_payload(resume_output={"pdf_path": "   "}),
    )

    config = load_generation_config(path)

    assert config.resume_output.pdf_path is None
    assert resolve_resume_pdf_output_path(config.resume_output.pdf_path) == (
        DEFAULT_RESUME_PDF_ARTIFACT_PATH
    )


def test_load_generation_config_rejects_artifact_output_dir(monkeypatch, tmp_path):
    generation_root = tmp_path / "resume_generation"
    monkeypatch.setattr(settings, "RESUME_GENERATION_ROOT", generation_root)
    path = _write_yaml(
        tmp_path / "config.yaml",
        _config_payload(
            resume_output={"output_dir": str(generation_root / "artifacts" / "user")},
        ),
    )

    with pytest.raises(ValidationError):
        load_generation_config(path)


def test_load_generation_config_rejects_invalid_pdf_resume_output_settings(tmp_path):
    path = _write_yaml(
        tmp_path / "config.yaml",
        _config_payload(
            resume_output={
                "pdf_timeout_seconds": 0,
            }
        ),
    )

    with pytest.raises(ValidationError):
        load_generation_config(path)


def test_resume_generation_stage_cache_reuses_exact_payload(tmp_path):
    cache = ResumeGenerationStageCache(tmp_path / "cache")
    calls: list[str] = []

    first = cache.get_or_store(
        stage="skill_selection",
        payload={"job_role": "Backend Engineer", "top_n": 3},
        fetch=lambda: calls.append("fetch") or {"technology": ["FastAPI"]},
    )
    second = cache.get_or_store(
        stage="skill_selection",
        payload={"top_n": 3, "job_role": "Backend Engineer"},
        fetch=lambda: calls.append("fetch") or {"technology": ["Django"]},
    )

    assert first == {"technology": ["FastAPI"]}
    assert second == {"technology": ["FastAPI"]}
    assert calls == ["fetch"]


def test_resume_generation_stage_cache_uses_cache_payload_for_lookup(tmp_path):
    cache = ResumeGenerationStageCache(tmp_path / "cache")
    first_payload = {"job_role": "Backend Engineer", "top_n": 1}
    second_payload = {"job_role": "Backend Engineer", "top_n": 3}
    calls: list[int] = []

    first = cache.get_or_store(
        stage="skill_selection",
        payload=first_payload,
        cache_payload={"job_role": "Backend Engineer"},
        fetch=lambda: calls.append(first_payload["top_n"]) or {"top_n_seen": 1},
    )
    second = cache.get_or_store(
        stage="skill_selection",
        payload=second_payload,
        cache_payload={"job_role": "Backend Engineer"},
        fetch=lambda: calls.append(second_payload["top_n"]) or {"top_n_seen": 3},
    )

    assert first == {"top_n_seen": 1}
    assert second == {"top_n_seen": 1}
    assert calls == [1]


def test_resume_generation_stage_cache_invalidates_changed_payload(tmp_path):
    cache = ResumeGenerationStageCache(tmp_path / "cache")
    calls: list[str] = []

    cache.get_or_store(
        stage="skill_selection",
        payload={"job_role": "Backend Engineer"},
        fetch=lambda: calls.append("first") or {"technology": ["FastAPI"]},
    )
    result = cache.get_or_store(
        stage="skill_selection",
        payload={"job_role": "ML Engineer"},
        fetch=lambda: calls.append("second") or {"technology": ["PyTorch"]},
    )

    assert result == {"technology": ["PyTorch"]}
    assert calls == ["first", "second"]


def test_resume_generation_stage_cache_force_refresh_bypasses_read(tmp_path):
    cache = ResumeGenerationStageCache(tmp_path / "cache")
    payload = {"project": {"id": "active-project"}}

    cache.get_or_store(
        stage="project_bullet_points",
        payload=payload,
        fetch=lambda: {"bullet_points": ["Original bullet."]},
        namespace="active-project",
    )

    refreshing_cache = ResumeGenerationStageCache(tmp_path / "cache", force_refresh=True)
    result = refreshing_cache.get_or_store(
        stage="project_bullet_points",
        payload=payload,
        fetch=lambda: {"bullet_points": ["Refreshed bullet."]},
        namespace="active-project",
    )

    assert result == {"bullet_points": ["Refreshed bullet."]}


def test_resume_generation_stage_cache_treats_malformed_entry_as_miss(tmp_path):
    cache = ResumeGenerationStageCache(tmp_path / "cache")
    payload = {"project": {"id": "active-project"}}
    cache_key = cache.cache_key(stage="project_bullet_points", payload=payload)
    entry_path = cache._entry_path(
        stage="project_bullet_points",
        cache_key=cache_key,
        namespace="active-project",
    )
    entry_path.parent.mkdir(parents=True)
    entry_path.write_text("{not valid json", encoding="utf-8")

    result = cache.get_or_store(
        stage="project_bullet_points",
        payload=payload,
        fetch=lambda: {"bullet_points": ["Recovered bullet."]},
        namespace="active-project",
    )

    assert result == {"bullet_points": ["Recovered bullet."]}
    payload_on_disk = json.loads(entry_path.read_text(encoding="utf-8"))
    assert payload_on_disk["data"] == {"bullet_points": ["Recovered bullet."]}


def test_load_generation_config_rejects_invalid_bullet_count_range(tmp_path):
    path = _write_yaml(
        tmp_path / "config.yaml",
        _config_payload(
            project_bullet_point_generation={
                "bullet_count_range": {"min": 0, "max": 4},
                "dev_mode": True,
            }
        ),
    )

    with pytest.raises(ValidationError, match="bullet_count_range.min"):
        load_generation_config(path)


def test_load_generation_config_rejects_invalid_bullet_concurrency(tmp_path):
    path = _write_yaml(
        tmp_path / "config.yaml",
        _config_payload(concurrency={"bullet_point_requests": 0}),
    )

    with pytest.raises(ValidationError, match="concurrency request limits"):
        load_generation_config(path)


def test_load_generation_config_rejects_invalid_llm_concurrency(tmp_path):
    path = _write_yaml(
        tmp_path / "config.yaml",
        _config_payload(concurrency={"llm_requests": 0}),
    )

    with pytest.raises(ValidationError, match="concurrency request limits"):
        load_generation_config(path)


def test_load_generation_config_rejects_legacy_shared_bullet_config(tmp_path):
    path = _write_yaml(
        tmp_path / "config.yaml",
        _config_payload(
            bullet_point_generation={
                "bullet_count_range": {"min": 2, "max": 4},
                "dev_mode": True,
            }
        ),
    )

    with pytest.raises(ValidationError, match="project_bullet_point_generation"):
        load_generation_config(path)


def test_load_job_target_rejects_extra_fields(tmp_path):
    path = _write_yaml(tmp_path / "job.yaml", _job_target_payload(extra="nope"))

    with pytest.raises(ValidationError):
        load_job_target(path)


def test_build_skill_selection_payload_uses_evidence_and_config(tmp_path):
    config_path = _write_yaml(tmp_path / "config.yaml", _config_payload())
    job_path = _write_yaml(tmp_path / "job.yaml", _job_target_payload())
    skills_path = _write_yaml(tmp_path / "skills.yaml", _skills_payload())

    config = load_generation_config(config_path)
    job_target = load_job_target(job_path)

    skills_file = load_evidence_yaml(skills_path, "skills")

    payload = build_skill_selection_payload(
        job_target=job_target,
        skills_file=skills_file,
        config=config,
    )

    assert payload == {
        "job_role": "Backend Engineer",
        "job_text": "Build Python APIs with FastAPI.",
        "technology": ["FastAPI", "Django"],
        "programming": ["Python"],
        "concepts": ["API"],
        "method": "llm",
        "top_n": 3,
        "baseline_filter": True,
        "dev_mode": True,
        "llm_model": "skill-model",
        "llm_max_output_tokens": 777,
    }


def test_generate_selection_context_posts_evidence_payloads(monkeypatch, tmp_path):
    config_path = _write_yaml(tmp_path / "config.yaml", _config_payload())
    job_path = _write_yaml(tmp_path / "job.yaml", _job_target_payload())
    projects_path = _write_yaml(tmp_path / "projects.yaml", _projects_payload())
    skills_path = _write_yaml(tmp_path / "skills.yaml", _skills_payload())
    config = load_generation_config(config_path)
    job_target = load_job_target(job_path)
    requests: list[tuple[str, dict]] = []

    class FakeClient:
        def __init__(self, *, base_url: str, timeout: float):
            assert base_url == "http://resumecr7.test"
            assert timeout == 5

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return None

        def post(self, endpoint: str, json: dict):
            requests.append((endpoint, json))
            if endpoint == "/select-skills":
                return httpx.Response(
                    200,
                    json={
                        "technology": ["FastAPI"],
                        "programming": ["Python"],
                        "concepts": ["API"],
                        "details": {"method": "llm"},
                    },
                )
            if endpoint == "/select-projects":
                return httpx.Response(
                    200,
                    json={
                        "selected_project_ids": ["active-project"],
                        "ranked_projects": [
                            {
                                "project_id": "active-project",
                                "score": 1.0,
                                "method": "llm",
                            }
                        ],
                        "details": {"method": "llm"},
                    },
                )
            raise AssertionError(f"unexpected endpoint: {endpoint}")

    monkeypatch.setattr("resume_generation.selection.httpx.Client", FakeClient)

    result = generate_selection_context(
        loaded_evidence=_loaded_evidence(projects_path, skills_path),
        config=config,
        job_target=job_target,
        config_path=config_path,
        job_target_path=job_path,
        evidence_paths={
            "projects": projects_path,
            "skills": skills_path,
        },
    )

    assert [endpoint for endpoint, _ in requests] == ["/select-skills", "/select-projects"]
    assert requests[0][1]["llm_model"] == "skill-model"
    assert requests[1][1]["llm_model"] == "project-model"
    assert requests[1][1]["top_n"] == 2
    assert [candidate["id"] for candidate in requests[1][1]["candidates"]] == ["active-project"]
    assert result.selected_skills.technology == ["FastAPI"]
    assert [project.id for project in result.selected_projects] == ["active-project"]


def test_generate_project_bullet_points_posts_once_per_selected_project(monkeypatch, tmp_path):
    config_path = _write_yaml(tmp_path / "config.yaml", _config_payload())
    job_path = _write_yaml(tmp_path / "job.yaml", _job_target_payload())
    projects_path = _write_yaml(tmp_path / "projects.yaml", _projects_payload())
    skills_path = _write_yaml(tmp_path / "skills.yaml", _skills_payload())
    config = load_generation_config(config_path)
    job_target = load_job_target(job_path)
    projects_file = _loaded_evidence(projects_path, skills_path)["projects"]
    selected_project = projects_file.projects_by_id()["active-project"]
    requests: list[tuple[str, dict]] = []

    class FakeClient:
        def __init__(self, *, base_url: str, timeout: float):
            assert base_url == "http://resumecr7.test"
            assert timeout == 5

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return None

        def post(self, endpoint: str, json: dict):
            requests.append((endpoint, json))
            return httpx.Response(
                200,
                json={
                    "bullet_points": [f"Generated bullet for {json['project']['id']}."],
                    "details": {"method": "llm"},
                },
            )

    monkeypatch.setattr("resume_generation.bullet_points.httpx.Client", FakeClient)

    result = generate_project_bullet_points(
        selected_projects=[selected_project],
        config=config,
        job_target=job_target,
    )

    assert [endpoint for endpoint, _ in requests] == ["/generate-bulletpoints"]
    payload = requests[0][1]
    assert payload["context"] == {
        "title": "Backend Engineer",
        "description": "Build Python APIs with FastAPI.",
    }
    assert payload["project"]["id"] == "active-project"
    assert payload["project"]["highlights"] == ["Built the service."]
    assert payload["bullet_count_range"] == {"min": 2, "max": 4}
    assert payload["llm_model"] == "project-bullet-model"
    assert payload["llm_max_output_tokens"] == 990
    assert [item.project_id for item in result] == ["active-project"]
    assert result[0].bullet_points == ["Generated bullet for active-project."]


def test_generate_project_bullet_points_async_limits_concurrency_and_preserves_order(
    monkeypatch,
    tmp_path,
):
    config_payload = _config_payload(concurrency={"bullet_point_requests": 2})
    config_path = _write_yaml(tmp_path / "config.yaml", config_payload)
    job_path = _write_yaml(tmp_path / "job.yaml", _job_target_payload())
    projects_payload = _projects_payload()
    projects_payload["projects"].append(
        {
            "id": "second-active-project",
            "name": "Second Active Project",
            "summary": "Another FastAPI backend service.",
            "highlights": ["Built another service."],
            "active": True,
            "skills": {
                "technology": ["FastAPI"],
                "programming": ["Python"],
                "concepts": ["API"],
            },
            "links": None,
        }
    )
    projects_path = _write_yaml(tmp_path / "projects.yaml", projects_payload)
    skills_path = _write_yaml(tmp_path / "skills.yaml", _skills_payload())
    config = load_generation_config(config_path)
    job_target = load_job_target(job_path)
    projects_by_id = _loaded_evidence(projects_path, skills_path)["projects"].projects_by_id()
    selected_projects = [
        projects_by_id["active-project"],
        projects_by_id["second-active-project"],
    ]
    current_in_flight = 0
    max_in_flight = 0
    requests: list[str] = []
    stage_response_records: list[dict] = []

    class FakeAsyncClient:
        def __init__(self, *, base_url: str, timeout: float):
            assert base_url == "http://resumecr7.test"
            assert timeout == 5

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return None

        async def post(self, endpoint: str, json: dict):
            nonlocal current_in_flight, max_in_flight
            project_id = json["project"]["id"]
            requests.append(project_id)
            current_in_flight += 1
            max_in_flight = max(max_in_flight, current_in_flight)
            await asyncio.sleep(0.03 if project_id == "active-project" else 0.01)
            current_in_flight -= 1
            return httpx.Response(
                200,
                json={
                    "bullet_points": [f"Generated bullet for {project_id}."],
                    "details": {
                        "method": "llm",
                        "_bulletpoints_llm": {
                            "prompt_tokens": 1,
                            "completion_tokens": 1,
                            "total_tokens": 2,
                            "api_calls": 1,
                            "latency_ms": 10.0,
                        },
                    },
                },
            )

    monkeypatch.setattr("resume_generation.bullet_points.httpx.AsyncClient", FakeAsyncClient)

    result = asyncio.run(
        generate_project_bullet_points_async(
            selected_projects=selected_projects,
            config=config,
            job_target=job_target,
            stage_response_records=stage_response_records,
        )
    )

    assert set(requests) == {"active-project", "second-active-project"}
    assert max_in_flight == 2
    assert [item.project_id for item in result] == [
        "active-project",
        "second-active-project",
    ]
    assert [record["namespace"] for record in stage_response_records] == [
        "active-project",
        "second-active-project",
    ]


def test_generate_experience_bullet_points_posts_once_per_active_experience(
    monkeypatch,
    tmp_path,
):
    config_path = _write_yaml(tmp_path / "config.yaml", _config_payload())
    job_path = _write_yaml(tmp_path / "job.yaml", _job_target_payload())
    projects_path = _write_yaml(tmp_path / "projects.yaml", _projects_payload())
    skills_path = _write_yaml(tmp_path / "skills.yaml", _skills_payload())
    experience_payload = _experience_payload()
    experience_payload["experience"].append(
        {
            "id": "inactive-role",
            "name": "Inactive Company",
            "role": "Frontend Engineer",
            "summary": "Older inactive experience.",
            "highlights": ["This should not generate."],
            "active": False,
            "skills": {
                "technology": ["Angular"],
                "programming": ["JavaScript"],
                "concepts": ["UI"],
            },
            "location": "Remote",
            "start": "2022",
            "end": "2023",
            "links": None,
        }
    )
    experience_path = _write_yaml(tmp_path / "experience.yaml", experience_payload)
    config = load_generation_config(config_path)
    job_target = load_job_target(job_path)
    experience_file = _loaded_evidence(
        projects_path,
        skills_path,
        experience_path=experience_path,
    )["experience"]
    requests: list[tuple[str, dict]] = []

    class FakeClient:
        def __init__(self, *, base_url: str, timeout: float):
            assert base_url == "http://resumecr7.test"
            assert timeout == 5

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return None

        def post(self, endpoint: str, json: dict):
            requests.append((endpoint, json))
            return httpx.Response(
                200,
                json={
                    "bullet_points": [
                        f"Generated bullet for {json['experience']['id']}."
                    ],
                    "details": {"method": "llm"},
                },
            )

    monkeypatch.setattr("resume_generation.bullet_points.httpx.Client", FakeClient)

    result = generate_experience_bullet_points(
        experience=experience_file.experience,
        config=config,
        job_target=job_target,
    )

    assert [endpoint for endpoint, _ in requests] == ["/generate-bulletpoints"]
    payload = requests[0][1]
    assert payload["context"] == {
        "title": "Backend Engineer",
        "description": "Build Python APIs with FastAPI.",
    }
    assert payload["experience"]["id"] == "backend-engineer"
    assert payload["experience"]["role"] == "Backend Engineer"
    assert payload["experience"]["highlights"] == ["Designed schema-validated APIs."]
    assert payload["bullet_count_range"] == {"min": 1, "max": 2}
    assert payload["llm_model"] == "experience-bullet-model"
    assert payload["llm_max_output_tokens"] == 990
    assert [item.experience_id for item in result] == ["backend-engineer"]
    assert result[0].bullet_points == ["Generated bullet for backend-engineer."]


def test_generate_resume_section_bullet_points_posts_once_for_selected_records(
    monkeypatch,
    tmp_path,
):
    config_payload = _config_payload(
        bullet_point_generation_strategy="section_batch"
    )
    config_path = _write_yaml(tmp_path / "config.yaml", config_payload)
    job_path = _write_yaml(tmp_path / "job.yaml", _job_target_payload())
    projects_path = _write_yaml(tmp_path / "projects.yaml", _projects_payload())
    skills_path = _write_yaml(tmp_path / "skills.yaml", _skills_payload())
    config = load_generation_config(config_path)
    job_target = load_job_target(job_path)
    loaded_evidence = _loaded_evidence(projects_path, skills_path)
    selected_project = loaded_evidence["projects"].projects_by_id()["active-project"]
    experience_file = loaded_evidence["experience"]
    requests: list[tuple[str, dict]] = []

    class FakeClient:
        def __init__(self, *, base_url: str, timeout: float):
            assert base_url == "http://resumecr7.test"
            assert timeout == 5

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return None

        def post(self, endpoint: str, json: dict):
            requests.append((endpoint, json))
            return httpx.Response(
                200,
                json={
                    "project_bullet_points": [
                        {
                            "project_id": "active-project",
                            "bullet_points": ["Generated project batch bullet."],
                        }
                    ],
                    "experience_bullet_points": [
                        {
                            "experience_id": "backend-engineer",
                            "bullet_points": ["Generated experience batch bullet."],
                        }
                    ],
                    "details": {"method": "llm"},
                },
            )

    monkeypatch.setattr("resume_generation.bullet_points.httpx.Client", FakeClient)

    result = generate_resume_section_bullet_points(
        selected_projects=[selected_project],
        experience=experience_file.experience,
        config=config,
        job_target=job_target,
    )

    assert [endpoint for endpoint, _ in requests] == [
        "/generate-resume-section-bulletpoints"
    ]
    payload = requests[0][1]
    assert payload["context"] == {
        "title": "Backend Engineer",
        "description": "Build Python APIs with FastAPI.",
    }
    assert [project["id"] for project in payload["projects"]] == ["active-project"]
    assert [item["id"] for item in payload["experiences"]] == ["backend-engineer"]
    assert payload["project_bullet_count_range"] == {"min": 2, "max": 4}
    assert payload["experience_bullet_count_range"] == {"min": 1, "max": 2}
    assert payload["llm_model"] == "project-bullet-model"
    assert result.project_bullet_points[0].project_id == "active-project"
    assert result.experience_bullet_points[0].experience_id == "backend-engineer"


def test_derive_job_focus_posts_job_target_once(monkeypatch, tmp_path):
    config_path = _write_yaml(tmp_path / "config.yaml", _config_payload())
    job_path = _write_yaml(tmp_path / "job.yaml", _job_target_payload())
    config = load_generation_config(config_path)
    job_target = load_job_target(job_path)
    requests: list[tuple[str, dict]] = []

    class FakeClient:
        def __init__(self, *, base_url: str, timeout: float):
            assert base_url == "http://resumecr7.test"
            assert timeout == 5

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return None

        def post(self, endpoint: str, json: dict):
            requests.append((endpoint, json))
            return httpx.Response(
                200,
                json={
                    "job_focus": _job_focus_payload(),
                    "details": {
                        "method": "llm",
                        "_job_focus_llm": {"total_tokens": 13},
                    },
                },
            )

    monkeypatch.setattr("resume_generation.job_focus.httpx.Client", FakeClient)

    result = derive_job_focus(config=config, job_target=job_target)

    assert [endpoint for endpoint, _ in requests] == ["/derive-job-focus"]
    payload = requests[0][1]
    assert payload["title"] == "Backend Engineer"
    assert payload["description"] == "Build Python APIs with FastAPI."
    assert payload["dev_mode"] is True
    assert payload["llm_model"] == "job-focus-model"
    assert payload["llm_max_output_tokens"] == 770
    assert result.required_skills == ["Python", "FastAPI"]


def test_cached_project_bullet_generation_logs_response_source(
    monkeypatch,
    tmp_path,
    caplog,
):
    config_path = _write_yaml(tmp_path / "config.yaml", _config_payload())
    job_path = _write_yaml(tmp_path / "job.yaml", _job_target_payload())
    projects_path = _write_yaml(tmp_path / "projects.yaml", _projects_payload())
    skills_path = _write_yaml(tmp_path / "skills.yaml", _skills_payload())
    config = load_generation_config(config_path)
    job_target = load_job_target(job_path)
    projects_file = _loaded_evidence(projects_path, skills_path)["projects"]
    selected_project = projects_file.projects_by_id()["active-project"]
    cache = ResumeGenerationStageCache(tmp_path / "cache")
    calls: list[str] = []

    class FakeClient:
        def __init__(self, *, base_url: str, timeout: float):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return None

        def post(self, endpoint: str, json: dict):
            calls.append(endpoint)
            return httpx.Response(
                200,
                json={
                    "bullet_points": [
                        "Generated bullet 1 for active-project.",
                        "Generated bullet 2 for active-project.",
                    ],
                    "details": {
                        "_bulletpoints_llm": {
                            "prompt_tokens": 6,
                            "completion_tokens": 4,
                            "total_tokens": 10,
                            "api_calls": 1,
                            "latency_ms": 50.5,
                        }
                    },
                },
            )

    monkeypatch.setattr("resume_generation.bullet_points.httpx.Client", FakeClient)

    with caplog.at_level(logging.INFO, logger="resume_generation"):
        generate_project_bullet_points(
            selected_projects=[selected_project],
            config=config,
            job_target=job_target,
            cache=cache,
        )
        generate_project_bullet_points(
            selected_projects=[selected_project],
            config=config,
            job_target=job_target,
            cache=cache,
        )

    response_records = [
        record
        for record in caplog.records
        if getattr(record, "event", None) == "resume_generation_stage_response"
    ]
    assert calls == ["/generate-bulletpoints"]
    assert [
        (record.stage, record.source, record.cache_status, record.endpoint)
        for record in response_records
    ] == [
        ("project_bullet_points", "http", "miss", "/generate-bulletpoints"),
        ("project_bullet_points", "cache", "hit", "/generate-bulletpoints"),
    ]
    assert [
        (
            record.prompt_tokens,
            record.completion_tokens,
            record.total_tokens,
            record.api_calls,
            record.latency_ms,
        )
        for record in response_records
    ] == [
        (6, 4, 10, 1, 50.5),
        (6, 4, 10, 1, 50.5),
    ]
    assert all(record.cache_key for record in response_records)


def test_project_bullet_cache_reuses_across_dev_mode_and_output_token_changes(
    monkeypatch,
    tmp_path,
):
    cache = ResumeGenerationStageCache(tmp_path / "cache")
    first_config_payload = _config_payload()
    first_config_payload["project_bullet_point_generation"]["dev_mode"] = False
    first_config_payload["project_bullet_point_generation"]["llm_max_output_tokens"] = 111
    first_config_path = _write_yaml(tmp_path / "first-config.yaml", first_config_payload)
    second_config_payload = _config_payload()
    second_config_payload["project_bullet_point_generation"]["dev_mode"] = True
    second_config_payload["project_bullet_point_generation"]["llm_max_output_tokens"] = 222
    second_config_path = _write_yaml(tmp_path / "second-config.yaml", second_config_payload)
    job_path = _write_yaml(tmp_path / "job.yaml", _job_target_payload())
    projects_path = _write_yaml(tmp_path / "projects.yaml", _projects_payload())
    skills_path = _write_yaml(tmp_path / "skills.yaml", _skills_payload())
    selected_project = _loaded_evidence(projects_path, skills_path)[
        "projects"
    ].projects_by_id()["active-project"]
    requests: list[dict] = []

    class FakeClient:
        def __init__(self, *, base_url: str, timeout: float):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return None

        def post(self, endpoint: str, json: dict):
            requests.append(json)
            return httpx.Response(
                200,
                json={
                    "bullet_points": ["Project bullet one.", "Project bullet two."],
                    "details": {"method": "llm", "_bulletpoints_llm": {"total_tokens": 12}},
                },
            )

    monkeypatch.setattr("resume_generation.bullet_points.httpx.Client", FakeClient)

    first_result = generate_project_bullet_points(
        selected_projects=[selected_project],
        config=load_generation_config(first_config_path),
        job_target=load_job_target(job_path),
        cache=cache,
    )
    second_result = generate_project_bullet_points(
        selected_projects=[selected_project],
        config=load_generation_config(second_config_path),
        job_target=load_job_target(job_path),
        cache=cache,
    )

    assert len(requests) == 1
    assert requests[0]["dev_mode"] is True
    assert requests[0]["llm_max_output_tokens"] == 111
    assert first_result[0].details is None
    assert second_result[0].details == {
        "method": "llm",
        "_bulletpoints_llm": {"total_tokens": 12},
    }


def test_experience_bullet_cache_reuses_across_dev_mode_and_output_token_changes(
    monkeypatch,
    tmp_path,
):
    cache = ResumeGenerationStageCache(tmp_path / "cache")
    first_config_payload = _config_payload()
    first_config_payload["experience_bullet_point_generation"]["dev_mode"] = False
    first_config_payload["experience_bullet_point_generation"]["llm_max_output_tokens"] = 111
    first_config_path = _write_yaml(tmp_path / "first-config.yaml", first_config_payload)
    second_config_payload = _config_payload()
    second_config_payload["experience_bullet_point_generation"]["dev_mode"] = True
    second_config_payload["experience_bullet_point_generation"]["llm_max_output_tokens"] = 222
    second_config_path = _write_yaml(tmp_path / "second-config.yaml", second_config_payload)
    job_path = _write_yaml(tmp_path / "job.yaml", _job_target_payload())
    projects_path = _write_yaml(tmp_path / "projects.yaml", _projects_payload())
    skills_path = _write_yaml(tmp_path / "skills.yaml", _skills_payload())
    active_experience = _loaded_evidence(projects_path, skills_path)[
        "experience"
    ].experience
    requests: list[dict] = []

    class FakeClient:
        def __init__(self, *, base_url: str, timeout: float):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return None

        def post(self, endpoint: str, json: dict):
            requests.append(json)
            return httpx.Response(
                200,
                json={
                    "bullet_points": ["Experience bullet."],
                    "details": {"method": "llm", "_bulletpoints_llm": {"total_tokens": 13}},
                },
            )

    monkeypatch.setattr("resume_generation.bullet_points.httpx.Client", FakeClient)

    first_result = generate_experience_bullet_points(
        experience=active_experience,
        config=load_generation_config(first_config_path),
        job_target=load_job_target(job_path),
        cache=cache,
    )
    second_result = generate_experience_bullet_points(
        experience=active_experience,
        config=load_generation_config(second_config_path),
        job_target=load_job_target(job_path),
        cache=cache,
    )

    assert len(requests) == 1
    assert requests[0]["dev_mode"] is True
    assert requests[0]["llm_max_output_tokens"] == 111
    assert first_result[0].details is None
    assert second_result[0].details == {
        "method": "llm",
        "_bulletpoints_llm": {"total_tokens": 13},
    }


def test_project_bullet_cache_reuses_when_count_is_inside_requested_range(
    monkeypatch,
    tmp_path,
):
    cache = ResumeGenerationStageCache(tmp_path / "cache")
    first_config_payload = _config_payload()
    first_config_payload["project_bullet_point_generation"]["bullet_count_range"] = {
        "min": 3,
        "max": 3,
    }
    first_config_path = _write_yaml(tmp_path / "first-config.yaml", first_config_payload)
    second_config_payload = _config_payload()
    second_config_payload["project_bullet_point_generation"]["bullet_count_range"] = {
        "min": 2,
        "max": 4,
    }
    second_config_path = _write_yaml(tmp_path / "second-config.yaml", second_config_payload)
    job_path = _write_yaml(tmp_path / "job.yaml", _job_target_payload())
    projects_path = _write_yaml(tmp_path / "projects.yaml", _projects_payload())
    skills_path = _write_yaml(tmp_path / "skills.yaml", _skills_payload())
    selected_project = _loaded_evidence(projects_path, skills_path)[
        "projects"
    ].projects_by_id()["active-project"]
    requests: list[dict] = []

    class FakeClient:
        def __init__(self, *, base_url: str, timeout: float):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return None

        def post(self, endpoint: str, json: dict):
            requests.append(json)
            return httpx.Response(
                200,
                json={
                    "bullet_points": [
                        "Project bullet one.",
                        "Project bullet two.",
                        "Project bullet three.",
                    ],
                    "details": {"_bulletpoints_llm": {"total_tokens": 21}},
                },
            )

    monkeypatch.setattr("resume_generation.bullet_points.httpx.Client", FakeClient)

    first_result = generate_project_bullet_points(
        selected_projects=[selected_project],
        config=load_generation_config(first_config_path),
        job_target=load_job_target(job_path),
        cache=cache,
    )
    second_result = generate_project_bullet_points(
        selected_projects=[selected_project],
        config=load_generation_config(second_config_path),
        job_target=load_job_target(job_path),
        cache=cache,
    )

    assert len(requests) == 1
    assert requests[0]["bullet_count_range"] == {"min": 3, "max": 3}
    assert len(first_result[0].bullet_points) == 3
    assert len(second_result[0].bullet_points) == 3


def test_project_bullet_cache_refreshes_when_count_is_outside_requested_range(
    monkeypatch,
    tmp_path,
):
    cache = ResumeGenerationStageCache(tmp_path / "cache")
    first_config_payload = _config_payload()
    first_config_payload["project_bullet_point_generation"]["bullet_count_range"] = {
        "min": 2,
        "max": 2,
    }
    first_config_path = _write_yaml(tmp_path / "first-config.yaml", first_config_payload)
    second_config_payload = _config_payload()
    second_config_payload["project_bullet_point_generation"]["bullet_count_range"] = {
        "min": 3,
        "max": 3,
    }
    second_config_path = _write_yaml(tmp_path / "second-config.yaml", second_config_payload)
    job_path = _write_yaml(tmp_path / "job.yaml", _job_target_payload())
    projects_path = _write_yaml(tmp_path / "projects.yaml", _projects_payload())
    skills_path = _write_yaml(tmp_path / "skills.yaml", _skills_payload())
    selected_project = _loaded_evidence(projects_path, skills_path)[
        "projects"
    ].projects_by_id()["active-project"]
    requests: list[dict] = []

    class FakeClient:
        def __init__(self, *, base_url: str, timeout: float):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return None

        def post(self, endpoint: str, json: dict):
            requests.append(json)
            bullet_count = json["bullet_count_range"]["min"]
            return httpx.Response(
                200,
                json={
                    "bullet_points": [
                        f"Project bullet {index}."
                        for index in range(1, bullet_count + 1)
                    ],
                    "details": {"_bulletpoints_llm": {"total_tokens": 21}},
                },
            )

    monkeypatch.setattr("resume_generation.bullet_points.httpx.Client", FakeClient)

    first_result = generate_project_bullet_points(
        selected_projects=[selected_project],
        config=load_generation_config(first_config_path),
        job_target=load_job_target(job_path),
        cache=cache,
    )
    second_result = generate_project_bullet_points(
        selected_projects=[selected_project],
        config=load_generation_config(second_config_path),
        job_target=load_job_target(job_path),
        cache=cache,
    )
    third_result = generate_project_bullet_points(
        selected_projects=[selected_project],
        config=load_generation_config(second_config_path),
        job_target=load_job_target(job_path),
        cache=cache,
    )

    assert [request["bullet_count_range"] for request in requests] == [
        {"min": 2, "max": 2},
        {"min": 3, "max": 3},
    ]
    assert len(first_result[0].bullet_points) == 2
    assert len(second_result[0].bullet_points) == 3
    assert len(third_result[0].bullet_points) == 3


def test_project_bullet_cache_invalidates_when_evidence_payload_changes(
    monkeypatch,
    tmp_path,
):
    cache = ResumeGenerationStageCache(tmp_path / "cache")
    config_path = _write_yaml(tmp_path / "config.yaml", _config_payload())
    job_path = _write_yaml(tmp_path / "job.yaml", _job_target_payload())
    projects_path = _write_yaml(tmp_path / "projects.yaml", _projects_payload())
    skills_path = _write_yaml(tmp_path / "skills.yaml", _skills_payload())
    selected_project = _loaded_evidence(projects_path, skills_path)[
        "projects"
    ].projects_by_id()["active-project"]
    updated_project = selected_project.model_copy(
        update={"summary": "FastAPI backend service with Redis caching."}
    )
    requests: list[dict] = []

    class FakeClient:
        def __init__(self, *, base_url: str, timeout: float):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return None

        def post(self, endpoint: str, json: dict):
            requests.append(json)
            return httpx.Response(
                200,
                json={
                    "bullet_points": ["Project bullet one.", "Project bullet two."],
                    "details": {"_bulletpoints_llm": {"total_tokens": 21}},
                },
            )

    monkeypatch.setattr("resume_generation.bullet_points.httpx.Client", FakeClient)

    generate_project_bullet_points(
        selected_projects=[selected_project],
        config=load_generation_config(config_path),
        job_target=load_job_target(job_path),
        cache=cache,
    )
    generate_project_bullet_points(
        selected_projects=[updated_project],
        config=load_generation_config(config_path),
        job_target=load_job_target(job_path),
        cache=cache,
    )

    assert [request["project"]["summary"] for request in requests] == [
        "FastAPI backend service.",
        "FastAPI backend service with Redis caching.",
    ]


def test_extract_response_token_usage_reads_stage_metadata():
    skill_usage = extract_response_token_usage(
        "skill_selection",
        {
            "details": {
                "_llm": {
                    "prompt_tokens": "11",
                    "completion_tokens": 7,
                    "total_tokens": 18,
                    "api_calls": 1,
                    "latency_ms": "31.25",
                }
            }
        },
    )
    project_usage = extract_response_token_usage(
        "project_selection",
        {"details": {"_project_llm": {"total_tokens": 22}}},
    )
    link_usage = extract_response_token_usage(
        "link_scanning",
        {"details": {"_link_scanning_llm": {"total_tokens": 33}}},
    )
    bullet_usage = extract_response_token_usage(
        "experience_bullet_points",
        {"details": {"_bulletpoints_llm": {"total_tokens": 44}}},
    )
    section_bullet_usage = extract_response_token_usage(
        "resume_section_bullet_points",
        {"details": {"_bulletpoints_llm": {"total_tokens": 55}}},
    )
    missing_usage = extract_response_token_usage(
        "project_bullet_points",
        {"details": {"_bulletpoints_llm": {"total_tokens": "not-a-number"}}},
    )

    assert skill_usage.model_dump() == {
        "prompt_tokens": 11,
        "completion_tokens": 7,
        "total_tokens": 18,
        "api_calls": 1,
        "latency_ms": 31.25,
    }
    assert project_usage.total_tokens == 22
    assert link_usage.total_tokens == 33
    assert bullet_usage.total_tokens == 44
    assert section_bullet_usage.total_tokens == 55
    assert missing_usage.total_tokens == 0


def test_run_link_evidence_enrichment_scans_projects_and_experience_and_writes_yaml(
    tmp_path,
):
    config_path = _write_yaml(tmp_path / "config.yaml", _config_payload())
    projects_path = _write_yaml(tmp_path / "projects.yaml", _projects_payload())
    experience_path = _write_yaml(tmp_path / "experience.yaml", _experience_payload())
    config = load_generation_config(config_path)
    requests = []

    def fake_scan_service(req):
        requests.append(req)
        if req.evidence_type == "project":
            highlights = [
                LinkScanHighlight(
                    text="Built the service.",
                    source_url="https://example.com/active",
                ),
                LinkScanHighlight(
                    text="Scanned README confirms API orchestration.",
                    source_url="https://example.com/active",
                ),
            ]
        else:
            highlights = [
                LinkScanHighlight(
                    text="Company link confirms FastAPI platform work.",
                    source_url="https://example.com/company",
                )
            ]
        return LinkScanResponse(
            evidence_type=req.evidence_type,
            evidence_id=req.evidence.id,
            added_highlights=highlights,
            details={"method": "llm"},
        )

    result = run_link_evidence_enrichment(
        evidence_type="all",
        evidence_paths={
            "projects": projects_path,
            "experience": experience_path,
        },
        config=config,
        highlight_count=7,
        max_tokens_per_highlight=90,
        scan_service=fake_scan_service,
    )

    assert [(req.evidence_type, req.evidence.id) for req in requests] == [
        ("project", "active-project"),
        ("experience", "backend-engineer"),
    ]
    assert all(req.requested_highlight_count == 7 for req in requests)
    assert all(req.max_tokens_per_highlight == 90 for req in requests)
    assert result.scanned_count == 2
    assert result.total_added_highlights == 2
    assert set(result.updated_paths) == {str(projects_path), str(experience_path)}

    projects_file = load_evidence_yaml(projects_path, "projects")
    experience_file = load_evidence_yaml(experience_path, "experience")
    assert projects_file.projects_by_id()["active-project"].highlights == [
        "Built the service.",
        "Scanned README confirms API orchestration.",
    ]
    assert projects_file.projects_by_id()["inactive-project"].highlights == [
        "Built the frontend."
    ]
    assert experience_file.experience_by_id()["backend-engineer"].highlights == [
        "Designed schema-validated APIs.",
        "Company link confirms FastAPI platform work.",
    ]


def test_run_link_evidence_enrichment_dry_run_does_not_write_yaml(tmp_path):
    config_path = _write_yaml(tmp_path / "config.yaml", _config_payload())
    projects_path = _write_yaml(tmp_path / "projects.yaml", _projects_payload())
    config = load_generation_config(config_path)

    def fake_scan_service(req):
        return LinkScanResponse(
            evidence_type=req.evidence_type,
            evidence_id=req.evidence.id,
            added_highlights=[
                LinkScanHighlight(
                    text="Dry-run scanned detail.",
                    source_url="https://example.com/active",
                )
            ],
            details=None,
        )

    result = run_link_evidence_enrichment(
        evidence_type="projects",
        evidence_paths={"projects": projects_path},
        config=config,
        dry_run=True,
        scan_service=fake_scan_service,
    )

    assert result.dry_run is True
    assert result.total_added_highlights == 1
    assert result.updated_paths == ()
    projects_file = load_evidence_yaml(projects_path, "projects")
    assert projects_file.projects_by_id()["active-project"].highlights == [
        "Built the service."
    ]


def test_run_link_evidence_enrichment_scans_only_target_record(tmp_path):
    config_path = _write_yaml(tmp_path / "config.yaml", _config_payload())
    projects_payload = _projects_payload()
    projects_payload["projects"].append(
        {
            "id": "second-project",
            "name": "Second Project",
            "summary": "Second FastAPI backend service.",
            "highlights": ["Built another service."],
            "active": True,
            "skills": {
                "technology": ["FastAPI"],
                "programming": ["Python"],
                "concepts": ["API"],
            },
            "links": ["https://example.com/second"],
        }
    )
    projects_path = _write_yaml(tmp_path / "projects.yaml", projects_payload)
    config = load_generation_config(config_path)
    requests = []

    def fake_scan_service(req):
        requests.append(req)
        return LinkScanResponse(
            evidence_type=req.evidence_type,
            evidence_id=req.evidence.id,
            added_highlights=[
                LinkScanHighlight(
                    text="Second project scanned detail.",
                    source_url="https://example.com/second",
                )
            ],
            details=None,
        )

    result = run_link_evidence_enrichment(
        evidence_type="projects",
        evidence_id="second-project",
        evidence_paths={"projects": projects_path},
        config=config,
        scan_service=fake_scan_service,
    )

    assert [(req.evidence_type, req.evidence.id) for req in requests] == [
        ("project", "second-project")
    ]
    assert result.scanned_count == 1
    assert result.total_added_highlights == 1
    projects_file = load_evidence_yaml(projects_path, "projects")
    assert projects_file.projects_by_id()["active-project"].highlights == [
        "Built the service."
    ]
    assert projects_file.projects_by_id()["second-project"].highlights == [
        "Built another service.",
        "Second project scanned detail.",
    ]


def test_run_link_evidence_enrichment_rejects_invalid_targeting(tmp_path):
    config_path = _write_yaml(tmp_path / "config.yaml", _config_payload())
    projects_path = _write_yaml(tmp_path / "projects.yaml", _projects_payload())
    config = load_generation_config(config_path)

    with pytest.raises(ValueError, match="evidence_id requires"):
        run_link_evidence_enrichment(
            evidence_type="all",
            evidence_id="active-project",
            evidence_paths={"projects": projects_path},
            config=config,
        )

    with pytest.raises(ValueError, match="No projects evidence record found"):
        run_link_evidence_enrichment(
            evidence_type="projects",
            evidence_id="missing-project",
            evidence_paths={"projects": projects_path},
            config=config,
        )


def test_enrich_main_uses_link_scanning_config_defaults(tmp_path, monkeypatch):
    payload = _config_payload()
    payload["link_scanning"] = {
        "enabled": False,
        "dev_mode": False,
        "llm_model": "configured-link-model",
        "llm_max_output_tokens": None,
        "highlight_count": 4,
        "max_tokens_per_highlight": 80,
    }
    config_path = _write_yaml(tmp_path / "config.yaml", payload)
    captured: dict[str, object] = {}

    def fake_run_link_evidence_enrichment(**kwargs):
        captured.update(kwargs)
        return resume_enrich.LinkEvidenceEnrichmentResult(
            dry_run=bool(kwargs["dry_run"]),
            records=(),
            updated_paths=(),
        )

    monkeypatch.setattr(
        resume_enrich,
        "run_link_evidence_enrichment",
        fake_run_link_evidence_enrichment,
    )

    exit_code = resume_enrich.main(["--config-path", str(config_path), "--dry-run"])

    assert exit_code == 0
    assert isinstance(captured["config"], ResumeGenerationConfig)
    assert captured["dev_mode"] is False
    assert captured["llm_model"] == "configured-link-model"
    assert captured["llm_max_output_tokens"] is None
    assert captured["highlight_count"] == 4
    assert captured["max_tokens_per_highlight"] == 80


def test_enrich_main_cli_args_override_link_scanning_config(tmp_path, monkeypatch):
    payload = _config_payload()
    payload["link_scanning"] = {
        "enabled": False,
        "dev_mode": True,
        "llm_model": "configured-link-model",
        "llm_max_output_tokens": 660,
        "highlight_count": 4,
        "max_tokens_per_highlight": 80,
    }
    config_path = _write_yaml(tmp_path / "config.yaml", payload)
    captured: dict[str, object] = {}

    def fake_run_link_evidence_enrichment(**kwargs):
        captured.update(kwargs)
        return resume_enrich.LinkEvidenceEnrichmentResult(
            dry_run=bool(kwargs["dry_run"]),
            records=(),
            updated_paths=(),
        )

    monkeypatch.setattr(
        resume_enrich,
        "run_link_evidence_enrichment",
        fake_run_link_evidence_enrichment,
    )

    exit_code = resume_enrich.main(
        [
            "--config-path",
            str(config_path),
            "--no-dev-mode",
            "--llm-model",
            "cli-link-model",
            "--llm-max-output-tokens",
            "222",
            "--highlight-count",
            "9",
            "--max-tokens-per-highlight",
            "77",
        ]
    )

    assert exit_code == 0
    assert captured["dev_mode"] is False
    assert captured["llm_model"] == "cli-link-model"
    assert captured["llm_max_output_tokens"] == 222
    assert captured["highlight_count"] == 9
    assert captured["max_tokens_per_highlight"] == 77


def test_enrich_module_help_does_not_emit_runpy_warning(tmp_path):
    config_path = _write_yaml(tmp_path / "config.yaml", _config_payload())

    completed = subprocess.run(
        [
            sys.executable,
            "-W",
            "error",
            "-m",
            "resume_generation.enrich",
            "--config-path",
            str(config_path),
            "--help",
        ],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "RuntimeWarning" not in completed.stderr
    assert "Enrich project and experience evidence" in completed.stdout


def test_assemble_intermediate_resume_result_builds_deterministic_schema(tmp_path):
    config_path = _write_yaml(tmp_path / "config.yaml", _config_payload())
    job_path = _write_yaml(tmp_path / "job.yaml", _job_target_payload())
    projects_path = _write_yaml(tmp_path / "projects.yaml", _projects_payload())
    skills_path = _write_yaml(tmp_path / "skills.yaml", _skills_payload())
    user_path = _write_yaml(
        tmp_path / "user.yaml",
        {
            **_user_payload(),
            "website": "https://example.com",
        },
    )
    experience_payload = _experience_payload()
    experience_payload["experience"][0]["skills"] = {
        "technology": ["FastAPI", "Docker"],
        "programming": ["Python", "SQL"],
        "concepts": ["API", "Testing"],
    }
    experience_payload["experience"].append(
        {
            "id": "inactive-role",
            "name": "Inactive Company",
            "role": "Frontend Engineer",
            "summary": "Older inactive experience.",
            "highlights": ["This should not appear."],
            "active": False,
            "skills": {
                "technology": ["Angular"],
                "programming": ["JavaScript"],
                "concepts": ["UI"],
            },
            "location": "Remote",
            "start": "2022",
            "end": "2023",
            "links": None,
        }
    )
    education_path = _write_yaml(tmp_path / "education.yaml", _education_payload())
    experience_path = _write_yaml(tmp_path / "experience.yaml", experience_payload)
    loaded_evidence = _loaded_evidence(
        projects_path,
        skills_path,
        user_path=user_path,
        education_path=education_path,
        experience_path=experience_path,
    )
    projects_file = loaded_evidence["projects"]
    unlinked_project = projects_file.projects_by_id()["inactive-project"]
    linked_project = projects_file.projects_by_id()["active-project"]
    selection_context = ResumeSelectionContext(
        job_target=load_job_target(job_path),
        selected_skills=SkillSelectionResult(
            technology=["FastAPI", "Django"],
            programming=["Python"],
            concepts=["API"],
        ),
        project_selection=ProjectSelectionResult(
            selected_project_ids=["inactive-project", "active-project"],
            ranked_projects=[
                {"project_id": "inactive-project", "score": 1.0, "method": "baseline"},
                {"project_id": "active-project", "score": 0.9, "method": "baseline"},
            ],
        ),
        selected_projects=[unlinked_project, linked_project],
        config_path=config_path,
        job_target_path=job_path,
        evidence_paths={
            "projects": projects_path,
            "skills": skills_path,
            "user": user_path,
            "education": education_path,
            "experience": experience_path,
        },
    )

    result = assemble_intermediate_resume_result(
        user_info=loaded_evidence["user"],
        education=loaded_evidence["education"],
        experience=loaded_evidence["experience"],
        selection_context=selection_context,
        selected_projects=[unlinked_project, linked_project],
        project_bullet_points=[
            ProjectBulletPointResult(
                project_id="inactive-project",
                bullet_points=["Generated bullet for inactive-project."],
            ),
            ProjectBulletPointResult(
                project_id="active-project",
                bullet_points=["Generated bullet for active-project."],
            ),
        ],
        experience_bullet_points=[
            ExperienceBulletPointResult(
                experience_id="backend-engineer",
                bullet_points=["Generated bullet for backend-engineer."],
            )
        ],
    )

    assert result.top.model_dump() == {
        "name": "Example Candidate",
        "phone": "+1 555-0100",
        "email": "candidate@example.com",
        "github": "https://github.com/example-candidate",
        "website": "https://example.com",
        "linkedin": "https://www.linkedin.com/in/example-candidate",
    }
    assert [item.name for item in result.education] == ["Example University"]
    assert result.education[0].relevant_coursework == ["Data Structures", "Algorithms"]
    assert [item.name for item in result.experience] == ["Example Company"]
    assert result.experience[0].role == "Backend Engineer"
    assert result.experience[0].bullet_points == ["Generated bullet for backend-engineer."]
    assert result.experience[0].skills == [
        "FastAPI",
        "Docker",
        "Python",
        "SQL",
        "API",
        "Testing",
    ]
    assert [project.name for project in result.projects] == [
        "Inactive Project",
        "Active Project",
    ]
    assert result.projects[0].bullet_points == ["Generated bullet for inactive-project."]
    assert result.projects[0].skills == ["Angular", "JavaScript", "UI"]
    assert result.projects[0].links == []
    assert result.projects[1].links == ["https://example.com/active"]
    assert result.skills.model_dump() == {
        "technology": ["FastAPI", "Django"],
        "programming": ["Python"],
        "concepts": ["API"],
    }


def test_write_resume_result_artifact_writes_human_readable_json(tmp_path):
    resume_result = IntermediateResumeResult.model_validate(
        {
            "top": {
                "name": "Example Candidate",
                "phone": "+1 555-0100",
                "email": "candidate@example.com",
                "github": "https://github.com/example-candidate",
            },
            "education": [
                {
                    "name": "Example University",
                    "degree": "Bachelor of Science in Computer Science",
                    "grade": "3.8 GPA",
                    "start": "2020",
                    "end": "2024",
                    "location": "Example City, ST",
                    "relevant_coursework": ["Data Structures"],
                }
            ],
            "experience": [
                {
                    "name": "Example Company",
                    "role": "Backend Engineer",
                    "bullet_points": ["Designed schema-validated APIs."],
                    "skills": ["FastAPI", "Python"],
                    "location": "Example City, ST",
                    "start": "2024",
                }
            ],
            "projects": [
                {
                    "name": "Active Project",
                    "bullet_points": ["Generated bullet for active-project."],
                    "skills": ["FastAPI", "Python", "API"],
                    "links": ["https://example.com/active"],
                }
            ],
            "skills": {
                "technology": ["FastAPI"],
                "programming": ["Python"],
                "concepts": ["API"],
            },
        }
    )
    artifact_path = tmp_path / "artifacts" / "resume_result.json"

    written_path = write_resume_result_artifact(resume_result, artifact_path)

    assert written_path == artifact_path
    raw_json = artifact_path.read_text(encoding="utf-8")
    assert raw_json.endswith("\n")
    assert '\n  "top": {' in raw_json
    payload = json.loads(raw_json)
    assert list(payload) == ["top", "education", "experience", "projects", "skills"]
    assert payload["top"]["name"] == "Example Candidate"
    assert payload["projects"][0]["bullet_points"] == [
        "Generated bullet for active-project."
    ]


def test_latex_escape_escapes_reserved_characters():
    assert latex_escape("&%$_#{}") == r"\&\%\$\_\#\{\}"
    assert latex_escape("Path \\ value ~ caret ^") == (
        r"Path \textbackslash{} value \textasciitilde{} caret \textasciicircum{}"
    )


def test_latex_escape_normalizes_unicode_punctuation_for_pdflatex():
    text = (
        "Runtime \u2248 2 minutes \u2192 dashboards \u2014 "
        "\u201crole\u2011specific\u201d \u2022 shipped \U0001f680"
    )

    escaped = latex_escape(text)

    assert escaped == 'Runtime about 2 minutes to dashboards - "role-specific" - shipped'
    assert "\u2248" not in escaped
    assert "\u2192" not in escaped
    assert "\u2014" not in escaped
    assert "\u2011" not in escaped
    assert "\u2022" not in escaped
    assert "\U0001f680" not in escaped


def test_render_resume_latex_uses_template_sections_and_runtime_result():
    resume_result = _sample_intermediate_resume_result()

    rendered = render_resume_latex(resume_result)

    assert rendered.startswith("\\documentclass[letterpaper,9pt]{article}")
    assert rendered.endswith("\\end{document}\n")
    assert "\\section{Education}" in rendered
    assert "\\section{Experience}" in rendered
    assert "\\section{Projects}" in rendered
    assert "\\section{Technical Skills}" in rendered
    assert r"\newsavebox{\resumeHeaderBox}" in rendered
    assert r"\newcommand{\resumeHeaderLine}[1]" in rendered
    assert r"\setlength{\footskip}{4pt}" in rendered
    assert r"\textbf{\Large \scshape Example Candidate}" in rendered
    assert r"{\seticon{faEnvelope} candidate\_name@example.com}" in rendered
    assert r"{\seticon{faPhone} +1 555-0100}" in rendered
    assert r"{\seticon{faGithub} \underline{github.com/example-candidate}}" in rendered
    assert "faLinkedin" not in rendered
    assert "faGlobe" not in rendered
    assert r"{Example \& University}{2020 -- 2024}" in rendered
    assert (
        r"\resumeItem{\textbf{Relevant Coursework:} Data Structures, Algorithms}"
        in rendered
    )
    assert r"\resumeExperienceSubheading" in rendered
    assert r"{Example Company}{Backend Engineer}{2024 -- Present}" in rendered
    assert r"{FastAPI, Python}{Example City, ST}" in rendered
    assert (
        r"{Backend Engineer $|$ \emph{FastAPI, Python}}{Example City, ST}"
        not in rendered
    )
    assert r"\resumeItem{Designed schema-validated APIs \& workers.}" in rendered
    assert (
        r"{\textbf{Active Project} $|$ \emph{FastAPI, Python, API}}{}"
        in rendered
    )
    assert r"\resumeItem{Generated bullet for active\_project.}" in rendered
    assert (
        rendered.index("\\section{Education}")
        < rendered.index("\\section{Experience}")
        < rendered.index("\\section{Projects}")
        < rendered.index("\\section{Technical Skills}")
    )


def test_render_resume_latex_keeps_contact_and_profiles_on_one_header_line():
    payload = _sample_intermediate_resume_result().model_dump()
    payload["top"].update(
        {
            "linkedin": "https://www.linkedin.com/in/example-candidate/",
            "website": "https://www.example.dev/",
        }
    )
    resume_result = IntermediateResumeResult.model_validate(payload)

    rendered = render_resume_latex(resume_result)

    header_line = next(
        line.strip()
        for line in rendered.splitlines()
        if line.strip().startswith(r"\resumeHeaderLine")
    )
    assert header_line == (
        r"\resumeHeaderLine{{\seticon{faEnvelope} candidate\_name@example.com}"
        r"\hspace{0.75em}{\seticon{faPhone} +1 555-0100}"
        r"\hspace{0.75em}{\seticon{faLinkedin} "
        r"\underline{linkedin.com/in/example-candidate}}"
        r"\hspace{0.75em}{\seticon{faGithub} "
        r"\underline{github.com/example-candidate}}"
        r"\hspace{0.75em}{\seticon{faGlobe} \underline{example.dev}}}"
    )
    assert r"\\quad" not in header_line
    assert r"\resizebox{\textwidth}{!}{\usebox{\resumeHeaderBox}}" in rendered


def test_render_resume_latex_uses_wrapping_heading_columns_for_long_skill_suffixes():
    payload = _sample_intermediate_resume_result().model_dump()
    long_experience_skills = [
        "Julia",
        "Python",
        "Error Correcting Codes",
        "Quantum Error Correction",
        "Distributed Computing",
        "High Performance Computing",
        "Slurm Cluster",
        "Benchmarking",
        "System Administration",
        "DevOps",
        "Web Development",
        "Database Management",
    ]
    long_project_skills = [
        "FastAPI",
        "Supabase",
        "NextJS",
        "Pydantic",
        "Docker",
        "Python",
        "TypeScript",
        "SQL",
        "REST API",
        "Authentication",
        "Database Management",
        "LLM",
    ]
    payload["experience"][0].update(
        {
            "role": "Research Software Engineer - Quantum Information",
            "skills": long_experience_skills,
            "location": "Nuremberg, Bavaria, Germany",
            "start": "June 2025",
            "end": "August 2025",
        }
    )
    payload["projects"][0].update(
        {
            "name": "Community Funding Operations Dashboard",
            "skills": long_project_skills,
        }
    )
    resume_result = IntermediateResumeResult.model_validate(payload)

    rendered = render_resume_latex(resume_result)

    assert r"\newcolumntype{L}{>{\raggedright\arraybackslash}X}" in rendered
    assert r"\newcolumntype{R}[1]{>{\raggedleft\arraybackslash}p{#1}}" in rendered
    assert r"\newcommand{\resumeHeadingRightWidth}{1.75in}" in rendered
    assert r"\newcommand{\resumeExperienceSubheading}[5]" in rendered
    assert (
        r"\begin{tabularx}{0.97\textwidth}[t]{@{}L R{\resumeHeadingRightWidth}@{}}"
        in rendered
    )
    assert (
        r"\begin{tabularx}{0.97\textwidth}{@{}L R{\resumeHeadingRightWidth}@{}}"
        in rendered
    )
    assert r"\begin{tabularx}{0.97\textwidth}{@{}L@{}}" in rendered
    assert (
        r"{Example Company}{Research Software Engineer - Quantum Information}"
        r"{June 2025 -- August 2025}"
        in rendered
    )
    assert (
        r"{Julia, Python, Error Correcting Codes, Quantum Error Correction, "
        r"Distributed Computing"
        in rendered
    )
    assert r"\small#1 & #2 \\" not in rendered
    assert r"\begin{tabular*}{0.97\textwidth}" not in rendered
    for skill in long_experience_skills + long_project_skills:
        assert latex_escape(skill) in rendered


def test_render_resume_latex_sanitizes_generated_bullet_text():
    payload = _sample_intermediate_resume_result().model_dump()
    payload["experience"][0]["bullet_points"] = [
        "Improved applicant \u2192 admin flow with role\u2011specific data views.",
    ]
    payload["projects"][0]["bullet_points"] = [
        "Reduced analysis runtime \u2248 2 minutes \u2014 shipped dashboard output \U0001f680.",
    ]
    resume_result = IntermediateResumeResult.model_validate(payload)

    rendered = render_resume_latex(resume_result)

    assert (
        r"\resumeItem{Improved applicant to admin flow with role-specific data views.}"
        in rendered
    )
    assert (
        r"\resumeItem{Reduced analysis runtime about 2 minutes - shipped dashboard output.}"
        in rendered
    )
    assert "\u2192" not in rendered
    assert "\u2248" not in rendered
    assert "\u2014" not in rendered
    assert "\U0001f680" not in rendered


def test_write_resume_latex_artifact_writes_tex_file(tmp_path):
    resume_result = _sample_intermediate_resume_result()
    artifact_path = tmp_path / "artifacts" / "resume.tex"

    written_path = write_resume_latex_artifact(resume_result, artifact_path)

    assert written_path == artifact_path
    rendered = artifact_path.read_text(encoding="utf-8")
    assert rendered.startswith("\\documentclass[letterpaper,9pt]{article}")
    assert rendered.endswith("\\end{document}\n")
    assert "\\section{Projects}" in rendered


def test_write_resume_latex_from_config_writes_artifact_and_configured_output(
    monkeypatch,
    tmp_path,
    caplog,
):
    generation_root = tmp_path / "resume_generation"
    monkeypatch.setattr(settings, "RESUME_GENERATION_ROOT", generation_root)
    resume_result = _sample_intermediate_resume_result()
    output_dir = tmp_path / "out"
    output_path = output_dir / "resume.tex"
    artifact_path = generation_root / "artifacts" / "resume.tex"
    config_path = _write_yaml(
        tmp_path / "config.yaml",
        _config_payload(resume_output={"output_dir": str(output_dir)}),
    )

    with caplog.at_level(logging.INFO, logger="resume_generation"):
        written_path = write_resume_latex_from_config(
            resume_result,
            config_path=config_path,
        )

    assert written_path == output_path
    assert artifact_path.read_text(encoding="utf-8").endswith("\\end{document}\n")
    assert output_path.read_text(encoding="utf-8").endswith("\\end{document}\n")
    artifact_records = [
        record
        for record in caplog.records
        if getattr(record, "event", None) == "resume_generation_latex_artifact_written"
    ]
    output_records = [
        record
        for record in caplog.records
        if getattr(record, "event", None) == "resume_generation_latex_output_written"
    ]
    assert len(artifact_records) == 1
    assert artifact_records[0].path == str(artifact_path)
    assert len(output_records) == 1
    assert output_records[0].path == str(output_path)


def test_render_latex_pdf_local_runs_latexmk_and_writes_pdf(monkeypatch, tmp_path):
    tex_path = tmp_path / "resume.tex"
    pdf_path = tmp_path / "out" / "resume.pdf"
    tex_path.write_text("\\documentclass{article}\\begin{document}Hi\\end{document}\n")
    captured: dict[str, object] = {}

    def fake_run(command, *, cwd, check, capture_output, text, timeout):
        captured["command"] = command
        captured["cwd"] = cwd
        captured["check"] = check
        captured["capture_output"] = capture_output
        captured["text"] = text
        captured["timeout"] = timeout
        output_dir_arg = next(part for part in command if part.startswith("-outdir="))
        output_dir = Path(output_dir_arg.removeprefix("-outdir="))
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "resume.pdf").write_bytes(b"%PDF-1.4\n")
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    monkeypatch.setattr("resume_generation.pdf.subprocess.run", fake_run)

    written_path = render_latex_pdf(
        tex_path,
        pdf_path,
        timeout_seconds=12,
    )

    assert written_path == pdf_path
    assert pdf_path.read_bytes() == b"%PDF-1.4\n"
    assert captured["command"] == [
        "latexmk",
        "-pdf",
        "-interaction=nonstopmode",
        "-halt-on-error",
        captured["command"][4],
        "resume.tex",
    ]
    assert str(captured["command"][4]).startswith("-outdir=")
    assert captured["cwd"] == tmp_path
    assert captured["check"] is False
    assert captured["capture_output"] is True
    assert captured["text"] is True
    assert captured["timeout"] == 12


def test_render_latex_pdf_local_raises_for_compile_failure(monkeypatch, tmp_path):
    tex_path = tmp_path / "resume.tex"
    tex_path.write_text("\\documentclass{article}\\begin{document}Hi\\end{document}\n")

    def fake_run(command, *, cwd, check, capture_output, text, timeout):
        output_dir_arg = next(part for part in command if part.startswith("-outdir="))
        output_dir = Path(output_dir_arg.removeprefix("-outdir="))
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "resume.log").write_text("Undefined control sequence")
        return subprocess.CompletedProcess(
            command,
            12,
            stdout="latexmk stdout",
            stderr="latexmk stderr",
        )

    monkeypatch.setattr("resume_generation.pdf.subprocess.run", fake_run)

    with pytest.raises(LatexPdfRenderError, match="Undefined control sequence"):
        render_latex_pdf(tex_path, tmp_path / "resume.pdf")


def test_render_latex_pdf_local_raises_for_missing_command(monkeypatch, tmp_path):
    tex_path = tmp_path / "resume.tex"
    tex_path.write_text("\\documentclass{article}\\begin{document}Hi\\end{document}\n")

    def fake_run(command, *, cwd, check, capture_output, text, timeout):
        raise FileNotFoundError(command[0])

    monkeypatch.setattr("resume_generation.pdf.subprocess.run", fake_run)

    with pytest.raises(LatexPdfRenderError, match="command not found: latexmk"):
        render_latex_pdf(tex_path, tmp_path / "resume.pdf")


def test_render_latex_pdf_local_classifies_missing_tex_package(monkeypatch, tmp_path):
    tex_path = tmp_path / "resume.tex"
    tex_path.write_text("\\documentclass{article}\\begin{document}Hi\\end{document}\n")

    def fake_run(command, *, cwd, check, capture_output, text, timeout):
        output_dir_arg = next(part for part in command if part.startswith("-outdir="))
        output_dir = Path(output_dir_arg.removeprefix("-outdir="))
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "resume.log").write_text(
            "! LaTeX Error: File `fontawesome5.sty' not found."
        )
        return subprocess.CompletedProcess(command, 12, stdout="", stderr="")

    monkeypatch.setattr("resume_generation.pdf.subprocess.run", fake_run)

    with pytest.raises(LatexPdfPrerequisiteError, match="PDF rendering prerequisites"):
        render_latex_pdf(tex_path, tmp_path / "resume.pdf")


def test_write_resume_pdf_from_config_skips_when_disabled(tmp_path, caplog):
    tex_path = tmp_path / "resume.tex"
    tex_path.write_text("\\documentclass{article}\\begin{document}Hi\\end{document}\n")
    config_path = _write_yaml(tmp_path / "config.yaml", _config_payload())

    with caplog.at_level(logging.INFO, logger="resume_generation"):
        written_path = write_resume_pdf_from_config(tex_path, config_path=config_path)

    assert written_path is None
    records = [
        record
        for record in caplog.records
        if getattr(record, "event", None) == "resume_generation_pdf_render_skipped"
    ]
    assert len(records) == 1


def test_write_resume_pdf_from_config_renders_when_enabled(
    monkeypatch,
    tmp_path,
    caplog,
):
    generation_root = tmp_path / "resume_generation"
    monkeypatch.setattr(settings, "RESUME_GENERATION_ROOT", generation_root)
    tex_path = generation_root / "artifacts" / "resume.tex"
    artifact_pdf_path = generation_root / "artifacts" / "resume.pdf"
    output_dir = tmp_path / "out"
    output_pdf_path = output_dir / "resume.pdf"
    tex_path.parent.mkdir(parents=True, exist_ok=True)
    tex_path.write_text("\\documentclass{article}\\begin{document}Hi\\end{document}\n")
    config_path = _write_yaml(
        tmp_path / "config.yaml",
        _config_payload(
            resume_output={
                "output_dir": str(output_dir),
                "render_pdf": True,
                "pdf_timeout_seconds": 22,
            }
        ),
    )
    calls: list[dict[str, object]] = []

    def fake_render_latex_pdf(
        tex_arg,
        pdf_arg,
        *,
        timeout_seconds,
    ):
        calls.append(
            {
                "tex_arg": tex_arg,
                "pdf_arg": pdf_arg,
                "timeout_seconds": timeout_seconds,
            }
        )
        Path(pdf_arg).parent.mkdir(parents=True, exist_ok=True)
        Path(pdf_arg).write_bytes(b"%PDF-1.4\n")
        return Path(pdf_arg)

    monkeypatch.setattr(
        "resume_generation.main.render_latex_pdf",
        fake_render_latex_pdf,
    )

    with caplog.at_level(logging.INFO, logger="resume_generation"):
        written_path = write_resume_pdf_from_config(tex_path, config_path=config_path)

    assert written_path == output_pdf_path
    assert artifact_pdf_path.read_bytes() == b"%PDF-1.4\n"
    assert output_pdf_path.read_bytes() == b"%PDF-1.4\n"
    assert calls == [
        {
            "tex_arg": tex_path,
            "pdf_arg": artifact_pdf_path,
            "timeout_seconds": 22.0,
        }
    ]
    artifact_records = [
        record
        for record in caplog.records
        if getattr(record, "event", None) == "resume_generation_pdf_artifact_written"
    ]
    output_records = [
        record
        for record in caplog.records
        if getattr(record, "event", None) == "resume_generation_pdf_output_written"
    ]
    assert len(artifact_records) == 1
    assert artifact_records[0].path == str(artifact_pdf_path)
    assert len(output_records) == 1
    assert output_records[0].path == str(output_pdf_path)


def test_resume_pdf_main_uses_default_paths(monkeypatch):
    calls: list[dict[str, object]] = []

    def fake_render_latex_pdf(
        tex_path,
        pdf_path,
        *,
        timeout_seconds,
    ):
        calls.append(
            {
                "tex_path": tex_path,
                "pdf_path": pdf_path,
                "timeout_seconds": timeout_seconds,
            }
        )
        return Path(pdf_path)

    monkeypatch.setattr(sys, "argv", ["python -m resume_generation.pdf"])
    monkeypatch.setattr(resume_pdf, "render_latex_pdf", fake_render_latex_pdf)

    result = resume_pdf.main()

    assert result == resume_pdf.DEFAULT_RESUME_PDF_ARTIFACT_PATH
    assert calls == [
        {
            "tex_path": str(resume_pdf.DEFAULT_RESUME_TEX_INPUT_PATH),
            "pdf_path": str(resume_pdf.DEFAULT_RESUME_PDF_ARTIFACT_PATH),
            "timeout_seconds": resume_pdf.DEFAULT_LATEX_PDF_TIMEOUT_SECONDS,
        }
    ]


def test_generate_project_bullet_points_wraps_http_errors(monkeypatch, tmp_path):
    config_path = _write_yaml(tmp_path / "config.yaml", _config_payload())
    job_path = _write_yaml(tmp_path / "job.yaml", _job_target_payload())
    projects_path = _write_yaml(tmp_path / "projects.yaml", _projects_payload())
    skills_path = _write_yaml(tmp_path / "skills.yaml", _skills_payload())
    config = load_generation_config(config_path)
    job_target = load_job_target(job_path)
    projects_file = _loaded_evidence(projects_path, skills_path)["projects"]
    selected_project = projects_file.projects_by_id()["active-project"]

    class FailingClient:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return None

        def post(self, endpoint: str, json: dict):
            return httpx.Response(502, text="llm down")

    monkeypatch.setattr("resume_generation.bullet_points.httpx.Client", FailingClient)

    with pytest.raises(ResumeGenerationError, match="/generate-bulletpoints returned 502"):
        generate_project_bullet_points(
            selected_projects=[selected_project],
            config=config,
            job_target=job_target,
        )


def test_generate_selection_context_wraps_http_errors(monkeypatch, tmp_path):
    config_path = _write_yaml(tmp_path / "config.yaml", _config_payload())
    job_path = _write_yaml(tmp_path / "job.yaml", _job_target_payload())
    projects_path = _write_yaml(tmp_path / "projects.yaml", _projects_payload())
    skills_path = _write_yaml(tmp_path / "skills.yaml", _skills_payload())
    config = load_generation_config(config_path)
    job_target = load_job_target(job_path)

    class FailingClient:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return None

        def post(self, endpoint: str, json: dict):
            return httpx.Response(500, text="server down")

    monkeypatch.setattr("resume_generation.selection.httpx.Client", FailingClient)

    with pytest.raises(ResumeGenerationError, match="/select-skills returned 500"):
        generate_selection_context(
            loaded_evidence=_loaded_evidence(projects_path, skills_path),
            config=config,
            job_target=job_target,
            config_path=config_path,
            job_target_path=job_path,
            evidence_paths={
                "projects": projects_path,
                "skills": skills_path,
            },
        )


def test_resume_generation_pipeline_requires_loaded_education(monkeypatch, tmp_path):
    config_path = _write_yaml(tmp_path / "config.yaml", _config_payload())
    job_path = _write_yaml(tmp_path / "job.yaml", _job_target_payload())
    projects_path = _write_yaml(tmp_path / "projects.yaml", _projects_payload())
    skills_path = _write_yaml(tmp_path / "skills.yaml", _skills_payload())
    loaded_evidence = _loaded_evidence(projects_path, skills_path)
    del loaded_evidence["education"]
    calls: list[str] = []

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return None

        def post(self, endpoint: str, json: dict):
            calls.append(endpoint)
            raise AssertionError(f"unexpected endpoint: {endpoint}")

    monkeypatch.setattr("resume_generation.selection.httpx.Client", FakeClient)
    monkeypatch.setattr(
        "resume_generation.main.load_registered_evidence",
        lambda paths=None: loaded_evidence,
    )

    with pytest.raises(TypeError, match="valid education file"):
        run_resume_generation_pipeline(
            config_path=config_path,
            job_target_path=job_path,
            evidence_paths={
                "projects": projects_path,
                "skills": skills_path,
            },
        )

    assert calls == []


def test_resume_generation_pipeline_rejects_invalid_loaded_education(monkeypatch, tmp_path):
    config_path = _write_yaml(tmp_path / "config.yaml", _config_payload())
    job_path = _write_yaml(tmp_path / "job.yaml", _job_target_payload())
    projects_path = _write_yaml(tmp_path / "projects.yaml", _projects_payload())
    skills_path = _write_yaml(tmp_path / "skills.yaml", _skills_payload())
    user_path = _write_yaml(tmp_path / "user.yaml", _user_payload())
    loaded_evidence = _loaded_evidence(projects_path, skills_path, user_path=user_path)
    loaded_evidence["education"] = load_evidence_yaml(user_path, "user")
    calls: list[str] = []

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return None

        def post(self, endpoint: str, json: dict):
            calls.append(endpoint)
            raise AssertionError(f"unexpected endpoint: {endpoint}")

    monkeypatch.setattr("resume_generation.selection.httpx.Client", FakeClient)
    monkeypatch.setattr(
        "resume_generation.main.load_registered_evidence",
        lambda paths=None: loaded_evidence,
    )

    with pytest.raises(TypeError, match="valid education file"):
        run_resume_generation_pipeline(
            config_path=config_path,
            job_target_path=job_path,
            evidence_paths={
                "projects": projects_path,
                "skills": skills_path,
            },
        )

    assert calls == []


def test_resume_generation_pipeline_requires_loaded_experience(monkeypatch, tmp_path):
    config_path = _write_yaml(tmp_path / "config.yaml", _config_payload())
    job_path = _write_yaml(tmp_path / "job.yaml", _job_target_payload())
    projects_path = _write_yaml(tmp_path / "projects.yaml", _projects_payload())
    skills_path = _write_yaml(tmp_path / "skills.yaml", _skills_payload())
    loaded_evidence = _loaded_evidence(projects_path, skills_path)
    del loaded_evidence["experience"]
    calls: list[str] = []

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return None

        def post(self, endpoint: str, json: dict):
            calls.append(endpoint)
            raise AssertionError(f"unexpected endpoint: {endpoint}")

    monkeypatch.setattr("resume_generation.selection.httpx.Client", FakeClient)
    monkeypatch.setattr(
        "resume_generation.main.load_registered_evidence",
        lambda paths=None: loaded_evidence,
    )

    with pytest.raises(TypeError, match="valid experience file"):
        run_resume_generation_pipeline(
            config_path=config_path,
            job_target_path=job_path,
            evidence_paths={
                "projects": projects_path,
                "skills": skills_path,
            },
        )

    assert calls == []


def test_resume_generation_pipeline_rejects_invalid_loaded_experience(monkeypatch, tmp_path):
    config_path = _write_yaml(tmp_path / "config.yaml", _config_payload())
    job_path = _write_yaml(tmp_path / "job.yaml", _job_target_payload())
    projects_path = _write_yaml(tmp_path / "projects.yaml", _projects_payload())
    skills_path = _write_yaml(tmp_path / "skills.yaml", _skills_payload())
    user_path = _write_yaml(tmp_path / "user.yaml", _user_payload())
    loaded_evidence = _loaded_evidence(projects_path, skills_path, user_path=user_path)
    loaded_evidence["experience"] = load_evidence_yaml(user_path, "user")
    calls: list[str] = []

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return None

        def post(self, endpoint: str, json: dict):
            calls.append(endpoint)
            raise AssertionError(f"unexpected endpoint: {endpoint}")

    monkeypatch.setattr("resume_generation.selection.httpx.Client", FakeClient)
    monkeypatch.setattr(
        "resume_generation.main.load_registered_evidence",
        lambda paths=None: loaded_evidence,
    )

    with pytest.raises(TypeError, match="valid experience file"):
        run_resume_generation_pipeline(
            config_path=config_path,
            job_target_path=job_path,
            evidence_paths={
                "projects": projects_path,
                "skills": skills_path,
            },
        )

    assert calls == []


def test_resume_generation_pipeline_loads_config_job_and_evidence_once(monkeypatch, tmp_path):
    payload = _config_payload()
    payload["cache"] = {"enabled": False}
    payload["experience_selection"] = {"top_n": 1}
    config_path = _write_yaml(tmp_path / "config.yaml", payload)
    job_path = _write_yaml(tmp_path / "job.yaml", _job_target_payload())
    projects_path = _write_yaml(tmp_path / "projects.yaml", _projects_payload())
    skills_path = _write_yaml(tmp_path / "skills.yaml", _skills_payload())
    experience_payload = _experience_payload()
    experience_payload["experience"].append(
        {
            "id": "platform-engineer",
            "name": "Platform Company",
            "role": "Platform Engineer",
            "summary": "Built platform tooling.",
            "highlights": ["Improved deployment workflows."],
            "active": True,
            "skills": {
                "technology": ["Kubernetes"],
                "programming": ["Python"],
                "concepts": ["CI/CD"],
            },
            "location": "Remote",
            "start": "2023",
            "end": "2024",
            "links": None,
        }
    )
    experience_path = _write_yaml(tmp_path / "experience.yaml", experience_payload)
    loaded_evidence = _loaded_evidence(
        projects_path,
        skills_path,
        experience_path=experience_path,
    )
    calls: list[str] = []

    class FakeClient:
        def __init__(self, *, base_url: str, timeout: float):
            assert base_url == "http://resumecr7.test"
            assert timeout == 5

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return None

        def post(self, endpoint: str, json: dict):
            calls.append(endpoint)
            if endpoint == "/select-skills":
                return httpx.Response(
                    200,
                    json={
                        "technology": ["FastAPI"],
                        "programming": ["Python"],
                        "concepts": ["API"],
                        "details": {
                            "method": "baseline",
                            "_fallback_method": "baseline",
                            "_llm": {"fallback": "baseline"},
                        },
                    },
                )
            if endpoint == "/select-projects":
                return httpx.Response(
                    200,
                    json={
                        "selected_project_ids": ["active-project"],
                        "ranked_projects": [
                            {
                                "project_id": "active-project",
                                "score": 1.0,
                                "method": "llm",
                            }
                        ],
                    },
                )
            if endpoint == "/derive-job-focus":
                return _job_focus_response()
            if endpoint == "/generate-bulletpoints":
                evidence = json.get("project") or json.get("experience")
                return httpx.Response(
                    200,
                    json={
                        "bullet_points": [f"Generated bullet for {evidence['id']}."],
                    },
                )
            raise AssertionError(f"unexpected endpoint: {endpoint}")

    monkeypatch.setattr("resume_generation.selection.httpx.Client", FakeClient)
    monkeypatch.setattr("resume_generation.bullet_points.httpx.Client", FakeClient)
    monkeypatch.setattr(
        "resume_generation.main.load_registered_evidence",
        lambda paths=None: loaded_evidence,
    )
    assembly_calls: list[dict] = []

    def fake_assemble_intermediate_resume_result(**kwargs):
        calls.append("assemble")
        assembly_calls.append(kwargs)
        return IntermediateResumeResult.model_validate(
            {
                "top": {
                    "name": "Example Candidate",
                    "phone": "+1 555-0100",
                    "email": "candidate@example.com",
                },
                "education": [
                    {
                        "name": "Example University",
                        "degree": "Bachelor of Science in Computer Science",
                        "grade": "3.8 GPA",
                        "start": "2020",
                        "end": "2024",
                        "location": "Example City, ST",
                        "relevant_coursework": ["Data Structures"],
                    }
                ],
                "experience": [
                    {
                        "name": "Example Company",
                        "role": "Backend Engineer",
                        "bullet_points": ["Designed schema-validated APIs."],
                        "skills": ["FastAPI", "Python"],
                        "location": "Example City, ST",
                        "start": "2024",
                    }
                ],
                "projects": [
                    {
                        "name": "Active Project",
                        "bullet_points": ["Generated bullet for active-project."],
                        "skills": ["FastAPI", "Python", "API"],
                        "links": ["https://example.com/active"],
                    }
                ],
                "skills": {
                    "technology": ["FastAPI"],
                    "programming": ["Python"],
                    "concepts": ["API"],
                },
            }
        )

    monkeypatch.setattr(
        "resume_generation.main.assemble_intermediate_resume_result",
        fake_assemble_intermediate_resume_result,
    )
    artifact_path = tmp_path / "artifacts" / "resume_result.json"
    manifest_path = tmp_path / "artifacts" / "resume_run_manifest.json"

    result = run_resume_generation_pipeline(
        config_path=config_path,
        job_target_path=job_path,
        evidence_paths={
            "projects": projects_path,
            "skills": skills_path,
        },
        resume_result_artifact_path=artifact_path,
        resume_run_manifest_artifact_path=manifest_path,
    )

    assert calls == [
        "/derive-job-focus",
        "/select-skills",
        "/select-projects",
        "/generate-bulletpoints",
        "/generate-bulletpoints",
        "assemble",
    ]
    assert result.top.name == "Example Candidate"
    artifact_payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert list(artifact_payload) == ["top", "education", "experience", "projects", "skills"]
    assert artifact_payload["top"]["name"] == "Example Candidate"
    assert artifact_payload["projects"][0]["bullet_points"] == [
        "Generated bullet for active-project."
    ]
    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest_payload["schema_version"] == 1
    assert manifest_payload["artifacts"]["resume_result"] == str(artifact_path)
    assert manifest_payload["job_focus"]["required_skills"] == ["Python", "FastAPI"]
    assert manifest_payload["selection"]["skills"]["details"]["_fallback_method"] == "baseline"
    assert manifest_payload["selection"]["project_selection"]["ranked_projects"] == [
        {"method": "llm", "project_id": "active-project", "score": 1.0}
    ]
    assert [
        (record["stage"], record["cache_status"], record["cache_key"])
        for record in manifest_payload["stage_responses"]
        ] == [
            ("job_focus_generation", "disabled", None),
            ("skill_selection", "disabled", None),
            ("project_selection", "disabled", None),
            ("project_bullet_points", "disabled", None),
            ("experience_bullet_points", "disabled", None),
        ]
    assert "token_usage" in manifest_payload
    assert [item.id for item in loaded_evidence["experience"].experience] == [
        "backend-engineer",
        "platform-engineer",
    ]
    assert assembly_calls[0]["user_info"].name == "Example Candidate"
    assert assembly_calls[0]["education"].education[0].name == "Example University"
    assert [item.id for item in assembly_calls[0]["experience"].experience] == [
        "backend-engineer"
    ]
    assert assembly_calls[0]["experience"].experience[0].name == "Example Company"
    assert assembly_calls[0]["selection_context"].selected_skills.technology == [
        "FastAPI"
    ]
    assert [project.id for project in assembly_calls[0]["selected_projects"]] == [
        "active-project"
    ]
    assert [
        item.project_id for item in assembly_calls[0]["project_bullet_points"]
    ] == [
        "active-project"
    ]
    assert assembly_calls[0]["project_bullet_points"][0].bullet_points == [
        "Generated bullet for active-project."
    ]
    assert [
        item.experience_id
        for item in assembly_calls[0]["experience_bullet_points"]
    ] == [
        "backend-engineer"
    ]
    assert assembly_calls[0]["experience_bullet_points"][0].bullet_points == [
        "Generated bullet for backend-engineer."
    ]


def test_run_resume_generation_pipeline_defaults_to_section_batch(
    monkeypatch,
    tmp_path,
):
    config_payload = _config_payload()
    config_payload.pop("bullet_point_generation_strategy")
    config_path = _write_yaml(tmp_path / "config.yaml", config_payload)
    job_path = _write_yaml(tmp_path / "job.yaml", _job_target_payload())
    projects_path = _write_yaml(tmp_path / "projects.yaml", _projects_payload())
    skills_path = _write_yaml(tmp_path / "skills.yaml", _skills_payload())
    loaded_evidence = _loaded_evidence(projects_path, skills_path)
    calls: list[tuple[str, dict]] = []

    class FakeClient:
        def __init__(self, *, base_url: str, timeout: float):
            assert base_url == "http://resumecr7.test"
            assert timeout == 5

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return None

        def post(self, endpoint: str, json: dict):
            calls.append((endpoint, json))
            if endpoint == "/select-skills":
                return httpx.Response(
                    200,
                    json={
                        "technology": ["FastAPI"],
                        "programming": ["Python"],
                        "concepts": ["API"],
                    },
                )
            if endpoint == "/select-projects":
                return httpx.Response(
                    200,
                    json={
                        "selected_project_ids": ["active-project"],
                        "ranked_projects": [
                            {
                                "project_id": "active-project",
                                "score": 1.0,
                                "method": "llm",
                            }
                        ],
                    },
                )
            if endpoint == "/derive-job-focus":
                return _job_focus_response()
            if endpoint == "/generate-resume-section-bulletpoints":
                return httpx.Response(
                    200,
                    json={
                        "project_bullet_points": [
                            {
                                "project_id": "active-project",
                                "bullet_points": ["Generated project batch bullet."],
                            }
                        ],
                        "experience_bullet_points": [
                            {
                                "experience_id": "backend-engineer",
                                "bullet_points": [
                                    "Generated experience batch bullet."
                                ],
                            }
                        ],
                        "details": {
                            "_bulletpoints_llm": {
                                "prompt_tokens": 9,
                                "completion_tokens": 4,
                                "total_tokens": 13,
                                "api_calls": 1,
                                "latency_ms": 25.0,
                            }
                        },
                    },
                )
            raise AssertionError(f"unexpected endpoint: {endpoint}")

    monkeypatch.setattr("resume_generation.selection.httpx.Client", FakeClient)
    monkeypatch.setattr("resume_generation.bullet_points.httpx.Client", FakeClient)
    monkeypatch.setattr(
        "resume_generation.main.load_registered_evidence",
        lambda paths=None: loaded_evidence,
    )
    artifact_path = tmp_path / "artifacts" / "resume_result.json"
    manifest_path = tmp_path / "artifacts" / "resume_run_manifest.json"

    result = run_resume_generation_pipeline(
        config_path=config_path,
        job_target_path=job_path,
        evidence_paths={
            "projects": projects_path,
            "skills": skills_path,
        },
        resume_result_artifact_path=artifact_path,
        resume_run_manifest_artifact_path=manifest_path,
    )

    assert [endpoint for endpoint, _ in calls] == [
        "/derive-job-focus",
        "/select-skills",
        "/select-projects",
        "/generate-resume-section-bulletpoints",
    ]
    batch_payload = calls[-1][1]
    assert calls[1][1]["job_focus"]["required_skills"] == ["Python", "FastAPI"]
    assert calls[2][1]["context"]["job_focus"]["required_skills"] == [
        "Python",
        "FastAPI",
    ]
    assert [project["id"] for project in batch_payload["projects"]] == [
        "active-project"
    ]
    assert [item["id"] for item in batch_payload["experiences"]] == [
        "backend-engineer"
    ]
    assert result.projects[0].bullet_points == ["Generated project batch bullet."]
    assert result.experience[0].bullet_points == [
        "Generated experience batch bullet."
    ]
    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    section_stage = next(
        record
        for record in manifest_payload["stage_responses"]
        if record["stage"] == "resume_section_bullet_points"
    )
    assert section_stage["endpoint"] == "/generate-resume-section-bulletpoints"
    assert manifest_payload["token_usage"]["raw_stages"][
        "resume_section_bullet_points"
    ]["total_tokens"] == 13


def test_run_resume_generation_pipeline_async_starts_section_bullets_before_skill_selection_finishes(
    monkeypatch,
    tmp_path,
):
    config_payload = _config_payload(
        bullet_point_generation_strategy="section_batch",
        cache={"enabled": False},
        concurrency={"llm_requests": 3, "bullet_point_requests": 3},
    )
    config_path = _write_yaml(tmp_path / "config.yaml", config_payload)
    job_path = _write_yaml(tmp_path / "job.yaml", _job_target_payload())
    projects_path = _write_yaml(tmp_path / "projects.yaml", _projects_payload())
    skills_path = _write_yaml(tmp_path / "skills.yaml", _skills_payload())
    loaded_evidence = _loaded_evidence(projects_path, skills_path)
    starts: dict[str, float] = {}
    ends: dict[str, float] = {}

    class FakeAsyncClient:
        def __init__(self, *, base_url: str, timeout: float):
            assert base_url == "http://resumecr7.test"
            assert timeout == 5

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return None

        async def post(self, endpoint: str, json: dict):
            starts[endpoint] = asyncio.get_running_loop().time()
            delay = 0.12 if endpoint == "/select-skills" else 0.02
            await asyncio.sleep(delay)
            ends[endpoint] = asyncio.get_running_loop().time()
            if endpoint == "/select-skills":
                return httpx.Response(
                    200,
                    json={
                        "technology": ["FastAPI"],
                        "programming": ["Python"],
                        "concepts": ["API"],
                        "details": {"_llm": {"total_tokens": 3}},
                    },
                )
            if endpoint == "/select-projects":
                return httpx.Response(
                    200,
                    json={
                        "selected_project_ids": ["active-project"],
                        "ranked_projects": [
                            {
                                "project_id": "active-project",
                                "score": 1.0,
                                "method": "llm",
                            }
                        ],
                        "details": {"_project_llm": {"total_tokens": 5}},
                    },
                )
            if endpoint == "/derive-job-focus":
                return _job_focus_response(total_tokens=7)
            if endpoint == "/generate-resume-section-bulletpoints":
                return httpx.Response(
                    200,
                    json={
                        "project_bullet_points": [
                            {
                                "project_id": "active-project",
                                "bullet_points": ["Generated project batch bullet."],
                            }
                        ],
                        "experience_bullet_points": [
                            {
                                "experience_id": "backend-engineer",
                                "bullet_points": ["Generated experience batch bullet."],
                            }
                        ],
                        "details": {"_bulletpoints_llm": {"total_tokens": 11}},
                    },
                )
            raise AssertionError(f"unexpected endpoint: {endpoint}")

    monkeypatch.setattr("resume_generation.selection.httpx.AsyncClient", FakeAsyncClient)
    monkeypatch.setattr("resume_generation.job_focus.httpx.AsyncClient", FakeAsyncClient)
    monkeypatch.setattr("resume_generation.bullet_points.httpx.AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(
        "resume_generation.main.load_registered_evidence",
        lambda paths=None: loaded_evidence,
    )
    manifest_path = tmp_path / "artifacts" / "resume_run_manifest.json"

    result = asyncio.run(
        run_resume_generation_pipeline_async(
            config_path=config_path,
            job_target_path=job_path,
            evidence_paths={"projects": projects_path, "skills": skills_path},
            resume_result_artifact_path=tmp_path / "artifacts" / "resume_result.json",
            resume_run_manifest_artifact_path=manifest_path,
        )
    )

    assert result.projects[0].bullet_points == ["Generated project batch bullet."]
    assert starts["/generate-resume-section-bulletpoints"] >= ends["/select-projects"]
    assert starts["/generate-resume-section-bulletpoints"] >= ends["/derive-job-focus"]
    assert starts["/generate-resume-section-bulletpoints"] < ends["/select-skills"]
    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert [record["stage"] for record in manifest_payload["stage_responses"]] == [
        "job_focus_generation",
        "skill_selection",
        "project_selection",
        "resume_section_bullet_points",
    ]


def test_run_resume_generation_pipeline_async_enforces_global_llm_concurrency(
    monkeypatch,
    tmp_path,
):
    config_path = _write_yaml(
        tmp_path / "config.yaml",
        _config_payload(
            cache={"enabled": False},
            concurrency={"llm_requests": 2, "bullet_point_requests": 10},
        ),
    )
    job_path = _write_yaml(tmp_path / "job.yaml", _job_target_payload())
    projects_payload = _projects_payload()
    projects_payload["projects"].append(
        {
            "id": "second-active-project",
            "name": "Second Active Project",
            "summary": "Another FastAPI backend service.",
            "highlights": ["Built another service."],
            "active": True,
            "skills": {
                "technology": ["FastAPI"],
                "programming": ["Python"],
                "concepts": ["API"],
            },
            "links": None,
        }
    )
    experience_payload = _experience_payload()
    experience_payload["experience"].append(
        {
            "id": "platform-engineer",
            "name": "Platform Company",
            "role": "Platform Engineer",
            "summary": "Built deployment tooling.",
            "highlights": ["Improved deployment workflows."],
            "active": True,
            "skills": {
                "technology": ["Docker"],
                "programming": ["Python"],
                "concepts": ["CI/CD"],
            },
            "location": "Remote",
            "start": "2023",
            "end": "2024",
            "links": None,
        }
    )
    projects_path = _write_yaml(tmp_path / "projects.yaml", projects_payload)
    skills_path = _write_yaml(tmp_path / "skills.yaml", _skills_payload())
    experience_path = _write_yaml(tmp_path / "experience.yaml", experience_payload)
    loaded_evidence = _loaded_evidence(
        projects_path,
        skills_path,
        experience_path=experience_path,
    )
    current_in_flight = 0
    max_in_flight = 0
    bullet_in_flight = 0
    max_bullet_in_flight = 0

    class FakeAsyncClient:
        def __init__(self, *, base_url: str, timeout: float):
            assert base_url == "http://resumecr7.test"
            assert timeout == 5

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return None

        async def post(self, endpoint: str, json: dict):
            nonlocal current_in_flight, max_in_flight
            nonlocal bullet_in_flight, max_bullet_in_flight
            current_in_flight += 1
            max_in_flight = max(max_in_flight, current_in_flight)
            if endpoint == "/generate-bulletpoints":
                bullet_in_flight += 1
                max_bullet_in_flight = max(max_bullet_in_flight, bullet_in_flight)
            await asyncio.sleep(0.03)
            if endpoint == "/generate-bulletpoints":
                bullet_in_flight -= 1
            current_in_flight -= 1

            if endpoint == "/select-skills":
                return httpx.Response(
                    200,
                    json={
                        "technology": ["FastAPI"],
                        "programming": ["Python"],
                        "concepts": ["API"],
                    },
                )
            if endpoint == "/select-projects":
                return httpx.Response(
                    200,
                    json={
                        "selected_project_ids": [
                            "active-project",
                            "second-active-project",
                        ],
                        "ranked_projects": [
                            {
                                "project_id": "active-project",
                                "score": 1.0,
                                "method": "llm",
                            },
                            {
                                "project_id": "second-active-project",
                                "score": 0.9,
                                "method": "llm",
                            },
                        ],
                    },
                )
            if endpoint == "/derive-job-focus":
                return _job_focus_response()
            if endpoint == "/generate-bulletpoints":
                evidence = json.get("project") or json.get("experience")
                return httpx.Response(
                    200,
                    json={
                        "bullet_points": [f"Generated bullet for {evidence['id']}."],
                        "details": {"_bulletpoints_llm": {"total_tokens": 2}},
                    },
                )
            raise AssertionError(f"unexpected endpoint: {endpoint}")

    monkeypatch.setattr("resume_generation.selection.httpx.AsyncClient", FakeAsyncClient)
    monkeypatch.setattr("resume_generation.job_focus.httpx.AsyncClient", FakeAsyncClient)
    monkeypatch.setattr("resume_generation.bullet_points.httpx.AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(
        "resume_generation.main.load_registered_evidence",
        lambda paths=None: loaded_evidence,
    )

    result = asyncio.run(
        run_resume_generation_pipeline_async(
            config_path=config_path,
            job_target_path=job_path,
            evidence_paths={
                "projects": projects_path,
                "skills": skills_path,
                "experience": experience_path,
            },
            resume_result_artifact_path=tmp_path / "artifacts" / "resume_result.json",
            resume_run_manifest_artifact_path=(
                tmp_path / "artifacts" / "resume_run_manifest.json"
            ),
        )
    )

    assert max_in_flight == 2
    assert max_bullet_in_flight == 2
    assert [project.name for project in result.projects] == [
        "Active Project",
        "Second Active Project",
    ]
    assert {item.name for item in result.experience} == {
        "Example Company",
        "Platform Company",
    }


def test_resume_generation_pipeline_preserves_selected_experience_order(
    monkeypatch,
    tmp_path,
):
    config_path = _write_yaml(
        tmp_path / "config.yaml",
        _config_payload(
            cache={"enabled": False},
            experience_selection={"top_n": 4},
        ),
    )
    job_path = _write_yaml(tmp_path / "job.yaml", _job_target_payload())
    projects_path = _write_yaml(tmp_path / "projects.yaml", _projects_payload())
    skills_path = _write_yaml(tmp_path / "skills.yaml", _skills_payload())

    def experience_record(
        *,
        record_id: str,
        name: str,
        role: str,
        start: str,
        end: str | None,
    ) -> dict:
        return {
            "id": record_id,
            "name": name,
            "role": role,
            "summary": "Built platform tooling.",
            "highlights": ["Improved deployment workflows."],
            "active": True,
            "skills": {
                "technology": ["Kubernetes"],
                "programming": ["Python"],
                "concepts": ["CI/CD"],
            },
            "location": "Remote",
            "start": start,
            "end": end,
            "links": None,
        }

    experience_path = _write_yaml(
        tmp_path / "experience.yaml",
        {
            "schema_version": 1,
            "experience": [
                experience_record(
                    record_id="manning",
                    name="Manning College",
                    role="Undergraduate Research Volunteer",
                    start="June 2025",
                    end="August 2025",
                ),
                experience_record(
                    record_id="daros",
                    name="DARoS Lab",
                    role="Robotics Researcher",
                    start="May 2026",
                    end=None,
                ),
                experience_record(
                    record_id="secunet",
                    name="Secunet Security Networks",
                    role="Intern - Software Engineer",
                    start="June 2026",
                    end="August 2026",
                ),
                experience_record(
                    record_id="krastanov",
                    name="Krastanov Lab",
                    role="Research Software Engineer",
                    start="Feb 2026",
                    end=None,
                ),
            ],
        },
    )
    loaded_evidence = _loaded_evidence(
        projects_path,
        skills_path,
        experience_path=experience_path,
    )
    calls: list[tuple[str, str | None]] = []

    class FakeClient:
        def __init__(self, *, base_url: str, timeout: float):
            assert base_url == "http://resumecr7.test"
            assert timeout == 5

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return None

        def post(self, endpoint: str, json: dict):
            evidence = json.get("project") or json.get("experience")
            calls.append((endpoint, evidence.get("id") if evidence else None))
            if endpoint == "/select-skills":
                return httpx.Response(
                    200,
                    json={
                        "technology": ["FastAPI"],
                        "programming": ["Python"],
                        "concepts": ["API"],
                    },
                )
            if endpoint == "/select-projects":
                return httpx.Response(
                    200,
                    json={
                        "selected_project_ids": ["active-project"],
                        "ranked_projects": [
                            {
                                "project_id": "active-project",
                                "score": 1.0,
                                "method": "llm",
                            }
                        ],
                    },
                )
            if endpoint == "/derive-job-focus":
                return _job_focus_response()
            if endpoint == "/generate-bulletpoints":
                return httpx.Response(
                    200,
                    json={
                        "bullet_points": [f"Generated bullet for {evidence['id']}."],
                    },
                )
            raise AssertionError(f"unexpected endpoint: {endpoint}")

    monkeypatch.setattr("resume_generation.selection.httpx.Client", FakeClient)
    monkeypatch.setattr("resume_generation.bullet_points.httpx.Client", FakeClient)
    monkeypatch.setattr(
        "resume_generation.main.load_registered_evidence",
        lambda paths=None: loaded_evidence,
    )

    result = run_resume_generation_pipeline(
        config_path=config_path,
        job_target_path=job_path,
        evidence_paths={
            "projects": projects_path,
            "skills": skills_path,
            "experience": experience_path,
        },
        resume_result_artifact_path=tmp_path / "resume_result.json",
        resume_run_manifest_artifact_path=tmp_path / "resume_run_manifest.json",
    )

    assert [item.name for item in result.experience] == [
        "Krastanov Lab",
        "DARoS Lab",
        "Secunet Security Networks",
        "Manning College",
    ]
    assert [item.bullet_points for item in result.experience] == [
        ["Generated bullet for krastanov."],
        ["Generated bullet for daros."],
        ["Generated bullet for secunet."],
        ["Generated bullet for manning."],
    ]
    assert calls[-4:] == [
        ("/generate-bulletpoints", "krastanov"),
        ("/generate-bulletpoints", "daros"),
        ("/generate-bulletpoints", "secunet"),
        ("/generate-bulletpoints", "manning"),
    ]


def test_resume_generation_pipeline_reuses_cached_stage_results(monkeypatch, tmp_path):
    config_path = _write_yaml(
        tmp_path / "config.yaml",
        _config_payload(
            cache={
                "enabled": True,
                "path": str(tmp_path / "cache"),
                "force_refresh": False,
            }
        ),
    )
    job_path = _write_yaml(tmp_path / "job.yaml", _job_target_payload())
    projects_path = _write_yaml(tmp_path / "projects.yaml", _projects_payload())
    skills_path = _write_yaml(tmp_path / "skills.yaml", _skills_payload())
    loaded_evidence = _loaded_evidence(projects_path, skills_path)
    calls: list[str] = []

    class FakeClient:
        def __init__(self, *, base_url: str, timeout: float):
            assert base_url == "http://resumecr7.test"
            assert timeout == 5

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return None

        def post(self, endpoint: str, json: dict):
            calls.append(endpoint)
            if endpoint == "/select-skills":
                return httpx.Response(
                    200,
                    json={
                        "technology": ["FastAPI"],
                        "programming": ["Python"],
                        "concepts": ["API"],
                    },
                )
            if endpoint == "/select-projects":
                return httpx.Response(
                    200,
                    json={
                        "selected_project_ids": ["active-project"],
                        "ranked_projects": [
                            {
                                "project_id": "active-project",
                                "score": 1.0,
                                "method": "llm",
                            }
                        ],
                    },
                )
            if endpoint == "/derive-job-focus":
                return _job_focus_response()
            if endpoint == "/generate-bulletpoints":
                bullet_count_range = json.get("bullet_count_range") or {}
                bullet_count = bullet_count_range.get("min", 1)
                return httpx.Response(
                    200,
                    json={
                        "bullet_points": [
                            f"Cached generated bullet {index}."
                            for index in range(1, bullet_count + 1)
                        ],
                    },
                )
            raise AssertionError(f"unexpected endpoint: {endpoint}")

    monkeypatch.setattr("resume_generation.selection.httpx.Client", FakeClient)
    monkeypatch.setattr("resume_generation.bullet_points.httpx.Client", FakeClient)
    monkeypatch.setattr(
        "resume_generation.main.load_registered_evidence",
        lambda paths=None: loaded_evidence,
    )

    for _ in range(2):
        run_resume_generation_pipeline(
            config_path=config_path,
            job_target_path=job_path,
            evidence_paths={
                "projects": projects_path,
                "skills": skills_path,
            },
        )

    assert calls == [
        "/derive-job-focus",
        "/select-skills",
        "/select-projects",
        "/generate-bulletpoints",
        "/generate-bulletpoints",
    ]


def test_selection_cache_reuses_scores_across_response_shaping_fields(
    monkeypatch,
    tmp_path,
):
    cache_path = tmp_path / "cache"
    cache_config = {
        "enabled": True,
        "path": str(cache_path),
        "force_refresh": False,
    }
    first_config_payload = _config_payload(cache=cache_config)
    first_config_payload["skill_selection"]["top_n"] = 1
    first_config_payload["skill_selection"]["dev_mode"] = False
    first_config_payload["skill_selection"]["llm_max_output_tokens"] = 111
    first_config_payload["project_selection"]["top_n"] = 1
    first_config_payload["project_selection"]["dev_mode"] = False
    first_config_payload["project_selection"]["llm_max_output_tokens"] = 222
    first_config_path = _write_yaml(tmp_path / "first-config.yaml", first_config_payload)

    second_config_payload = _config_payload(cache=cache_config)
    second_config_payload["skill_selection"]["top_n"] = 2
    second_config_payload["skill_selection"]["dev_mode"] = True
    second_config_payload["skill_selection"]["llm_max_output_tokens"] = 333
    second_config_payload["project_selection"]["top_n"] = 2
    second_config_payload["project_selection"]["dev_mode"] = True
    second_config_payload["project_selection"]["llm_max_output_tokens"] = 444
    second_config_path = _write_yaml(tmp_path / "second-config.yaml", second_config_payload)

    job_path = _write_yaml(tmp_path / "job.yaml", _job_target_payload())
    skills_payload = _skills_payload()
    skills_payload["skills"]["technology"].append("Flask")
    skills_payload["skills"]["programming"].append("Go")
    skills_payload["skills"]["concepts"].append("Caching")
    skills_path = _write_yaml(tmp_path / "skills.yaml", skills_payload)
    projects_payload = _projects_payload()
    projects_payload["projects"][1]["id"] = "second-project"
    projects_payload["projects"][1]["name"] = "Second Project"
    projects_payload["projects"][1]["active"] = True
    projects_path = _write_yaml(tmp_path / "projects.yaml", projects_payload)
    loaded_evidence = _loaded_evidence(projects_path, skills_path)
    job_target = load_job_target(job_path)
    cache = ResumeGenerationStageCache(cache_path)
    requests: list[tuple[str, dict]] = []

    class FakeClient:
        def __init__(self, *, base_url: str, timeout: float):
            assert base_url == "http://resumecr7.test"
            assert timeout == 5

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return None

        def post(self, endpoint: str, json: dict):
            requests.append((endpoint, json))
            if endpoint == "/select-skills":
                return httpx.Response(
                    200,
                    json={
                        "technology": ["FastAPI", "Django", "Flask"],
                        "programming": ["Python", "Go"],
                        "concepts": ["API", "Caching"],
                        "details": {"method": "llm", "_llm": {"total_tokens": 10}},
                    },
                )
            if endpoint == "/select-projects":
                return httpx.Response(
                    200,
                    json={
                        "selected_project_ids": ["active-project", "second-project"],
                        "ranked_projects": [
                            {
                                "project_id": "active-project",
                                "score": 1.0,
                                "method": "llm",
                            },
                            {
                                "project_id": "second-project",
                                "score": 0.8,
                                "method": "llm",
                            },
                        ],
                        "details": {
                            "method": "llm",
                            "_project_llm": {"total_tokens": 20},
                        },
                    },
                )
            raise AssertionError(f"unexpected endpoint: {endpoint}")

    monkeypatch.setattr("resume_generation.selection.httpx.Client", FakeClient)

    first_context = generate_selection_context(
        loaded_evidence=loaded_evidence,
        config=load_generation_config(first_config_path),
        job_target=job_target,
        config_path=first_config_path,
        job_target_path=job_path,
        evidence_paths={
            "projects": projects_path,
            "skills": skills_path,
        },
        cache=cache,
    )
    second_context = generate_selection_context(
        loaded_evidence=loaded_evidence,
        config=load_generation_config(second_config_path),
        job_target=job_target,
        config_path=second_config_path,
        job_target_path=job_path,
        evidence_paths={
            "projects": projects_path,
            "skills": skills_path,
        },
        cache=cache,
    )

    assert [endpoint for endpoint, _ in requests] == ["/select-skills", "/select-projects"]
    assert requests[0][1]["top_n"] == 3
    assert requests[0][1]["dev_mode"] is True
    assert requests[0][1]["llm_max_output_tokens"] == 111
    assert requests[1][1]["top_n"] == 2
    assert requests[1][1]["dev_mode"] is True
    assert requests[1][1]["llm_max_output_tokens"] == 222
    assert first_context.selected_skills.technology == ["FastAPI"]
    assert first_context.selected_skills.programming == ["Python"]
    assert first_context.selected_skills.concepts == ["API"]
    assert first_context.selected_skills.details is None
    assert [project.id for project in first_context.selected_projects] == ["active-project"]
    assert first_context.project_selection.details is None
    assert second_context.selected_skills.technology == ["FastAPI", "Django"]
    assert second_context.selected_skills.programming == ["Python", "Go"]
    assert second_context.selected_skills.concepts == ["API", "Caching"]
    assert second_context.selected_skills.details == {"method": "llm", "_llm": {"total_tokens": 10}}
    assert [project.id for project in second_context.selected_projects] == [
        "active-project",
        "second-project",
    ]
    assert second_context.project_selection.details == {
        "method": "llm",
        "_project_llm": {"total_tokens": 20},
    }


def test_resume_generation_pipeline_does_not_cache_skill_llm_fallback(
    monkeypatch,
    tmp_path,
    caplog,
):
    config_path = _write_yaml(
        tmp_path / "config.yaml",
        _config_payload(
            cache={
                "enabled": True,
                "path": str(tmp_path / "cache"),
                "force_refresh": False,
            }
        ),
    )
    job_path = _write_yaml(tmp_path / "job.yaml", _job_target_payload())
    projects_path = _write_yaml(tmp_path / "projects.yaml", _projects_payload())
    skills_path = _write_yaml(tmp_path / "skills.yaml", _skills_payload())
    loaded_evidence = _loaded_evidence(projects_path, skills_path)
    calls: list[str] = []

    class FakeClient:
        def __init__(self, *, base_url: str, timeout: float):
            assert base_url == "http://resumecr7.test"
            assert timeout == 5

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return None

        def post(self, endpoint: str, json: dict):
            calls.append(endpoint)
            if endpoint == "/select-skills":
                return httpx.Response(
                    200,
                    json={
                        "technology": ["FastAPI"],
                        "programming": ["Python"],
                        "concepts": ["API"],
                        "details": {
                            "_fallback_method": "baseline",
                            "_llm": {
                                "fallback": "baseline",
                                "reason": "LLM selection failed; fell back to baseline",
                                "prompt_tokens": 11,
                                "completion_tokens": 12,
                                "total_tokens": 23,
                                "api_calls": 2,
                                "latency_ms": 51.5,
                                "attempts": [
                                    {
                                        "attempt": 1,
                                        "max_output_tokens": 777,
                                        "total_tokens": 13,
                                    },
                                    {
                                        "attempt": 2,
                                        "max_output_tokens": 3000,
                                        "total_tokens": 10,
                                    },
                                ],
                            },
                        },
                    },
                )
            if endpoint == "/select-projects":
                return httpx.Response(
                    200,
                    json={
                        "selected_project_ids": ["active-project"],
                        "ranked_projects": [
                            {
                                "project_id": "active-project",
                                "score": 1.0,
                                "method": "llm",
                            }
                        ],
                    },
                )
            if endpoint == "/derive-job-focus":
                return _job_focus_response()
            if endpoint == "/generate-bulletpoints":
                evidence = json.get("project") or json.get("experience")
                bullet_count_range = json.get("bullet_count_range") or {}
                bullet_count = bullet_count_range.get("min", 1)
                return httpx.Response(
                    200,
                    json={
                        "bullet_points": [
                            f"Generated bullet {index} for {evidence['id']}."
                            for index in range(1, bullet_count + 1)
                        ],
                    },
                )
            raise AssertionError(f"unexpected endpoint: {endpoint}")

    monkeypatch.setattr("resume_generation.selection.httpx.Client", FakeClient)
    monkeypatch.setattr("resume_generation.bullet_points.httpx.Client", FakeClient)
    monkeypatch.setattr(
        "resume_generation.main.load_registered_evidence",
        lambda paths=None: loaded_evidence,
    )

    with caplog.at_level(logging.INFO, logger="resume_generation"):
        for _ in range(2):
            run_resume_generation_pipeline(
                config_path=config_path,
                job_target_path=job_path,
                evidence_paths={
                    "projects": projects_path,
                    "skills": skills_path,
                },
                resume_result_artifact_path=tmp_path / "resume_result.json",
                resume_run_manifest_artifact_path=tmp_path / "resume_run_manifest.json",
            )

    assert calls == [
        "/derive-job-focus",
        "/select-skills",
        "/select-projects",
        "/generate-bulletpoints",
        "/generate-bulletpoints",
        "/select-skills",
    ]
    skill_records = [
        record
        for record in caplog.records
        if getattr(record, "event", None) == "resume_generation_stage_response"
        and getattr(record, "stage", None) == "skill_selection"
    ]
    assert [
        (
            record.source,
            record.cache_status,
            record.llm_max_output_tokens,
            record.total_tokens,
            record.api_calls,
        )
        for record in skill_records
    ] == [
        ("http", "skipped", 777, 23, 2),
        ("http", "skipped", 777, 23, 2),
    ]


def test_selection_context_bypasses_cached_skill_llm_fallback(monkeypatch, tmp_path):
    cache_path = tmp_path / "cache"
    config_path = _write_yaml(
        tmp_path / "config.yaml",
        _config_payload(
            cache={
                "enabled": True,
                "path": str(cache_path),
                "force_refresh": False,
            }
        ),
    )
    job_path = _write_yaml(tmp_path / "job.yaml", _job_target_payload())
    projects_path = _write_yaml(tmp_path / "projects.yaml", _projects_payload())
    skills_payload = _skills_payload()
    skills_payload["skills"]["technology"].append("Flask")
    skills_payload["skills"]["programming"].append("Go")
    skills_payload["skills"]["concepts"].append("Caching")
    skills_path = _write_yaml(tmp_path / "skills.yaml", skills_payload)
    loaded_evidence = _loaded_evidence(projects_path, skills_path)
    config = load_generation_config(config_path)
    job_target = load_job_target(job_path)
    cache = ResumeGenerationStageCache(cache_path)

    skill_payload = build_skill_selection_payload(
        job_target=job_target,
        skills_file=loaded_evidence["skills"],
        config=config,
    )
    skill_cache_payload = resume_selection._selection_cache_payload(skill_payload)
    skill_fetch_payload = resume_selection._canonical_selection_fetch_payload(
        skill_payload,
        full_top_n=resume_selection._skill_selection_full_top_n(skill_payload),
    )
    cache.get_or_store_result(
        stage="skill_selection",
        payload=skill_fetch_payload,
        cache_payload=skill_cache_payload,
        fetch=lambda: {
            "technology": ["StaleFallback"],
            "programming": [],
            "concepts": [],
            "details": {
                "_fallback_method": "baseline",
                "_llm": {"fallback": "baseline"},
            },
        },
    )
    calls: list[str] = []

    class FakeClient:
        def __init__(self, *, base_url: str, timeout: float):
            assert base_url == "http://resumecr7.test"
            assert timeout == 5

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return None

        def post(self, endpoint: str, json: dict):
            calls.append(endpoint)
            if endpoint == "/select-skills":
                return httpx.Response(
                    200,
                    json={
                        "technology": ["FastAPI", "Django", "Flask"],
                        "programming": ["Python", "Go"],
                        "concepts": ["API", "Caching"],
                        "details": {"method": "llm", "_llm": {"total_tokens": 10}},
                    },
                )
            if endpoint == "/select-projects":
                return httpx.Response(
                    200,
                    json={
                        "selected_project_ids": ["active-project"],
                        "ranked_projects": [
                            {
                                "project_id": "active-project",
                                "score": 1.0,
                                "method": "llm",
                            }
                        ],
                    },
                )
            raise AssertionError(f"unexpected endpoint: {endpoint}")

    monkeypatch.setattr("resume_generation.selection.httpx.Client", FakeClient)

    context = generate_selection_context(
        loaded_evidence=loaded_evidence,
        config=config,
        job_target=job_target,
        config_path=config_path,
        job_target_path=job_path,
        evidence_paths={
            "projects": projects_path,
            "skills": skills_path,
        },
        cache=cache,
    )

    assert calls == ["/select-skills", "/select-projects"]
    assert context.selected_skills.technology == ["FastAPI", "Django", "Flask"]


def test_selection_cache_does_not_store_project_llm_fallback(
    monkeypatch,
    tmp_path,
):
    config_path = _write_yaml(
        tmp_path / "config.yaml",
        _config_payload(
            cache={
                "enabled": True,
                "path": str(tmp_path / "cache"),
                "force_refresh": False,
            }
        ),
    )
    job_path = _write_yaml(tmp_path / "job.yaml", _job_target_payload())
    projects_path = _write_yaml(tmp_path / "projects.yaml", _projects_payload())
    skills_path = _write_yaml(tmp_path / "skills.yaml", _skills_payload())
    loaded_evidence = _loaded_evidence(projects_path, skills_path)
    config = load_generation_config(config_path)
    job_target = load_job_target(job_path)
    cache = ResumeGenerationStageCache(tmp_path / "cache")
    calls: list[str] = []
    stage_response_records: list[dict] = []

    class FakeClient:
        def __init__(self, *, base_url: str, timeout: float):
            assert base_url == "http://resumecr7.test"
            assert timeout == 5

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return None

        def post(self, endpoint: str, json: dict):
            calls.append(endpoint)
            if endpoint == "/select-skills":
                return httpx.Response(
                    200,
                    json={
                        "technology": ["FastAPI"],
                        "programming": ["Python"],
                        "concepts": ["API"],
                        "details": {"method": "llm"},
                    },
                )
            if endpoint == "/select-projects":
                return httpx.Response(
                    200,
                    json={
                        "selected_project_ids": ["active-project"],
                        "ranked_projects": [
                            {
                                "project_id": "active-project",
                                "score": 1.0,
                                "method": "baseline",
                            }
                        ],
                        "details": {
                            "_fallback_method": "baseline",
                            "_project_llm": {
                                "fallback": "baseline",
                                "reason": "Project LLM selection failed",
                                "total_tokens": 12,
                            },
                        },
                    },
                )
            raise AssertionError(f"unexpected endpoint: {endpoint}")

    monkeypatch.setattr("resume_generation.selection.httpx.Client", FakeClient)

    for _ in range(2):
        generate_selection_context(
            loaded_evidence=loaded_evidence,
            config=config,
            job_target=job_target,
            config_path=config_path,
            job_target_path=job_path,
            evidence_paths={
                "projects": projects_path,
                "skills": skills_path,
            },
            cache=cache,
            stage_response_records=stage_response_records,
        )

    assert calls == ["/select-skills", "/select-projects", "/select-projects"]
    project_records = [
        record
        for record in stage_response_records
        if record["stage"] == "project_selection"
    ]
    assert [
        (record["source"], record["cache_status"], record["total_tokens"])
        for record in project_records
    ] == [
        ("http", "skipped", 12),
        ("http", "skipped", 12),
    ]


def test_experience_bullet_model_change_does_not_regenerate_project_bullets(
    monkeypatch,
    tmp_path,
):
    cache_config = {
        "enabled": True,
        "path": str(tmp_path / "cache"),
        "force_refresh": False,
    }
    first_config_path = _write_yaml(
        tmp_path / "first-config.yaml",
        _config_payload(cache=cache_config),
    )
    second_config = _config_payload(cache=cache_config)
    second_config["experience_bullet_point_generation"][
        "llm_model"
    ] = "experience-bullet-model-v2"
    second_config_path = _write_yaml(tmp_path / "second-config.yaml", second_config)
    job_path = _write_yaml(tmp_path / "job.yaml", _job_target_payload())
    projects_path = _write_yaml(tmp_path / "projects.yaml", _projects_payload())
    skills_path = _write_yaml(tmp_path / "skills.yaml", _skills_payload())
    loaded_evidence = _loaded_evidence(projects_path, skills_path)
    calls: list[dict] = []

    _install_successful_pipeline_client(monkeypatch, calls)
    monkeypatch.setattr(
        "resume_generation.main.load_registered_evidence",
        lambda paths=None: loaded_evidence,
    )

    run_resume_generation_pipeline(
        config_path=first_config_path,
        job_target_path=job_path,
        evidence_paths={"projects": projects_path, "skills": skills_path},
    )
    run_resume_generation_pipeline(
        config_path=second_config_path,
        job_target_path=job_path,
        evidence_paths={"projects": projects_path, "skills": skills_path},
    )

    assert [
        (call["endpoint"], call["project_id"], call["experience_id"], call["llm_model"])
        for call in calls
        ] == [
            ("/derive-job-focus", None, None, "job-focus-model"),
            ("/select-skills", None, None, "skill-model"),
            ("/select-projects", None, None, "project-model"),
            ("/generate-bulletpoints", "active-project", None, "project-bullet-model"),
            (
                "/generate-bulletpoints",
            None,
            "backend-engineer",
            "experience-bullet-model",
        ),
        (
            "/generate-bulletpoints",
            None,
            "backend-engineer",
            "experience-bullet-model-v2",
        ),
    ]


def test_project_bullet_model_change_does_not_regenerate_experience_bullets(
    monkeypatch,
    tmp_path,
):
    cache_config = {
        "enabled": True,
        "path": str(tmp_path / "cache"),
        "force_refresh": False,
    }
    first_config_path = _write_yaml(
        tmp_path / "first-config.yaml",
        _config_payload(cache=cache_config),
    )
    second_config = _config_payload(cache=cache_config)
    second_config["project_bullet_point_generation"][
        "llm_model"
    ] = "project-bullet-model-v2"
    second_config_path = _write_yaml(tmp_path / "second-config.yaml", second_config)
    job_path = _write_yaml(tmp_path / "job.yaml", _job_target_payload())
    projects_path = _write_yaml(tmp_path / "projects.yaml", _projects_payload())
    skills_path = _write_yaml(tmp_path / "skills.yaml", _skills_payload())
    loaded_evidence = _loaded_evidence(projects_path, skills_path)
    calls: list[dict] = []

    _install_successful_pipeline_client(monkeypatch, calls)
    monkeypatch.setattr(
        "resume_generation.main.load_registered_evidence",
        lambda paths=None: loaded_evidence,
    )

    run_resume_generation_pipeline(
        config_path=first_config_path,
        job_target_path=job_path,
        evidence_paths={"projects": projects_path, "skills": skills_path},
    )
    run_resume_generation_pipeline(
        config_path=second_config_path,
        job_target_path=job_path,
        evidence_paths={"projects": projects_path, "skills": skills_path},
    )

    assert [
        (call["endpoint"], call["project_id"], call["experience_id"], call["llm_model"])
        for call in calls
        ] == [
            ("/derive-job-focus", None, None, "job-focus-model"),
            ("/select-skills", None, None, "skill-model"),
            ("/select-projects", None, None, "project-model"),
            ("/generate-bulletpoints", "active-project", None, "project-bullet-model"),
            (
                "/generate-bulletpoints",
            None,
            "backend-engineer",
            "experience-bullet-model",
        ),
        ("/generate-bulletpoints", "active-project", None, "project-bullet-model-v2"),
    ]


def test_skill_evidence_change_only_invalidates_skill_selection(
    monkeypatch,
    tmp_path,
):
    config_path = _write_yaml(
        tmp_path / "config.yaml",
        _config_payload(
            cache={
                "enabled": True,
                "path": str(tmp_path / "cache"),
                "force_refresh": False,
            }
        ),
    )
    job_path = _write_yaml(tmp_path / "job.yaml", _job_target_payload())
    projects_path = _write_yaml(tmp_path / "projects.yaml", _projects_payload())
    first_skills_path = _write_yaml(tmp_path / "first-skills.yaml", _skills_payload())
    second_skills = _skills_payload()
    second_skills["skills"]["technology"].append("Redis")
    second_skills_path = _write_yaml(tmp_path / "second-skills.yaml", second_skills)
    evidence_by_skills_path = {
        first_skills_path: _loaded_evidence(projects_path, first_skills_path),
        second_skills_path: _loaded_evidence(projects_path, second_skills_path),
    }
    calls: list[dict] = []

    _install_successful_pipeline_client(monkeypatch, calls)

    def fake_load_registered_evidence(paths=None):
        assert paths is not None
        return evidence_by_skills_path[Path(paths["skills"])]

    monkeypatch.setattr(
        "resume_generation.main.load_registered_evidence",
        fake_load_registered_evidence,
    )

    run_resume_generation_pipeline(
        config_path=config_path,
        job_target_path=job_path,
        evidence_paths={"projects": projects_path, "skills": first_skills_path},
    )
    run_resume_generation_pipeline(
        config_path=config_path,
        job_target_path=job_path,
        evidence_paths={"projects": projects_path, "skills": second_skills_path},
    )

    assert [
        (call["endpoint"], call["project_id"], call["experience_id"])
        for call in calls
        ] == [
            ("/derive-job-focus", None, None),
            ("/select-skills", None, None),
            ("/select-projects", None, None),
            ("/generate-bulletpoints", "active-project", None),
            ("/generate-bulletpoints", None, "backend-engineer"),
            ("/select-skills", None, None),
    ]


def test_resume_generation_pipeline_logs_stage_events(monkeypatch, tmp_path, caplog):
    config_path = _write_yaml(tmp_path / "config.yaml", _config_payload())
    job_path = _write_yaml(tmp_path / "job.yaml", _job_target_payload())
    projects_path = _write_yaml(tmp_path / "projects.yaml", _projects_payload())
    skills_path = _write_yaml(tmp_path / "skills.yaml", _skills_payload())
    loaded_evidence = _loaded_evidence(projects_path, skills_path)
    calls: list[dict] = []

    _install_successful_pipeline_client(monkeypatch, calls)
    monkeypatch.setattr(
        "resume_generation.main.load_registered_evidence",
        lambda paths=None: loaded_evidence,
    )

    with caplog.at_level(logging.INFO, logger="resume_generation"):
        run_resume_generation_pipeline(
            config_path=config_path,
            job_target_path=job_path,
            evidence_paths={"projects": projects_path, "skills": skills_path},
        )

    stage_events = [
        (record.event, getattr(record, "stage", None))
        for record in caplog.records
        if getattr(record, "event", None)
        in {
            "resume_generation_pipeline_start",
            "resume_generation_pipeline_complete",
            "resume_generation_stage_start",
            "resume_generation_stage_complete",
            "resume_generation_stage_skipped",
            "resume_generation_artifact_written",
        }
    ]
    assert ("resume_generation_pipeline_start", None) in stage_events
    assert ("resume_generation_stage_start", "selection") in stage_events
    assert ("resume_generation_stage_complete", "selection") in stage_events
    assert ("resume_generation_stage_start", "job_focus_generation") in stage_events
    assert ("resume_generation_stage_complete", "job_focus_generation") in stage_events
    assert ("resume_generation_stage_skipped", "link_scanning") not in stage_events
    assert ("resume_generation_stage_start", "link_scanning") not in stage_events
    assert ("resume_generation_stage_complete", "link_scanning") not in stage_events
    assert ("resume_generation_stage_start", "project_bullet_points") in stage_events
    assert ("resume_generation_stage_complete", "project_bullet_points") in stage_events
    assert ("resume_generation_stage_start", "experience_bullet_points") in stage_events
    assert ("resume_generation_stage_complete", "experience_bullet_points") in stage_events
    assert ("resume_generation_stage_complete", "assembly") in stage_events
    assert ("resume_generation_artifact_written", None) in stage_events
    assert ("resume_generation_pipeline_complete", None) in stage_events


def test_resume_generation_pipeline_logs_token_usage_summary(
    monkeypatch,
    tmp_path,
    caplog,
):
    config_path = _write_yaml(tmp_path / "config.yaml", _config_payload())
    job_path = _write_yaml(tmp_path / "job.yaml", _job_target_payload())
    projects_path = _write_yaml(tmp_path / "projects.yaml", _projects_payload())
    skills_path = _write_yaml(tmp_path / "skills.yaml", _skills_payload())
    loaded_evidence = _loaded_evidence(projects_path, skills_path)
    calls: list[dict] = []

    _install_successful_pipeline_client(monkeypatch, calls)
    monkeypatch.setattr(
        "resume_generation.main.load_registered_evidence",
        lambda paths=None: loaded_evidence,
    )

    with caplog.at_level(logging.INFO, logger="resume_generation"):
        run_resume_generation_pipeline(
            config_path=config_path,
            job_target_path=job_path,
            evidence_paths={"projects": projects_path, "skills": skills_path},
        )

    stage_complete = {
        record.stage: record
        for record in caplog.records
        if getattr(record, "event", None) == "resume_generation_stage_complete"
    }
    assert stage_complete["selection"].total_tokens == 45
    assert stage_complete["job_focus_generation"].total_tokens == 13
    assert stage_complete["project_bullet_points"].total_tokens == 7
    assert stage_complete["experience_bullet_points"].total_tokens == 7
    assert stage_complete["assembly"].total_tokens == 0

    summaries = [
        record
        for record in caplog.records
        if getattr(record, "event", None) == "resume_generation_token_usage_summary"
    ]
    assert len(summaries) == 1
    summary = summaries[0]
    assert summary.stages["selection"]["total_tokens"] == 45
    assert summary.stages["skill_selection"]["total_tokens"] == 15
    assert summary.stages["project_selection"]["total_tokens"] == 30
    assert summary.stages["job_focus_generation"]["total_tokens"] == 13
    assert summary.stages["link_scanning"]["total_tokens"] == 0
    assert summary.stages["project_bullet_points"]["total_tokens"] == 7
    assert summary.stages["experience_bullet_points"]["total_tokens"] == 7
    assert summary.stages["assembly"]["total_tokens"] == 0
    assert summary.total["total_tokens"] == 72
    assert summary.total["api_calls"] == 5


def test_resume_generation_pipeline_cache_misses_when_job_target_changes(
    monkeypatch,
    tmp_path,
):
    config_path = _write_yaml(
        tmp_path / "config.yaml",
        _config_payload(
            cache={
                "enabled": True,
                "path": str(tmp_path / "cache"),
                "force_refresh": False,
            }
        ),
    )
    first_job_path = _write_yaml(tmp_path / "first-job.yaml", _job_target_payload())
    second_job_path = _write_yaml(
        tmp_path / "second-job.yaml",
        _job_target_payload(title="ML Engineer"),
    )
    projects_path = _write_yaml(tmp_path / "projects.yaml", _projects_payload())
    skills_path = _write_yaml(tmp_path / "skills.yaml", _skills_payload())
    loaded_evidence = _loaded_evidence(projects_path, skills_path)
    calls: list[str] = []

    class FakeClient:
        def __init__(self, *, base_url: str, timeout: float):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return None

        def post(self, endpoint: str, json: dict):
            calls.append(endpoint)
            if endpoint == "/select-skills":
                return httpx.Response(
                    200,
                    json={
                        "technology": ["FastAPI"],
                        "programming": ["Python"],
                        "concepts": ["API"],
                    },
                )
            if endpoint == "/select-projects":
                return httpx.Response(
                    200,
                    json={
                        "selected_project_ids": ["active-project"],
                        "ranked_projects": [
                            {
                                "project_id": "active-project",
                                "score": 1.0,
                                "method": "llm",
                            }
                        ],
                    },
                )
            if endpoint == "/derive-job-focus":
                return _job_focus_response()
            if endpoint == "/generate-bulletpoints":
                return httpx.Response(
                    200,
                    json={"bullet_points": ["Generated bullet."]},
                )
            raise AssertionError(f"unexpected endpoint: {endpoint}")

    monkeypatch.setattr("resume_generation.selection.httpx.Client", FakeClient)
    monkeypatch.setattr("resume_generation.bullet_points.httpx.Client", FakeClient)
    monkeypatch.setattr(
        "resume_generation.main.load_registered_evidence",
        lambda paths=None: loaded_evidence,
    )

    run_resume_generation_pipeline(
        config_path=config_path,
        job_target_path=first_job_path,
        evidence_paths={
            "projects": projects_path,
            "skills": skills_path,
        },
    )
    run_resume_generation_pipeline(
        config_path=config_path,
        job_target_path=second_job_path,
        evidence_paths={
            "projects": projects_path,
            "skills": skills_path,
        },
    )

    assert calls == [
        "/derive-job-focus",
        "/select-skills",
        "/select-projects",
        "/generate-bulletpoints",
        "/generate-bulletpoints",
        "/derive-job-focus",
        "/select-skills",
        "/select-projects",
        "/generate-bulletpoints",
        "/generate-bulletpoints",
    ]


def test_resume_generation_pipeline_resumes_after_project_bullet_failure(
    monkeypatch,
    tmp_path,
):
    config_path = _write_yaml(
        tmp_path / "config.yaml",
        _config_payload(
            cache={
                "enabled": True,
                "path": str(tmp_path / "cache"),
                "force_refresh": False,
            }
        ),
    )
    job_path = _write_yaml(tmp_path / "job.yaml", _job_target_payload())
    projects_payload = _projects_payload()
    projects_payload["projects"].append(
        {
            "id": "second-project",
            "name": "Second Project",
            "summary": "Second FastAPI backend service.",
            "highlights": ["Built another service."],
            "active": True,
            "skills": {
                "technology": ["FastAPI"],
                "programming": ["Python"],
                "concepts": ["API"],
            },
            "links": None,
        }
    )
    projects_path = _write_yaml(tmp_path / "projects.yaml", projects_payload)
    skills_path = _write_yaml(tmp_path / "skills.yaml", _skills_payload())
    loaded_evidence = _loaded_evidence(projects_path, skills_path)
    calls: list[tuple[str, str | None]] = []
    fail_second_project = True

    class FakeClient:
        def __init__(self, *, base_url: str, timeout: float):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return None

        def post(self, endpoint: str, json: dict):
            nonlocal fail_second_project
            project_id = json.get("project", {}).get("id")
            experience_id = json.get("experience", {}).get("id")
            evidence_id = project_id or experience_id
            calls.append((endpoint, evidence_id))
            if endpoint == "/select-skills":
                return httpx.Response(
                    200,
                    json={
                        "technology": ["FastAPI"],
                        "programming": ["Python"],
                        "concepts": ["API"],
                    },
                )
            if endpoint == "/select-projects":
                return httpx.Response(
                    200,
                    json={
                        "selected_project_ids": ["active-project", "second-project"],
                        "ranked_projects": [
                            {
                                "project_id": "active-project",
                                "score": 1.0,
                                "method": "llm",
                            },
                            {
                                "project_id": "second-project",
                                "score": 0.9,
                                "method": "llm",
                            },
                        ],
                    },
                )
            if endpoint == "/derive-job-focus":
                return _job_focus_response()
            if endpoint == "/generate-bulletpoints":
                if project_id == "second-project" and fail_second_project:
                    raise httpx.ConnectError("simulated failure")
                bullet_count_range = json.get("bullet_count_range") or {}
                bullet_count = bullet_count_range.get("min", 1)
                return httpx.Response(
                    200,
                    json={
                        "bullet_points": [
                            f"Generated bullet {index} for {evidence_id}."
                            for index in range(1, bullet_count + 1)
                        ],
                    },
                )
            raise AssertionError(f"unexpected endpoint: {endpoint}")

    monkeypatch.setattr("resume_generation.selection.httpx.Client", FakeClient)
    monkeypatch.setattr("resume_generation.bullet_points.httpx.Client", FakeClient)
    monkeypatch.setattr(
        "resume_generation.main.load_registered_evidence",
        lambda paths=None: loaded_evidence,
    )

    with pytest.raises(
        ResumeGenerationError,
        match="HTTP request to /generate-bulletpoints failed",
    ):
        run_resume_generation_pipeline(
            config_path=config_path,
            job_target_path=job_path,
            evidence_paths={
                "projects": projects_path,
                "skills": skills_path,
            },
        )

    fail_second_project = False
    run_resume_generation_pipeline(
        config_path=config_path,
        job_target_path=job_path,
        evidence_paths={
            "projects": projects_path,
            "skills": skills_path,
        },
    )

    assert calls == [
        ("/derive-job-focus", None),
        ("/select-skills", None),
        ("/select-projects", None),
        ("/generate-bulletpoints", "active-project"),
        ("/generate-bulletpoints", "second-project"),
        ("/generate-bulletpoints", "second-project"),
        ("/generate-bulletpoints", "backend-engineer"),
    ]


def test_resume_generation_pipeline_does_not_scan_links_before_bullet_generation(
    monkeypatch,
    tmp_path,
):
    config_path = _write_yaml(
        tmp_path / "config.yaml",
        _config_payload(
            link_scanning={
                "enabled": True,
                "dev_mode": True,
                "llm_model": "link-model",
                "llm_max_output_tokens": 660,
                "highlight_count": 6,
                "max_tokens_per_highlight": 120,
            }
        ),
    )
    job_path = _write_yaml(tmp_path / "job.yaml", _job_target_payload())
    projects_path = _write_yaml(tmp_path / "projects.yaml", _projects_payload())
    skills_path = _write_yaml(tmp_path / "skills.yaml", _skills_payload())
    loaded_evidence = _loaded_evidence(projects_path, skills_path)
    calls: list[str] = []
    bullet_payloads: list[dict] = []

    class FakeClient:
        def __init__(self, *, base_url: str, timeout: float):
            assert base_url == "http://resumecr7.test"
            assert timeout == 5

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return None

        def post(self, endpoint: str, json: dict):
            calls.append(endpoint)
            if endpoint == "/select-skills":
                return httpx.Response(
                    200,
                    json={
                        "technology": ["FastAPI"],
                        "programming": ["Python"],
                        "concepts": ["API"],
                    },
                )
            if endpoint == "/select-projects":
                return httpx.Response(
                    200,
                    json={
                        "selected_project_ids": ["active-project"],
                        "ranked_projects": [
                            {
                                "project_id": "active-project",
                                "score": 1.0,
                                "method": "llm",
                            }
                        ],
                    },
                )
            if endpoint == "/derive-job-focus":
                return _job_focus_response()
            if endpoint == "/generate-bulletpoints":
                bullet_payloads.append(json)
                evidence = json.get("project") or json.get("experience")
                return httpx.Response(
                    200,
                    json={
                        "bullet_points": [f"Generated bullet for {evidence['id']}."],
                    },
                )
            raise AssertionError(f"unexpected endpoint: {endpoint}")

    monkeypatch.setattr("resume_generation.selection.httpx.Client", FakeClient)
    monkeypatch.setattr("resume_generation.bullet_points.httpx.Client", FakeClient)
    monkeypatch.setattr(
        "resume_generation.main.load_registered_evidence",
        lambda paths=None: loaded_evidence,
    )

    result = run_resume_generation_pipeline(
        config_path=config_path,
        job_target_path=job_path,
        evidence_paths={
            "projects": projects_path,
            "skills": skills_path,
        },
    )

    assert calls == [
        "/derive-job-focus",
        "/select-skills",
        "/select-projects",
        "/generate-bulletpoints",
        "/generate-bulletpoints",
    ]
    assert bullet_payloads[0]["context"]["job_focus"]["required_skills"] == [
        "Python",
        "FastAPI",
    ]
    assert "description" not in bullet_payloads[0]["context"]
    assert bullet_payloads[0]["project"]["highlights"] == [
        "Built the service.",
    ]
    assert bullet_payloads[0]["project"]["skills"]["technology"] == ["FastAPI"]
    assert bullet_payloads[1]["experience"]["id"] == "backend-engineer"
    assert result.projects[0].bullet_points == ["Generated bullet for active-project."]


def api_request(method: str, path: str, **kwargs):
    async def _request():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.request(method, path, **kwargs)

    return asyncio.run(_request())


def test_generate_bulletpoints_route_logs_http_source(monkeypatch, caplog):
    async def fake_generate_bulletpoints_service(_payload):
        return BulletGenerationResponse(bullet_points=["Built APIs."])

    monkeypatch.setattr(
        "app.main.generate_bulletpoints_service_async",
        fake_generate_bulletpoints_service,
    )

    with caplog.at_level(logging.INFO, logger="app_main"):
        response = api_request(
            "POST",
            "/generate-bulletpoints",
            json={
                "context": {
                    "title": "Backend Engineer",
                    "description": "Build APIs.",
                },
                "project": _projects_payload()["projects"][0],
            },
        )

    assert response.status_code == 200
    route_records = [
        record
        for record in caplog.records
        if getattr(record, "event", None) == "app_content_stage_request"
    ]
    assert len(route_records) == 1
    record = route_records[0]
    assert record.stage == "project_bullet_points"
    assert record.endpoint == "/generate-bulletpoints"
    assert record.source == "http"
    assert record.evidence_type == "project"
    assert record.evidence_id == "active-project"


def test_skill_selection_api_uses_request_llm_overrides(monkeypatch, caplog):
    captured: dict = {}

    def fake_score_skills_with_llm(**kwargs):
        captured.update(kwargs)
        return LLMScoreResult(
            scores={
                "technology": {"FastAPI": 3},
                "programming": {"Python": 3},
                "concepts": {"API": 3},
            },
            metadata={"model": kwargs["model"], "total_tokens": 0},
        )

    monkeypatch.setattr(
        "app.skill_selection.scoring.llm.score_skills_with_llm",
        fake_score_skills_with_llm,
    )

    with caplog.at_level(logging.INFO, logger="app_main"):
        response = api_request(
            "POST",
            "/select-skills",
            json={
                "job_role": "Backend Engineer",
                "job_text": "Build APIs.",
                "technology": ["FastAPI"],
                "programming": ["Python"],
                "concepts": ["API"],
                "method": "llm",
                "dev_mode": True,
                "llm_model": "request-skill-model",
                "llm_max_output_tokens": 333,
            },
        )

    assert response.status_code == 200
    assert captured["model"] == "request-skill-model"
    assert captured["max_output_tokens"] == 333
    assert response.json()["details"]["_llm"]["model"] == "request-skill-model"
    route_records = [
        record
        for record in caplog.records
        if getattr(record, "event", None) == "app_content_stage_request"
    ]
    assert route_records[0].llm_max_output_tokens == 333


def test_project_selection_api_uses_request_llm_overrides(monkeypatch):
    captured: dict = {}

    def fake_score_projects_with_llm(**kwargs):
        captured.update(kwargs)
        return LLMProjectScoreResult(
            scores={"resumecr7": 3},
            metadata={"model": kwargs["model"], "total_tokens": 0},
        )

    monkeypatch.setattr(
        "app.project_selection.llm.score_projects_with_llm",
        fake_score_projects_with_llm,
    )

    response = api_request(
        "POST",
        "/select-projects",
        json={
            "context": {
                "title": "Backend Engineer",
                "description": "Build APIs.",
            },
            "candidates": [
                {
                    "id": "resumecr7",
                    "name": "ResumeCR7",
                    "summary": "FastAPI backend API.",
                    "skills": {
                        "technology": ["FastAPI"],
                        "programming": ["Python"],
                        "concepts": ["API"],
                    },
                }
            ],
            "method": "llm",
            "dev_mode": True,
            "llm_model": "request-project-model",
            "llm_max_output_tokens": 444,
        },
    )

    assert response.status_code == 200
    assert captured["model"] == "request-project-model"
    assert captured["max_output_tokens"] == 444
    assert response.json()["details"]["_project_llm"]["model"] == "request-project-model"


def test_resume_generation_enrich_link_evidence_route_returns_batch_result_and_refreshes_state(
    monkeypatch,
):
    captured: dict = {}

    def fake_run_link_evidence_enrichment(**kwargs):
        captured.update(kwargs)
        return resume_enrich.LinkEvidenceEnrichmentResult(
            dry_run=bool(kwargs["dry_run"]),
            records=(
                resume_enrich.LinkEvidenceEnrichmentRecordResult(
                    evidence_type="project",
                    evidence_id="resumecr7",
                    name="ResumeCR7",
                    scanned=True,
                    added_highlights=("Scanned project highlight.",),
                    details={"method": "llm"},
                ),
                resume_enrich.LinkEvidenceEnrichmentRecordResult(
                    evidence_type="experience",
                    evidence_id="backend-engineer",
                    name="Example Company",
                    scanned=False,
                    added_highlights=(),
                    skipped_reason="no_links",
                ),
            ),
            updated_paths=("user/resume_evidence/projects.yaml",),
        )

    monkeypatch.setattr(
        "app.resume_generation.api.run_link_evidence_enrichment",
        fake_run_link_evidence_enrichment,
    )
    monkeypatch.setattr(
        "app.resume_generation.api.load_registered_evidence",
        lambda: {"projects": "reloaded"},
    )

    response = api_request(
        "POST",
        "/resume-generation/enrich-link-evidence",
        json={
            "evidence_type": "all",
            "dry_run": False,
            "llm_model": "route-link-model",
            "highlight_count": 5,
        },
    )

    assert response.status_code == 200
    assert captured["evidence_type"] == "all"
    assert captured["llm_model"] == "route-link-model"
    assert captured["highlight_count"] == 5
    assert app.state.resume_evidence == {"projects": "reloaded"}
    data = response.json()
    assert data["scanned_count"] == 1
    assert data["total_added_highlights"] == 1
    assert data["updated_paths"] == ["user/resume_evidence/projects.yaml"]
    assert data["records"][0]["added_highlights"] == ["Scanned project highlight."]
    assert data["records"][1]["skipped_reason"] == "no_links"


def test_resume_generation_enrich_link_evidence_route_passes_target_record_id(
    monkeypatch,
):
    captured: dict = {}

    def fake_run_link_evidence_enrichment(**kwargs):
        captured.update(kwargs)
        return resume_enrich.LinkEvidenceEnrichmentResult(
            dry_run=bool(kwargs["dry_run"]),
            records=(
                resume_enrich.LinkEvidenceEnrichmentRecordResult(
                    evidence_type="project",
                    evidence_id="resumecr7",
                    name="ResumeCR7",
                    scanned=True,
                    added_highlights=("Scanned project highlight.",),
                ),
            ),
            updated_paths=("user/resume_evidence/projects.yaml",),
        )

    monkeypatch.setattr(
        "app.resume_generation.api.run_link_evidence_enrichment",
        fake_run_link_evidence_enrichment,
    )
    monkeypatch.setattr(
        "app.resume_generation.api.load_registered_evidence",
        lambda: {"projects": "reloaded"},
    )

    response = api_request(
        "POST",
        "/resume-generation/enrich-link-evidence",
        json={
            "evidence_type": "projects",
            "evidence_id": "resumecr7",
            "dry_run": False,
        },
    )

    assert response.status_code == 200
    assert captured["evidence_type"] == "projects"
    assert captured["evidence_id"] == "resumecr7"
    assert response.json()["records"][0]["evidence_id"] == "resumecr7"
    assert app.state.resume_evidence == {"projects": "reloaded"}


def test_resume_generation_enrich_link_evidence_route_rejects_all_with_target_id():
    response = api_request(
        "POST",
        "/resume-generation/enrich-link-evidence",
        json={"evidence_type": "all", "evidence_id": "resumecr7"},
    )

    assert response.status_code == 400
    assert "evidence_id requires" in response.text


def test_resume_generation_status_route_returns_idle_snapshot():
    resume_generation_status_store.reset()

    response = api_request("GET", "/resume-generation/status")

    assert response.status_code == 200
    data = response.json()
    assert data == {
        "schema_version": 1,
        "run_id": None,
        "operation": None,
        "status": "idle",
        "started_at": None,
        "completed_at": None,
        "current_stage_id": None,
        "error": None,
        "stages": [],
        "job_focus": None,
        "metric_notes": [],
    }


def test_resume_generation_tex_route_runs_pipeline_and_returns_tex_content(
    monkeypatch,
    tmp_path,
):
    resume_generation_status_store.reset()
    resume_result = _sample_intermediate_resume_result()
    tex_path = tmp_path / "resume.tex"
    tex_path.write_text("rendered tex\n", encoding="utf-8")
    calls: list[str] = []

    async def fake_run_resume_generation_pipeline(**kwargs):
        calls.append("pipeline")
        status_reporter = kwargs["status_reporter"]
        status_reporter("job_focus_generation", "running", "Generating job focus", None)
        status_reporter(
            "job_focus_generation",
            "succeeded",
            "Done",
            JobFocus.model_validate(_job_focus_payload()),
        )
        status_reporter(
            "project_selection",
            "succeeded",
            "Done",
            None,
            [
                MetricOpportunityNote(
                    evidence_type="project",
                    evidence_id="resumecr7",
                    name="ResumeCR7",
                    suggestions=[
                        "Add a real runtime, latency, throughput, or speedup metric if known."
                    ],
                )
            ],
        )
        return resume_result

    def fake_write_resume_latex_from_config(result):
        calls.append("latex")
        assert result is resume_result
        return tex_path

    monkeypatch.setattr(
        "app.resume_generation.api.run_resume_generation_pipeline_async",
        fake_run_resume_generation_pipeline,
    )
    monkeypatch.setattr(
        "app.resume_generation.api.write_resume_latex_from_config",
        fake_write_resume_latex_from_config,
    )

    response = api_request("POST", "/resume-generation/tex", json={})

    assert response.status_code == 200
    assert calls == ["pipeline", "latex"]
    data = response.json()
    assert data["run_id"]
    assert data["resume_result"]["top"]["name"] == "Example Candidate"
    assert data["tex_path"] == str(tex_path)
    assert data["artifact_tex_path"].endswith("user/resume_generation/artifacts/resume.tex")
    assert data["tex_content"] == "rendered tex\n"
    assert data["resume_result_path"].endswith(
        "user/resume_generation/artifacts/resume_result.json"
    )
    assert data["manifest_path"].endswith(
        "user/resume_generation/artifacts/resume_run_manifest.json"
    )
    status_response = api_request("GET", "/resume-generation/status")
    assert status_response.status_code == 200
    status_payload = status_response.json()
    assert status_payload["run_id"] == data["run_id"]
    assert status_payload["status"] == "succeeded"
    assert status_payload["job_focus"]["summary"] == (
        "Backend API role focused on Python services."
    )
    assert status_payload["metric_notes"] == [
        {
            "evidence_type": "project",
            "evidence_id": "resumecr7",
            "name": "ResumeCR7",
            "suggestions": [
                "Add a real runtime, latency, throughput, or speedup metric if known."
            ],
        }
    ]
    assert [stage["status"] for stage in status_payload["stages"]][-1] == "succeeded"


def test_resume_generation_tex_route_accepts_job_target_override(
    monkeypatch,
    tmp_path,
):
    resume_generation_status_store.reset()
    resume_result = _sample_intermediate_resume_result()
    tex_path = tmp_path / "resume.tex"
    tex_path.write_text("rendered tex\n", encoding="utf-8")
    captured: dict[str, object] = {}

    async def fake_run_resume_generation_pipeline(**kwargs):
        captured.update(kwargs)
        return resume_result

    def fake_write_resume_latex_from_config(result):
        assert result is resume_result
        return tex_path

    monkeypatch.setattr(
        "app.resume_generation.api.run_resume_generation_pipeline_async",
        fake_run_resume_generation_pipeline,
    )
    monkeypatch.setattr(
        "app.resume_generation.api.write_resume_latex_from_config",
        fake_write_resume_latex_from_config,
    )

    response = api_request(
        "POST",
        "/resume-generation/tex",
        json={
            "job_target": {
                "schema_version": 1,
                "title": "Frontend Engineer",
                "description": "Build React interfaces.",
            }
        },
    )

    assert response.status_code == 200
    job_target = captured["job_target_override"]
    assert isinstance(job_target, JobTarget)
    assert job_target.title == "Frontend Engineer"
    assert job_target.description == "Build React interfaces."


def test_resume_generation_tex_route_marks_status_failed(monkeypatch):
    resume_generation_status_store.reset()

    async def fake_run_resume_generation_pipeline(**kwargs):
        status_reporter = kwargs["status_reporter"]
        status_reporter("job_focus_generation", "running", "Generating job focus", None)
        raise ResumeGenerationError("selection service unavailable")

    monkeypatch.setattr(
        "app.resume_generation.api.run_resume_generation_pipeline_async",
        fake_run_resume_generation_pipeline,
    )

    response = api_request("POST", "/resume-generation/tex", json={})

    assert response.status_code == 502
    status_response = api_request("GET", "/resume-generation/status")
    data = status_response.json()
    assert data["status"] == "failed"
    assert data["error"] == "selection service unavailable"
    assert data["stages"][0]["status"] == "failed"


def test_resume_generation_pdf_route_returns_rendered_pdf(monkeypatch, tmp_path):
    generation_root = tmp_path / "resume_generation"
    monkeypatch.setattr(settings, "RESUME_GENERATION_ROOT", generation_root)
    artifact_tex_path = generation_root / "artifacts" / "resume.tex"
    artifact_pdf_path = generation_root / "artifacts" / "resume.pdf"
    output_dir = tmp_path / "out"
    output_tex_path = output_dir / "resume.tex"
    output_pdf_path = output_dir / "resume.pdf"
    artifact_tex_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_tex_path.write_text("tex", encoding="utf-8")
    config = ResumeGenerationConfig.model_validate(
        _config_payload(
            resume_output={
                "output_dir": str(output_dir),
                "pdf_timeout_seconds": 11,
            }
        )
    )
    calls: list[dict[str, object]] = []

    def fake_render_latex_pdf(tex_arg, pdf_arg, *, timeout_seconds):
        calls.append(
            {
                "tex_arg": tex_arg,
                "pdf_arg": pdf_arg,
                "timeout_seconds": timeout_seconds,
            }
        )
        Path(pdf_arg).parent.mkdir(parents=True, exist_ok=True)
        Path(pdf_arg).write_bytes(b"%PDF-1.4\n")
        return Path(pdf_arg)

    monkeypatch.setattr(
        "app.resume_generation.api.load_generation_config",
        lambda _path: config,
    )
    monkeypatch.setattr(
        "app.resume_generation.api.render_latex_pdf",
        fake_render_latex_pdf,
    )

    response = api_request("POST", "/resume-generation/pdf", json={})

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["x-resumecr7-tex-path"] == str(output_tex_path)
    assert response.headers["x-resumecr7-pdf-path"] == str(output_pdf_path)
    assert response.headers["x-resumecr7-artifact-tex-path"] == str(artifact_tex_path)
    assert response.headers["x-resumecr7-artifact-pdf-path"] == str(artifact_pdf_path)
    assert response.content == b"%PDF-1.4\n"
    assert output_tex_path.read_text(encoding="utf-8") == "tex"
    assert output_pdf_path.read_bytes() == b"%PDF-1.4\n"
    assert calls == [
        {
            "tex_arg": artifact_tex_path,
            "pdf_arg": artifact_pdf_path,
            "timeout_seconds": 11.0,
        }
    ]


def test_resume_generation_pdf_route_returns_404_for_missing_tex(monkeypatch, tmp_path):
    generation_root = tmp_path / "resume_generation"
    monkeypatch.setattr(settings, "RESUME_GENERATION_ROOT", generation_root)
    tex_path = generation_root / "artifacts" / "missing.tex"
    config = ResumeGenerationConfig.model_validate(
        _config_payload(resume_output={"output_dir": str(tmp_path / "out")})
    )

    def fake_render_latex_pdf(*_args, **_kwargs):
        raise FileNotFoundError(f"LaTeX source file does not exist: {tex_path}")

    monkeypatch.setattr(
        "app.resume_generation.api.load_generation_config",
        lambda _path: config,
    )
    monkeypatch.setattr(
        "app.resume_generation.api.render_latex_pdf",
        fake_render_latex_pdf,
    )

    response = api_request("POST", "/resume-generation/pdf", json={})

    assert response.status_code == 404
    assert "LaTeX source file does not exist" in response.text


def test_resume_generation_pdf_route_returns_502_for_latex_failure(
    monkeypatch,
    tmp_path,
):
    generation_root = tmp_path / "resume_generation"
    monkeypatch.setattr(settings, "RESUME_GENERATION_ROOT", generation_root)
    tex_path = generation_root / "artifacts" / "resume.tex"
    tex_path.parent.mkdir(parents=True, exist_ok=True)
    tex_path.write_text("tex", encoding="utf-8")
    config = ResumeGenerationConfig.model_validate(
        _config_payload(resume_output={"output_dir": str(tmp_path / "out")})
    )

    def fake_render_latex_pdf(*_args, **_kwargs):
        raise LatexPdfRenderError("latex failed")

    monkeypatch.setattr(
        "app.resume_generation.api.load_generation_config",
        lambda _path: config,
    )
    monkeypatch.setattr(
        "app.resume_generation.api.render_latex_pdf",
        fake_render_latex_pdf,
    )

    response = api_request("POST", "/resume-generation/pdf", json={})

    assert response.status_code == 502
    assert "latex failed" in response.text


def test_resume_generation_pipeline_uses_local_stage_services_by_default(
    monkeypatch,
    tmp_path,
):
    config_path = _write_yaml(tmp_path / "config.yaml", _config_payload())
    job_path = _write_yaml(tmp_path / "job.yaml", _job_target_payload())
    projects_path = _write_yaml(tmp_path / "projects.yaml", _projects_payload())
    skills_path = _write_yaml(tmp_path / "skills.yaml", _skills_payload())
    loaded_evidence = _loaded_evidence(projects_path, skills_path)
    calls: list[tuple[str, str | None]] = []

    def fake_select_skills_service(req):
        calls.append(("select-skills", req.llm_model))
        return SkillSelectResponse(
            technology=["FastAPI"],
            programming=["Python"],
            concepts=["API"],
            details={"method": "llm"},
        )

    def fake_select_projects_service(req):
        calls.append(("select-projects", req.llm_model))
        return AppProjectSelectionResult(
            selected_project_ids=["active-project"],
            ranked_projects=[
                RankedProject(project_id="active-project", score=1.0, method="llm")
            ],
            details={"method": "llm"},
        )

    def fake_derive_job_focus_service(req):
        calls.append(("derive-job-focus", req.llm_model))
        return JobFocusResponse(
            job_focus=JobFocus(
                summary="Backend role.",
                required_skills=["Python", "FastAPI"],
                preferred_skills=[],
                responsibilities=["Build APIs"],
                domain_emphasis=[],
                resume_relevant_constraints=[],
                excluded_context=[],
            ),
            details={"method": "llm"},
        )

    def fake_generate_bulletpoints_service(req):
        calls.append(("generate-bulletpoints", req.evidence_id))
        return BulletGenerationResponse(
            bullet_points=[f"Generated bullet for {req.evidence_id}."],
            details={"method": "llm"},
        )

    monkeypatch.setattr(
        "app.resume_generation.selection.select_skills_service",
        fake_select_skills_service,
    )
    monkeypatch.setattr(
        "app.resume_generation.selection.select_projects_service",
        fake_select_projects_service,
    )
    monkeypatch.setattr(
        "app.resume_generation.selection.derive_job_focus_service",
        fake_derive_job_focus_service,
    )
    monkeypatch.setattr(
        "app.resume_generation.selection.generate_bulletpoints_service",
        fake_generate_bulletpoints_service,
    )
    monkeypatch.setattr(
        "app.resume_generation.main.load_registered_evidence",
        lambda paths=None: loaded_evidence,
    )

    result = run_resume_generation_pipeline(
        config_path=config_path,
        job_target_path=job_path,
        evidence_paths={"projects": projects_path, "skills": skills_path},
        resume_result_artifact_path=tmp_path / "resume_result.json",
        resume_run_manifest_artifact_path=tmp_path / "resume_run_manifest.json",
    )

    assert calls == [
        ("derive-job-focus", "job-focus-model"),
        ("select-skills", "skill-model"),
        ("select-projects", "project-model"),
        ("generate-bulletpoints", "active-project"),
        ("generate-bulletpoints", "backend-engineer"),
    ]
    assert result.projects[0].bullet_points == ["Generated bullet for active-project."]
    assert result.experience[0].bullet_points == [
        "Generated bullet for backend-engineer."
    ]


def test_resume_generation_pipeline_job_target_override_reaches_stage_services(
    monkeypatch,
    tmp_path,
):
    config_path = _write_yaml(tmp_path / "config.yaml", _config_payload())
    job_path = _write_yaml(tmp_path / "job.yaml", _job_target_payload())
    projects_path = _write_yaml(tmp_path / "projects.yaml", _projects_payload())
    skills_path = _write_yaml(tmp_path / "skills.yaml", _skills_payload())
    loaded_evidence = _loaded_evidence(projects_path, skills_path)
    captured: dict[str, object] = {}
    override = JobTarget(
        schema_version=1,
        title="Frontend Engineer",
        description="Build React interfaces.",
    )

    def fake_select_skills_service(req):
        captured["skill_target"] = (req.job_role, req.job_text)
        return SkillSelectResponse(
            technology=["FastAPI"],
            programming=["Python"],
            concepts=["API"],
            details={"method": "llm"},
        )

    def fake_select_projects_service(req):
        captured["project_target"] = (req.context.title, req.context.description)
        return AppProjectSelectionResult(
            selected_project_ids=["active-project"],
            ranked_projects=[
                RankedProject(project_id="active-project", score=1.0, method="llm")
            ],
            details={"method": "llm"},
        )

    def fake_derive_job_focus_service(req):
        captured["job_focus_target"] = (req.title, req.description)
        return JobFocusResponse(
            job_focus=JobFocus(
                summary="Frontend role.",
                required_skills=["React"],
                preferred_skills=[],
                responsibilities=["Build interfaces"],
                domain_emphasis=[],
                resume_relevant_constraints=[],
                excluded_context=[],
            ),
            details={"method": "llm"},
        )

    def fake_generate_bulletpoints_service(req):
        captured.setdefault("bullet_targets", []).append(
            (req.context.title, req.context.description, req.context.job_focus.summary)
        )
        return BulletGenerationResponse(
            bullet_points=[f"Generated bullet for {req.evidence_id}."],
            details={"method": "llm"},
        )

    monkeypatch.setattr(
        "app.resume_generation.selection.select_skills_service",
        fake_select_skills_service,
    )
    monkeypatch.setattr(
        "app.resume_generation.selection.select_projects_service",
        fake_select_projects_service,
    )
    monkeypatch.setattr(
        "app.resume_generation.selection.derive_job_focus_service",
        fake_derive_job_focus_service,
    )
    monkeypatch.setattr(
        "app.resume_generation.selection.generate_bulletpoints_service",
        fake_generate_bulletpoints_service,
    )
    monkeypatch.setattr(
        "app.resume_generation.main.load_registered_evidence",
        lambda paths=None: loaded_evidence,
    )

    manifest_path = tmp_path / "resume_run_manifest.json"
    run_resume_generation_pipeline(
        config_path=config_path,
        job_target_path=job_path,
        job_target_override=override,
        evidence_paths={"projects": projects_path, "skills": skills_path},
        resume_result_artifact_path=tmp_path / "resume_result.json",
        resume_run_manifest_artifact_path=manifest_path,
    )

    assert captured["skill_target"] == (
        "Frontend Engineer",
        "Build React interfaces.",
    )
    assert captured["project_target"] == (
        "Frontend Engineer",
        "Build React interfaces.",
    )
    assert captured["job_focus_target"] == (
        "Frontend Engineer",
        "Build React interfaces.",
    )
    assert captured["bullet_targets"] == [
        ("Frontend Engineer", None, "Frontend role."),
        ("Frontend Engineer", None, "Frontend role."),
    ]
    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest_payload["inputs"]["job_target_source"] == "request"
    assert manifest_payload["inputs"]["job_target"] == {
        "schema_version": 1,
        "title": "Frontend Engineer",
        "description": "Build React interfaces.",
    }
