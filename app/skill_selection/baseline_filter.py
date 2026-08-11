from __future__ import annotations

import logging
from typing import Any

from app.skill_selection.models import SkillSelectRequest
from app.skill_selection.scoring.baseline import baseline_select_skills, normalize_skill
from app.skill_selection.scoring.embeddings import embedding_select_skills
from app.skill_selection.scoring.llm import llm_select_skills

logger = logging.getLogger("baseline_filter")
CATEGORIES = ("technology", "programming", "concepts")


def _focus_job_text(job_text: str | None, job_focus: object | None) -> str | None:
    if job_focus is None:
        return job_text

    focus_parts: list[str] = []
    for field_name in (
        "summary",
        "required_skills",
        "preferred_skills",
        "responsibilities",
        "domain_emphasis",
    ):
        value = getattr(job_focus, field_name, None)
        if isinstance(value, str):
            focus_parts.append(value)
        elif isinstance(value, list):
            focus_parts.extend(item for item in value if isinstance(item, str))

    focus_text = "\n".join(part.strip() for part in focus_parts if part.strip())
    if not focus_text:
        return job_text
    if job_text:
        return f"{focus_text}\n{job_text}"
    return focus_text


def _effective_method(requested_method: str, meta: dict | None) -> str:
    if not isinstance(meta, dict):
        return requested_method

    fallback_method = meta.get("_fallback_method")
    if isinstance(fallback_method, str) and fallback_method:
        return fallback_method

    llm_meta = meta.get("_llm")
    if isinstance(llm_meta, dict) and llm_meta.get("fallback") == "baseline":
        return "baseline"

    return requested_method


def _append_warning(meta: dict, warning: str) -> None:
    warnings = meta.setdefault("_warnings", [])
    if isinstance(warnings, list):
        warnings.append(warning)


def _extend_warnings(meta: dict, source_meta: dict | None) -> None:
    if not isinstance(source_meta, dict):
        return

    warnings = source_meta.get("_warnings")
    if not isinstance(warnings, list):
        return

    target = meta.setdefault("_warnings", [])
    if isinstance(target, list):
        target.extend(warnings)


def _category_inputs(
    *,
    technology: list[str],
    programming: list[str],
    concepts: list[str],
) -> dict[str, list[str]]:
    return {
        "technology": technology,
        "programming": programming,
        "concepts": concepts,
    }


def _normalize_final_score(method: str, raw_score: Any) -> float:
    try:
        score = float(raw_score)
    except (TypeError, ValueError):
        score = 0.0

    if method in {"baseline", "llm"}:
        score = score / 3.0

    return max(0.0, min(1.0, score))


def _call_second_pass_scorer(
    *,
    method: str,
    job_role: str,
    job_text: str | None,
    job_focus: object | None,
    technology: list[str],
    programming: list[str],
    concepts: list[str],
    llm_model: str | None,
    llm_max_output_tokens: int | None,
) -> tuple[dict, dict | None]:
    if method == "embeddings":
        return embedding_select_skills(
            job_role=job_role,
            job_text=_focus_job_text(job_text, job_focus),
            job_focus=job_focus,
            technology=technology,
            programming=programming,
            concepts=concepts,
            top_n=None,
            dev_mode=True,
        )
    if method == "llm":
        return llm_select_skills(
            job_role=job_role,
            job_text=job_text,
            technology=technology,
            programming=programming,
            concepts=concepts,
            top_n=None,
            dev_mode=True,
            llm_model=llm_model,
            llm_max_output_tokens=llm_max_output_tokens,
        )

    raise ValueError(f"Unsupported baseline filter method: {method}")


def _full_baseline_filter_fallback(
    *,
    requested_method: str,
    req: SkillSelectRequest,
    top_n: int | None,
    warning: str,
    second_pass_meta: dict | None = None,
) -> tuple[dict, dict]:
    selected, meta = baseline_select_skills(
        job_role=req.job_role,
        job_text=_focus_job_text(req.job_text, req.job_focus),
        technology=req.technology,
        programming=req.programming,
        concepts=req.concepts,
        top_n=top_n,
        dev_mode=True,
    )
    meta = meta or {}
    _extend_warnings(meta, second_pass_meta)
    _append_warning(meta, warning)
    meta["_fallback_method"] = "baseline"
    meta["_baseline_filter"] = {
        "enabled": True,
        "requested_method": requested_method,
        "fallback": "baseline",
        "fallback_reason": warning,
    }

    if isinstance(second_pass_meta, dict) and isinstance(second_pass_meta.get("_llm"), dict):
        meta["_llm"] = second_pass_meta["_llm"]

    return selected, meta


def select_with_baseline_filter(
    *,
    method: str,
    req: SkillSelectRequest,
    top_n: int | None,
) -> tuple[dict, dict]:
    _, baseline_meta = baseline_select_skills(
        job_role=req.job_role,
        job_text=_focus_job_text(req.job_text, req.job_focus),
        technology=req.technology,
        programming=req.programming,
        concepts=req.concepts,
        top_n=None,
        dev_mode=True,
        include_zero=True,
    )

    baseline_meta = baseline_meta or {}
    original_inputs = _category_inputs(
        technology=req.technology,
        programming=req.programming,
        concepts=req.concepts,
    )
    unrecognized_inputs: dict[str, list[str]] = {category: [] for category in CATEGORIES}
    candidates: dict[str, list[dict[str, Any]]] = {category: [] for category in CATEGORIES}
    counts: dict[str, dict[str, int]] = {}

    for category in CATEGORIES:
        category_details = baseline_meta.get(category, {})
        recognized_count = 0
        unrecognized_count = 0

        for skill in original_inputs[category]:
            details = category_details.get(skill, {}) if isinstance(category_details, dict) else {}
            raw_score = details.get("score", 0.0)
            normalized = details.get("normalized_skill", normalize_skill(skill))
            if raw_score > 0:
                recognized_count += 1
                candidates[category].append(
                    {
                        "skill": skill,
                        "source": "baseline",
                        "baseline_score": raw_score,
                        "normalized_skill": normalized,
                        "normalized_final_score": _normalize_final_score("baseline", raw_score),
                    }
                )
            else:
                unrecognized_count += 1
                unrecognized_inputs[category].append(skill)

        counts[category] = {
            "recognized": recognized_count,
            "unrecognized": unrecognized_count,
            "second_pass_scored": 0,
        }

    second_pass_meta: dict | None = None
    has_unrecognized = any(unrecognized_inputs[category] for category in CATEGORIES)

    if has_unrecognized:
        try:
            _, second_pass_meta = _call_second_pass_scorer(
                method=method,
                job_role=req.job_role,
                job_text=req.job_text,
                job_focus=req.job_focus,
                technology=unrecognized_inputs["technology"],
                programming=unrecognized_inputs["programming"],
                concepts=unrecognized_inputs["concepts"],
                llm_model=req.llm_model,
                llm_max_output_tokens=req.llm_max_output_tokens,
            )
        except Exception as exc:
            logger.warning(
                "baseline_filter_second_pass_failed",
                extra={
                    "event": "baseline_filter_second_pass_failed",
                    "role": req.job_role,
                    "method": method,
                    "error": str(exc),
                },
            )
            return _full_baseline_filter_fallback(
                requested_method=method,
                req=req,
                top_n=top_n,
                warning=f"{method} second-pass selection failed; fell back to baseline: {exc}",
            )

        if _effective_method(method, second_pass_meta) == "baseline":
            return _full_baseline_filter_fallback(
                requested_method=method,
                req=req,
                top_n=top_n,
                warning=f"{method} second-pass selection fell back; returned full baseline selection",
                second_pass_meta=second_pass_meta,
            )

        second_pass_meta = second_pass_meta or {}

        for category in CATEGORIES:
            category_details = second_pass_meta.get(category, {})
            if not isinstance(category_details, dict):
                continue

            for skill in unrecognized_inputs[category]:
                details = category_details.get(skill)
                if not isinstance(details, dict):
                    continue

                normalized = details.get("normalized_skill", normalize_skill(skill))
                candidate = {
                    "skill": skill,
                    "source": method,
                    "normalized_skill": normalized,
                }
                if method == "embeddings":
                    raw_score = details.get("similarity", 0.0)
                    candidate["similarity"] = raw_score
                else:
                    raw_score = details.get("score", 0.0)
                    candidate["method_score"] = raw_score

                candidate["normalized_final_score"] = _normalize_final_score(method, raw_score)
                candidates[category].append(candidate)
                counts[category]["second_pass_scored"] += 1

    selected: dict[str, list[str]] = {}
    details_meta: dict[str, Any] = {}

    for category in CATEGORIES:
        ranked = sorted(
            candidates[category],
            key=lambda item: (
                -item["normalized_final_score"],
                item["normalized_skill"],
                item["skill"],
            ),
        )
        selected[category] = [item["skill"] for item in ranked[:top_n]]
        details_meta[category] = {
            item["skill"]: {
                key: value
                for key, value in item.items()
                if key != "skill"
            }
            for item in ranked
        }

    details_meta["_baseline_filter"] = {
        "enabled": True,
        "requested_method": method,
        "fallback": False,
        "categories": counts,
    }
    _extend_warnings(details_meta, second_pass_meta)

    if isinstance(second_pass_meta, dict) and isinstance(second_pass_meta.get("_llm"), dict):
        details_meta["_llm"] = second_pass_meta["_llm"]

    return selected, details_meta
