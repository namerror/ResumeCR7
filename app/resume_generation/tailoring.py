from __future__ import annotations

import re
from typing import Iterable

from app.job_focus_generation.models import JobFocus
from app.resume_generation.models import IntermediateResumeResult, ResumeSkillsSection
from app.skill_selection.scoring.baseline import normalize_skill

TOKEN_PATTERN = re.compile(r"[a-z0-9]+(?:#|\+\+)?")


def reorder_skills_for_job_focus(
    skills: ResumeSkillsSection,
    job_focus: JobFocus | None,
) -> ResumeSkillsSection:
    if job_focus is None:
        return skills

    return ResumeSkillsSection(
        technology=_reorder_category(skills.technology, job_focus),
        programming=_reorder_category(skills.programming, job_focus),
        concepts=_reorder_category(skills.concepts, job_focus),
    )


def build_tailoring_audit(
    *,
    resume_result: IntermediateResumeResult,
    job_focus: JobFocus,
) -> dict[str, object]:
    resume_text = _normalize_text(
        " ".join(
            [
                *resume_result.skills.technology,
                *resume_result.skills.programming,
                *resume_result.skills.concepts,
                *[
                    bullet
                    for item in resume_result.experience
                    for bullet in item.bullet_points
                ],
                *[
                    bullet
                    for item in resume_result.projects
                    for bullet in item.bullet_points
                ],
            ]
        )
    )
    audit_terms = _focus_terms_by_field(job_focus)
    covered: dict[str, list[str]] = {}
    omitted: dict[str, list[str]] = {}

    for field_name, terms in audit_terms.items():
        covered[field_name] = []
        omitted[field_name] = []
        for term in terms:
            if _term_matches_text(term, resume_text):
                covered[field_name].append(term)
            else:
                omitted[field_name].append(term)

    return {
        "covered_terms": covered,
        "omitted_terms": omitted,
    }


def _reorder_category(skills: list[str], job_focus: JobFocus) -> list[str]:
    scored = [
        (skill, _focus_relevance_score(skill, job_focus), index)
        for index, skill in enumerate(skills)
    ]
    scored.sort(key=lambda item: (-item[1], item[2]))
    return [skill for skill, _score, _index in scored]


def _focus_relevance_score(skill: str, job_focus: JobFocus) -> int:
    normalized_skill = _normalize_text(normalize_skill(skill))
    score = 0
    weighted_terms = [
        (job_focus.required_skills, 4),
        (job_focus.preferred_skills, 3),
        (job_focus.responsibilities, 2),
        (job_focus.domain_emphasis, 2),
        (job_focus.summary.split("."), 1),
    ]
    for terms, weight in weighted_terms:
        if any(_term_overlaps_skill(term, normalized_skill) for term in terms):
            score += weight
    return score


def _focus_terms_by_field(job_focus: JobFocus) -> dict[str, list[str]]:
    return {
        "required_skills": _dedupe(job_focus.required_skills),
        "preferred_skills": _dedupe(job_focus.preferred_skills),
        "responsibilities": _dedupe(job_focus.responsibilities),
        "domain_emphasis": _dedupe(job_focus.domain_emphasis),
        "resume_relevant_constraints": _dedupe(job_focus.resume_relevant_constraints),
    }


def _term_overlaps_skill(term: str, normalized_skill: str) -> bool:
    normalized_term = _normalize_text(term)
    if not normalized_term or not normalized_skill:
        return False
    return normalized_skill in normalized_term or normalized_term in normalized_skill


def _term_matches_text(term: str, normalized_text: str) -> bool:
    normalized_term = _normalize_text(term)
    if not normalized_term:
        return False
    if normalized_term in normalized_text:
        return True

    term_tokens = _tokens(normalized_term)
    if len(term_tokens) <= 2:
        return all(token in _tokens(normalized_text) for token in term_tokens)
    matched_count = sum(1 for token in term_tokens if token in _tokens(normalized_text))
    return matched_count >= max(2, len(term_tokens) - 1)


def _normalize_text(text: str) -> str:
    return " ".join(_tokens(text))


def _tokens(text: str) -> list[str]:
    return TOKEN_PATTERN.findall(text.casefold())


def _dedupe(items: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(item.strip() for item in items if item.strip()))
