import pytest
from pydantic import ValidationError

from app.bulletpoints_generation.models import (
    BulletCountRange,
    BulletGenerationRequest,
    BulletJobContext,
)
from app.bulletpoints_generation.service import effective_bullet_count_range
from app.job_focus_generation.models import JobFocus


def _project_payload(**overrides):
    payload = {
        "id": "resumecr7",
        "name": "ResumeCR7",
        "summary": "Resume engine for grounded, job-targeted resume generation.",
        "highlights": [
            "Built a FastAPI service for deterministic skill and project selection.",
            "Added grounded project evidence parsing and validation.",
        ],
        "active": True,
        "skills": {
            "technology": ["FastAPI", "OpenAI"],
            "programming": ["Python"],
            "concepts": ["API", "Resume Generation"],
        },
        "links": ["https://example.com/resumecr7"],
    }
    payload.update(overrides)
    return payload


def _experience_payload(**overrides):
    payload = {
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
    payload.update(overrides)
    return payload


def test_bullet_count_range_accepts_exact_and_flexible_ranges():
    exact = BulletCountRange(min=3, max=3)
    flexible = BulletCountRange(min=2, max=4)

    assert exact.min == exact.max == 3
    assert flexible.min == 2
    assert flexible.max == 4


@pytest.mark.parametrize(
    "count_range",
    [
        {"min": 0, "max": 3},
        {"min": 3, "max": 11},
        {"min": 4, "max": 3},
    ],
)
def test_bullet_count_range_rejects_invalid_ranges(count_range):
    with pytest.raises(ValidationError):
        BulletCountRange.model_validate(count_range)


def test_bullet_generation_request_accepts_full_project_record():
    request = BulletGenerationRequest.model_validate(
        {
            "context": {"title": "Backend Engineer", "description": "Build Python APIs."},
            "project": _project_payload(),
            "bullet_count_range": {"min": 2, "max": 4},
            "dev_mode": True,
        }
    )

    assert request.context.title == "Backend Engineer"
    assert request.project is not None
    assert request.project.highlights[0].startswith("Built a FastAPI")
    assert request.bullet_count_range is not None
    assert request.bullet_count_range.max == 4


def test_bullet_generation_request_accepts_job_focus_context():
    request = BulletGenerationRequest.model_validate(
        {
            "context": {
                "title": "Backend Engineer",
                "job_focus": {
                    "summary": "Python API role.",
                    "required_skills": ["Python", "FastAPI"],
                    "preferred_skills": ["Docker"],
                    "responsibilities": ["Build REST APIs"],
                    "domain_emphasis": ["Backend platforms"],
                    "resume_relevant_constraints": ["Remote collaboration"],
                    "excluded_context": ["Benefits"],
                },
            },
            "project": _project_payload(),
        }
    )

    assert isinstance(request.context.job_focus, JobFocus)
    assert request.context.job_focus.required_skills == ["Python", "FastAPI"]


def test_bullet_generation_request_accepts_full_experience_record():
    request = BulletGenerationRequest.model_validate(
        {
            "context": {"title": "Backend Engineer", "description": "Build Python APIs."},
            "experience": _experience_payload(),
            "bullet_count_range": {"min": 2, "max": 4},
            "dev_mode": True,
        }
    )

    assert request.context.title == "Backend Engineer"
    assert request.experience is not None
    assert request.experience.role == "Backend Engineer"
    assert request.evidence_type == "experience"
    assert request.evidence_id == "backend-engineer"


def test_bullet_generation_request_requires_exactly_one_evidence_record():
    with pytest.raises(ValidationError, match="Exactly one of project or experience"):
        BulletGenerationRequest.model_validate(
            {
                "context": {"title": "Backend Engineer"},
            }
        )

    with pytest.raises(ValidationError, match="Exactly one of project or experience"):
        BulletGenerationRequest.model_validate(
            {
                "context": {"title": "Backend Engineer"},
                "project": _project_payload(),
                "experience": _experience_payload(),
            }
        )


def test_bullet_generation_request_rejects_empty_title():
    with pytest.raises(ValidationError, match="title"):
        BulletJobContext(title="  ")


def test_bullet_generation_request_rejects_extra_project_fields():
    project = _project_payload(extra_claim="invented")

    with pytest.raises(ValidationError, match="extra_claim"):
        BulletGenerationRequest.model_validate(
            {
                "context": {"title": "Backend Engineer"},
                "project": project,
            }
        )


def test_effective_bullet_count_range_uses_config_default(monkeypatch):
    from app.bulletpoints_generation import service

    monkeypatch.setattr(service.settings, "BULLETPOINTS_DEFAULT_COUNT", 5)

    count_range = effective_bullet_count_range(None)

    assert count_range.min == 5
    assert count_range.max == 5
