from __future__ import annotations

import logging
from typing import Any

from app.project_selection.baseline import baseline_select_projects
from app.project_selection.models import (
    ProjectCandidate,
    ProjectJobContext,
    ProjectSelectionResult,
    RankedProject,
)
from app.project_selection.llm_client import (
    ProjectLLMClientError,
    score_projects_with_llm,
)

logger = logging.getLogger("project_llm_scorer")


class ProjectLLMValidationError(ValueError):
    """Raised when a model response is too malformed to rank safely."""


def _normalized_project_name(project: ProjectCandidate) -> str:
    return project.name.strip().casefold()


def _validate_scores(
    raw_scores: Any,
    candidates: list[ProjectCandidate],
) -> tuple[dict[str, int], list[str]]:
    if not isinstance(raw_scores, dict):
        raise ProjectLLMValidationError("Project LLM scores must be a JSON object")

    allowed_ids = {candidate.id for candidate in candidates}
    valid_scores: dict[str, int] = {}
    warnings: list[str] = []

    for project_id, score in raw_scores.items():
        if project_id not in allowed_ids:
            warnings.append(f"discarded invented project id '{project_id}'")
            continue
        if not isinstance(score, int) or isinstance(score, bool) or score < 0 or score > 3:
            warnings.append(f"discarded invalid score for project '{project_id}'")
            continue
        valid_scores[project_id] = score

    for candidate in candidates:
        if candidate.id not in raw_scores:
            warnings.append(f"missing score for project '{candidate.id}'")

    if candidates and not valid_scores:
        raise ProjectLLMValidationError("Project LLM response contained no valid project scores")

    return valid_scores, warnings


def _fallback_to_baseline(
    *,
    context: ProjectJobContext,
    candidates: list[ProjectCandidate],
    top_n: int | None,
    dev_mode: bool,
    warning: str,
    llm_metadata: dict[str, Any] | None = None,
) -> ProjectSelectionResult:
    result = baseline_select_projects(
        context=context,
        candidates=candidates,
        top_n=top_n,
        dev_mode=dev_mode,
        warning=warning,
    )
    if dev_mode:
        details = result.details or {}
        details["_project_llm"] = {
            "fallback": "baseline",
            "reason": warning,
            **(llm_metadata or {}),
        }
        result.details = details
    return result


def llm_select_projects(
    *,
    context: ProjectJobContext,
    candidates: list[ProjectCandidate],
    top_n: int | None = None,
    dev_mode: bool = False,
    llm_model: str | None = None,
    llm_max_output_tokens: int | None = None,
    llm_output_token_budget: object | None = None,
) -> ProjectSelectionResult:
    llm_metadata: dict[str, Any] | None = None
    try:
        llm_result = score_projects_with_llm(
            context=context,
            candidates=candidates,
            model=llm_model,
            max_output_tokens=llm_max_output_tokens,
            output_token_budget=llm_output_token_budget,
        )
        llm_metadata = llm_result.metadata
        scores, warnings = _validate_scores(llm_result.scores, candidates)
    except (ProjectLLMClientError, ProjectLLMValidationError) as exc:
        if isinstance(exc, ProjectLLMClientError):
            llm_metadata = exc.metadata
        logger.warning(
            "project_llm_fallback_to_baseline",
            extra={
                "event": "project_llm_fallback_to_baseline",
                "job_title": context.title,
                "error": str(exc),
                "requested_llm_max_output_tokens": llm_max_output_tokens,
            },
        )
        return _fallback_to_baseline(
            context=context,
            candidates=candidates,
            top_n=top_n,
            dev_mode=dev_mode,
            warning=f"Project LLM selection failed; fell back to baseline: {exc}",
            llm_metadata=llm_metadata,
        )

    candidates_by_id = {candidate.id: candidate for candidate in candidates}
    ranked = []
    for project_id, score in scores.items():
        candidate = candidates_by_id.get(project_id)
        if candidate is None:
            continue
        ranked.append((candidate, score, score / 3.0))

    ranked.sort(key=lambda item: (-item[2], _normalized_project_name(item[0]), item[0].id))
    selected = ranked[:top_n]
    ranked_projects = [
        RankedProject(project_id=candidate.id, score=normalized_score, method="llm")
        for candidate, _score, normalized_score in selected
    ]

    details: dict[str, Any] | None = None
    if dev_mode:
        details = {
            "method": "llm",
            "projects": {
                candidate.id: {
                    "score": normalized_score,
                    "llm_score": score,
                }
                for candidate, score, normalized_score in ranked
            },
            "_project_llm": llm_result.metadata,
        }
        if warnings:
            details["_warnings"] = warnings

    return ProjectSelectionResult(
        selected_project_ids=[project.project_id for project in ranked_projects],
        ranked_projects=ranked_projects,
        details=details,
    )
