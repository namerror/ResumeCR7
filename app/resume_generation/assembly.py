from __future__ import annotations

from collections.abc import Iterable

from app.job_focus_generation.models import JobFocus
from app.resume_evidence.models import (
    EducationFile,
    ExperienceFile,
    ProjectRecord,
    ProjectSkills,
    UserInfoFile,
)
from app.resume_generation.models import (
    ExperienceBulletPointResult,
    IntermediateResumeResult,
    ProjectBulletPointResult,
    ResumeEducationItem,
    ResumeExperienceItem,
    ResumeProjectItem,
    ResumeSelectionContext,
    ResumeSkillsSection,
    ResumeTopSection,
)
from app.resume_generation.tailoring import reorder_skills_for_job_focus


def assemble_intermediate_resume_result(
    *,
    user_info: UserInfoFile,
    education: EducationFile,
    experience: ExperienceFile,
    selection_context: ResumeSelectionContext,
    selected_projects: Iterable[ProjectRecord],
    project_bullet_points: Iterable[ProjectBulletPointResult],
    experience_bullet_points: Iterable[ExperienceBulletPointResult] | None = None,
    job_focus: JobFocus | None = None,
) -> IntermediateResumeResult:
    bullet_points_by_project_id = {
        result.project_id: result.bullet_points for result in project_bullet_points
    }
    bullet_points_by_experience_id = {
        result.experience_id: result.bullet_points
        for result in experience_bullet_points or []
    }

    selected_skills = reorder_skills_for_job_focus(
        ResumeSkillsSection(
            technology=selection_context.selected_skills.technology,
            programming=selection_context.selected_skills.programming,
            concepts=selection_context.selected_skills.concepts,
        ),
        job_focus,
    )

    return IntermediateResumeResult(
        top=ResumeTopSection(
            name=user_info.name,
            phone=user_info.phone,
            email=user_info.email,
            github=user_info.github,
            website=user_info.website,
            linkedin=user_info.linkedin,
        ),
        education=[
            ResumeEducationItem(
                name=item.name,
                degree=item.degree,
                grade=item.grade,
                start=item.start,
                end=item.end,
                location=item.location,
                relevant_coursework=item.relevant_coursework,
            )
            for item in education.education
        ],
        experience=[
            ResumeExperienceItem(
                name=item.name,
                role=item.role,
                bullet_points=bullet_points_by_experience_id.get(item.id, item.highlights),
                skills=_flatten_skills(item.skills),
                location=item.location,
                start=item.start,
                end=item.end,
            )
            for item in experience.experience
            if item.active
        ],
        projects=[
            ResumeProjectItem(
                name=project.name,
                bullet_points=bullet_points_by_project_id.get(project.id, []),
                skills=_flatten_skills(project.skills),
                links=project.links or [],
            )
            for project in selected_projects
        ],
        skills=selected_skills,
    )


def _flatten_skills(skills: ProjectSkills) -> list[str]:
    return [*skills.technology, *skills.programming, *skills.concepts]
