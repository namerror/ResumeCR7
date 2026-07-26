from __future__ import annotations

from typing import Any

from app.project_selection.baseline import baseline_select_projects
from app.project_selection.llm import llm_select_projects
from app.project_selection.models import (
    ProjectCandidate,
    ProjectJobContext,
    ProjectSelectionResult,
)


def _coerce_context(context: ProjectJobContext | dict[str, Any]) -> ProjectJobContext:
    return ProjectJobContext.model_validate(context)


def _coerce_candidates(
    candidates: list[ProjectCandidate] | list[dict[str, Any]],
) -> list[ProjectCandidate]:
    return [ProjectCandidate.model_validate(candidate) for candidate in candidates]


def _validate_unique_project_ids(candidates: list[ProjectCandidate]) -> None:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for candidate in candidates:
        if candidate.id in seen:
            duplicates.add(candidate.id)
        seen.add(candidate.id)

    if duplicates:
        duplicate_list = ", ".join(sorted(duplicates))
        raise ValueError(f"Duplicate project ids are not allowed: {duplicate_list}")


def _validate_top_n(top_n: int | None) -> None:
    if top_n is not None and top_n < 0:
        raise ValueError("top_n must be greater than or equal to 0")


def select_projects(
    *,
    context: ProjectJobContext | dict[str, Any],
    candidates: list[ProjectCandidate] | list[dict[str, Any]],
    method: str,
    top_n: int | None = None,
    dev_mode: bool = False,
    llm_model: str | None = None,
    llm_max_output_tokens: int | None = None,
    llm_output_token_budget: object | None = None,
) -> ProjectSelectionResult:
    job_context = _coerce_context(context)
    project_candidates = _coerce_candidates(candidates)
    _validate_unique_project_ids(project_candidates)
    _validate_top_n(top_n)

    normalized_method = method.lower()
    if normalized_method == "baseline":
        return baseline_select_projects(
            context=job_context,
            candidates=project_candidates,
            top_n=top_n,
            dev_mode=dev_mode,
        )
    if normalized_method == "llm":
        return llm_select_projects(
            context=job_context,
            candidates=project_candidates,
            top_n=top_n,
            dev_mode=dev_mode,
            llm_model=llm_model,
            llm_max_output_tokens=llm_max_output_tokens,
            llm_output_token_budget=llm_output_token_budget,
        )

    raise ValueError(f"Unsupported project selection method: {method}")
