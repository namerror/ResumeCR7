from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.project_selection.models import (
    ProjectCandidate,
    ProjectJobContext,
    ProjectSelectionResult,
    RankedProject,
)
from app.skill_selection.scoring.baseline import baseline_select_skills

CATEGORIES = ("technology", "programming", "concepts")
MAX_SKILL_MATCHES = 5
SKILL_SCORE_WEIGHT = 0.75
TEXT_OVERLAP_WEIGHT = 0.25
TOKEN_PATTERN = re.compile(r"[a-z0-9]+(?:#|\+\+)?")
STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "in",
    "into",
    "is",
    "of",
    "on",
    "or",
    "our",
    "that",
    "the",
    "to",
    "with",
}


@dataclass(frozen=True)
class BaselineProjectScore:
    project: ProjectCandidate
    final_score: float
    skill_score: float
    text_overlap_score: float
    matched_skill_count: int
    considered_skill_count: int
    skill_details: dict[str, Any]


def _category_inputs(candidate: ProjectCandidate) -> dict[str, list[str]]:
    return {
        "technology": candidate.skills.technology,
        "programming": candidate.skills.programming,
        "concepts": candidate.skills.concepts,
    }


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in TOKEN_PATTERN.findall(text.lower())
        if token and token not in STOPWORDS
    }


def _normalized_project_name(project: ProjectCandidate) -> str:
    return project.name.strip().casefold()


def text_overlap_score(project_summary: str, context: ProjectJobContext) -> float:
    summary_tokens = _tokens(project_summary)
    job_tokens = _tokens(_context_text(context))
    if not summary_tokens or not job_tokens:
        return 0.0

    return len(summary_tokens & job_tokens) / len(summary_tokens)


def _context_text(context: ProjectJobContext) -> str:
    if context.job_focus is None:
        return f"{context.title} {context.description or ''}"
    focus = context.job_focus
    return " ".join(
        [
            context.title,
            focus.summary,
            *focus.required_skills,
            *focus.preferred_skills,
            *focus.responsibilities,
            *focus.domain_emphasis,
        ]
    )


def score_project_baseline(
    *,
    context: ProjectJobContext,
    candidate: ProjectCandidate,
) -> BaselineProjectScore:
    inputs = _category_inputs(candidate)
    _, skill_details = baseline_select_skills(
        job_role=context.title,
        job_text=_context_text(context),
        technology=inputs["technology"],
        programming=inputs["programming"],
        concepts=inputs["concepts"],
        top_n=None,
        dev_mode=True,
        include_zero=True,
    )

    skill_details = skill_details or {}
    matched_scores: list[float] = []
    for category in CATEGORIES:
        category_details = skill_details.get(category, {})
        if not isinstance(category_details, dict):
            continue
        for details in category_details.values():
            if not isinstance(details, dict):
                continue
            raw_score = details.get("score", 0.0)
            try:
                score = float(raw_score)
            except (TypeError, ValueError):
                score = 0.0
            if score > 0:
                matched_scores.append(score)

    top_scores = sorted(matched_scores, reverse=True)[:MAX_SKILL_MATCHES]
    considered_count = len(top_scores)
    if considered_count:
        skill_score = sum(top_scores) / (3.0 * considered_count)
    else:
        skill_score = 0.0

    overlap_score = text_overlap_score(candidate.summary, context)
    final_score = (SKILL_SCORE_WEIGHT * skill_score) + (TEXT_OVERLAP_WEIGHT * overlap_score)

    return BaselineProjectScore(
        project=candidate,
        final_score=final_score,
        skill_score=skill_score,
        text_overlap_score=overlap_score,
        matched_skill_count=len(matched_scores),
        considered_skill_count=considered_count,
        skill_details=skill_details,
    )


def rank_projects_baseline(
    *,
    context: ProjectJobContext,
    candidates: list[ProjectCandidate],
) -> list[BaselineProjectScore]:
    scored = [
        score_project_baseline(context=context, candidate=candidate)
        for candidate in candidates
    ]
    scored.sort(
        key=lambda item: (
            -item.final_score,
            -item.matched_skill_count,
            -item.text_overlap_score,
            _normalized_project_name(item.project),
            item.project.id,
        )
    )
    return scored


def baseline_select_projects(
    *,
    context: ProjectJobContext,
    candidates: list[ProjectCandidate],
    top_n: int | None = None,
    dev_mode: bool = False,
    warning: str | None = None,
) -> ProjectSelectionResult:
    ranked_scores = rank_projects_baseline(context=context, candidates=candidates)
    selected_scores = ranked_scores[:top_n]
    ranked_projects = [
        RankedProject(
            project_id=score.project.id,
            score=score.final_score,
            method="baseline",
        )
        for score in selected_scores
    ]

    details: dict[str, Any] | None = None
    if dev_mode:
        details = {
            "method": "baseline",
            "projects": {
                score.project.id: {
                    "score": score.final_score,
                    "skill_score": score.skill_score,
                    "text_overlap_score": score.text_overlap_score,
                    "matched_skill_count": score.matched_skill_count,
                    "considered_skill_count": score.considered_skill_count,
                    "skill_details": score.skill_details,
                }
                for score in ranked_scores
            },
        }
        if warning:
            details["_warnings"] = [warning]
            details["_fallback_method"] = "baseline"

    return ProjectSelectionResult(
        selected_project_ids=[project.project_id for project in ranked_projects],
        ranked_projects=ranked_projects,
        details=details,
    )
