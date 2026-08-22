from __future__ import annotations

from app.bulletpoints_generation.metric_guidance import (
    build_metric_opportunity_notes,
    build_record_numeric_evidence,
)
from resume_evidence.models import ExperienceRecord, ProjectRecord, ProjectSkills


def _skills(*concepts: str) -> ProjectSkills:
    return ProjectSkills(
        technology=["FastAPI"],
        programming=["Python"],
        concepts=list(concepts),
    )


def test_build_record_numeric_evidence_extracts_supported_metric_snippets():
    project = ProjectRecord(
        id="agentic-workflow",
        name="Agentic Workflow",
        summary="AI workflow system for marketing content.",
        highlights=[
            "Integrated LangChain, Redis, and 6+ APIs for content creation.",
            "Maintained 97% uptime and increased online engagement by 400%.",
        ],
        active=True,
        skills=_skills("Automation"),
    )

    assert build_record_numeric_evidence(project) == [
        "Integrated LangChain, Redis, and 6+ APIs for content creation.",
        "Maintained 97% uptime and increased online engagement by 400%.",
    ]


def test_build_metric_opportunity_notes_flags_metric_worthy_records_without_numbers():
    project = ProjectRecord(
        id="parallel-runner",
        name="Parallel Runner",
        summary="Distributed processing service for data workloads.",
        highlights=["Optimized parallel task execution and reliability for batch jobs."],
        active=True,
        skills=_skills("Distributed Systems", "Performance Optimization"),
    )

    notes = build_metric_opportunity_notes(projects=[project], experiences=[])

    assert notes == [
        {
            "evidence_type": "project",
            "evidence_id": "parallel-runner",
            "name": "Parallel Runner",
            "suggestions": [
                "Add a real runtime, latency, throughput, or speedup metric if known.",
                (
                    "Add a real uptime, scale, user, request volume, "
                    "or reliability metric if known."
                ),
                (
                    "Add a real throughput, parallelism, worker count, "
                    "or processing-time metric if known."
                ),
            ],
        }
    ]


def test_build_metric_opportunity_notes_skips_records_with_existing_numbers():
    experience = ExperienceRecord(
        id="research-intern",
        name="Example Lab",
        role="Research Intern",
        summary="Mechanistic interpretability research.",
        highlights=["Reduced model complexity by 15% while maintaining performance."],
        active=True,
        skills=_skills("Performance Optimization"),
        location="Remote",
        start="2025",
        end=None,
    )

    assert build_metric_opportunity_notes(projects=[], experiences=[experience]) == []
