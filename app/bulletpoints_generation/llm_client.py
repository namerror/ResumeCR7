from __future__ import annotations

import json
import logging
import math
import time
from dataclasses import dataclass
from typing import Any, Literal, Mapping

from openai import AsyncOpenAI, OpenAI

from app.bulletpoints_generation.models import (
    BulletCountRange,
    BulletJobContext,
    BulletOutputTokenBudget,
    ExperienceBulletPointSet,
    ProjectBulletPointSet,
)
from app.config import settings
from app.llm_provider import apply_provider_response_options, resolve_llm_provider_config
from app.skill_selection.llm_client import _extract_output_text
from app.skill_selection.llm_client import supports_temperature
from app.resume_evidence.models import ExperienceRecord, ProjectRecord

logger = logging.getLogger("bulletpoints_llm_client")


class BulletPointLLMClientError(RuntimeError):
    """Raised when a bullet-point generation request or response cannot be used."""

    def __init__(self, message: str, metadata: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.metadata = metadata or {}


@dataclass
class LLMBulletPointResult:
    bullet_points: list[str]
    metadata: dict[str, Any]


@dataclass
class LLMResumeSectionBulletPointResult:
    project_bullet_points: list[ProjectBulletPointSet]
    experience_bullet_points: list[ExperienceBulletPointSet]
    metadata: dict[str, Any]


EvidenceType = Literal["project", "experience"]

DEFAULT_BULLET_OUTPUT_TOKEN_BUDGET = BulletOutputTokenBudget()


def build_bulletpoint_schema(count_range: BulletCountRange) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "bullet_points": {
                "type": "array",
                "items": {"type": "string", "minLength": 1},
                "minItems": count_range.min,
                "maxItems": count_range.max,
            }
        },
        "required": ["bullet_points"],
        "additionalProperties": False,
    }


def build_resume_section_bulletpoint_schema(
    *,
    project_ids: list[str],
    experience_ids: list[str],
    project_count_range: BulletCountRange,
    experience_count_range: BulletCountRange,
) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "project_bullet_points": {
                "type": "array",
                "items": _section_bullet_item_schema(
                    id_field="project_id",
                    allowed_ids=project_ids,
                    count_range=project_count_range,
                ),
                "minItems": len(project_ids),
                "maxItems": len(project_ids),
            },
            "experience_bullet_points": {
                "type": "array",
                "items": _section_bullet_item_schema(
                    id_field="experience_id",
                    allowed_ids=experience_ids,
                    count_range=experience_count_range,
                ),
                "minItems": len(experience_ids),
                "maxItems": len(experience_ids),
            },
        },
        "required": ["project_bullet_points", "experience_bullet_points"],
        "additionalProperties": False,
    }


def _section_bullet_item_schema(
    *,
    id_field: str,
    allowed_ids: list[str],
    count_range: BulletCountRange,
) -> dict[str, Any]:
    id_schema: dict[str, Any] = {"type": "string", "minLength": 1}
    if allowed_ids:
        id_schema["enum"] = allowed_ids
    return {
        "type": "object",
        "properties": {
            id_field: id_schema,
            "bullet_points": {
                "type": "array",
                "items": {"type": "string", "minLength": 1},
                "minItems": count_range.min,
                "maxItems": count_range.max,
            },
        },
        "required": [id_field, "bullet_points"],
        "additionalProperties": False,
    }


def build_bulletpoint_prompt_payload(
    *,
    context: BulletJobContext,
    count_range: BulletCountRange,
    project: ProjectRecord | None = None,
    experience: ExperienceRecord | None = None,
) -> str:
    evidence_type, evidence_payload = _build_evidence_payload(
        project=project,
        experience=experience,
    )
    job_payload: dict[str, Any] = {"title": context.title}
    if context.job_focus is not None:
        job_payload["focus"] = context.job_focus.model_dump()
    else:
        job_payload["description"] = context.description or ""

    payload = {
        "job": job_payload,
        evidence_type: evidence_payload,
        "bullet_count_range": count_range.model_dump(),
        "grounding_rules": [
            f"Use only the supplied {evidence_type} evidence as the source of user experience.",
            "The job focus or description may guide emphasis but is not evidence of user experience.",
            "Omit unsupported claims instead of guessing.",
            "Return plain bullet text without leading bullet symbols.",
        ],
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def build_resume_section_bulletpoint_prompt_payload(
    *,
    context: BulletJobContext,
    projects: list[ProjectRecord],
    experiences: list[ExperienceRecord],
    project_count_range: BulletCountRange,
    experience_count_range: BulletCountRange,
) -> str:
    job_payload: dict[str, Any] = {"title": context.title}
    if context.job_focus is not None:
        job_payload["focus"] = context.job_focus.model_dump()
    else:
        job_payload["description"] = context.description or ""

    payload = {
        "job": job_payload,
        "projects": [
            _build_evidence_payload(project=project)[1] for project in projects
        ],
        "experiences": [
            _build_evidence_payload(experience=experience)[1]
            for experience in experiences
        ],
        "bullet_count_ranges": {
            "projects": project_count_range.model_dump(),
            "experiences": experience_count_range.model_dump(),
        },
        "grounding_rules": [
            "Use only the supplied project and experience evidence as the source of user experience.",
            "The job focus or description may guide emphasis but is not evidence of user experience.",
            "Omit unsupported claims instead of guessing.",
            "Return plain bullet text without leading bullet symbols.",
        ],
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def build_bulletpoint_instructions(
    count_range: BulletCountRange,
    evidence_type: EvidenceType = "project",
) -> str:
    count_instruction = (
        f"Return exactly {count_range.min} bullet point strings."
        if count_range.min == count_range.max
        else (
            f"Return between {count_range.min} and {count_range.max} bullet point strings, "
            "choosing the count that best represents the supplied evidence."
        )
    )
    return (
        "You are a deterministic resume bullet writer. Return JSON only. "
        f"{count_instruction} Write grounded, recruiter-readable resume bullets for "
        f"the supplied {evidence_type} evidence and target job. Use only the supplied "
        f"{evidence_type} summary, highlights, skills, and factual fields as evidence "
        "of the user's work. The job focus or description may guide emphasis, but it "
        "is not evidence of user experience. Omit unsupported claims instead of "
        "guessing. When job focus is provided, identify exact required skill, "
        "preferred skill, responsibility, and domain-emphasis phrases that are "
        "directly supported by the evidence, then use those exact employer terms "
        "where they fit naturally. Prioritize supported target keywords in the "
        "strongest bullets, especially required skills and responsibilities. Do not "
        "name target technologies, systems, papers, or methods that are absent from "
        "the evidence. Treat the evidence as raw factual notes. Rewrite it into concise "
        "accomplishment statements; do not copy the evidence wording, structure, or "
        "tone. Each bullet must start with a past-tense action verb and follow this "
        "structure: action + purpose/context + method/tool + supported impact. Use "
        "past-tense action verbs for all bullets. Do not infer tense from eligibility, "
        "dates, or record status. Target 18 to 26 words and never exceed 32 words. "
        "Express one main accomplishment only. Use metrics only when the evidence "
        "supports them; otherwise use a "
        "concrete qualitative outcome or purpose. Prefer clear verbs and nouns over "
        "filler such as robust, seamless, cutting-edge, leveraged, utilized, enhanced, "
        "or optimized unless the evidence proves the improvement. For project bullets, "
        "make the first bullet explain what the project/system does and who or what "
        "it serves. Use later bullets to zoom into architecture, implementation "
        "details, technical highlights, or measured outcomes. The full set of bullets "
        "should let a non-specialist technical recruiter understand the project "
        "purpose before reading deep implementation details. For experience bullets, "
        "lead with the highest-value contribution for the role. Avoid repeating "
        "duties; focus on contributions, decisions, and outcomes. Do not use leading "
        "bullet markers. "
        "Do not use semicolons. Do not use internal dash separators. Hyphens are "
        "allowed only inside established terms such as end-to-end, role-based, or "
        "official technical names. Vary the opening verbs across bullets for the same "
        "record. Avoid repeating the same technology list in every bullet; mention "
        "tools only where they clarify the method. Use plain ASCII text only so the "
        "bullets can be rendered by pdfLaTeX. Do not use smart quotes, Unicode "
        "dashes, arrows, approximation signs, bullets, emoji, or non-ASCII symbols. "
        "Write words such as about or to instead of symbols when needed."
    )


def build_resume_section_bulletpoint_instructions(
    *,
    project_count_range: BulletCountRange,
    experience_count_range: BulletCountRange,
) -> str:
    return (
        "You are a deterministic resume section bullet writer. Return JSON only. "
        f"For each project, return {_count_range_instruction(project_count_range)}. "
        f"For each experience, return {_count_range_instruction(experience_count_range)}. "
        "Write grounded, recruiter-readable resume bullets for the supplied selected "
        "projects, selected experiences, and target job. Use only the supplied "
        "summaries, highlights, skills, and factual fields as evidence of the user's "
        "work. The job focus or description may guide emphasis, but it is not "
        "evidence of user experience. Omit unsupported claims instead of guessing. "
        "When job focus is provided, identify exact required skill, preferred skill, "
        "responsibility, and domain-emphasis phrases that are directly supported by "
        "each record's evidence, then use those exact employer terms where they fit "
        "naturally. Prioritize supported target keywords in the strongest bullets, "
        "especially required skills and responsibilities. Do not name target "
        "technologies, systems, papers, or methods that are absent from the evidence. "
        "Treat the evidence as raw factual notes. Rewrite it into concise "
        "accomplishment statements; do not copy the evidence wording, structure, or "
        "tone. Every bullet must start with a past-tense action verb. Use "
        "past-tense action verbs for all bullets. Do not infer tense from eligibility, "
        "dates, or record status. Each bullet should follow this "
        "structure when supported: action + purpose/context + method/tool + impact. "
        "Target 18 to 26 words and never exceed 32 words. Express one main "
        "accomplishment only. Use metrics only when the evidence supports them; "
        "otherwise use a concrete qualitative outcome or purpose. Prefer clear "
        "verbs and nouns over filler such as robust, seamless, cutting-edge, "
        "leveraged, utilized, enhanced, or optimized unless the evidence proves "
        "the improvement. For each project, make the first bullet explain what "
        "the project/system did and who or what it served. Use later bullets for "
        "architecture, implementation details, technical highlights, or measured "
        "outcomes. For experiences, lead with the highest-value contribution for "
        "the target role. Coordinate the full Experience and Projects sections: "
        "vary opening verbs across all bullets, avoid repetitive sentence frames, "
        "avoid overusing develop, implement, build, or forms of those verbs, and "
        "avoid repeating ', enabling ...' as the default impact clause. Every "
        "bullet must end with terminal punctuation. Do not use leading bullet "
        "markers. Do not use semicolons. Do not use internal dash separators. "
        "Hyphens are allowed only inside established terms such as end-to-end, "
        "role-based, or official technical names. Avoid repeating the same "
        "technology list in every bullet; mention tools only where they clarify "
        "the method. Use plain ASCII text only so the bullets can be rendered by "
        "pdfLaTeX. Do not use smart quotes, Unicode dashes, arrows, approximation "
        "signs, bullets, emoji, or non-ASCII symbols. Write words such as about "
        "or to instead of symbols when needed."
    )


def _count_range_instruction(count_range: BulletCountRange) -> str:
    if count_range.min == count_range.max:
        return f"exactly {count_range.min} bullet point strings"
    return (
        f"between {count_range.min} and {count_range.max} bullet point strings, "
        "choosing the count that best represents the supplied evidence"
    )


def _build_evidence_payload(
    *,
    project: ProjectRecord | None = None,
    experience: ExperienceRecord | None = None,
) -> tuple[EvidenceType, dict[str, Any]]:
    evidence_count = int(project is not None) + int(experience is not None)
    if evidence_count != 1:
        raise BulletPointLLMClientError(
            "Exactly one of project or experience must be provided"
        )

    if project is not None:
        return (
            "project",
            {
                "id": project.id,
                "name": project.name,
                "summary": project.summary,
                "highlights": project.highlights,
                "skills": project.skills.model_dump(),
            },
        )

    if experience is None:
        raise BulletPointLLMClientError(
            "Exactly one of project or experience must be provided"
        )

    return (
        "experience",
        {
            "id": experience.id,
            "name": experience.name,
            "role": experience.role,
            "summary": experience.summary,
            "highlights": experience.highlights,
            "skills": experience.skills.model_dump(),
            "location": experience.location,
        },
    )


def _usage_metadata(response: Any) -> dict[str, int]:
    usage = getattr(response, "usage", None)
    return {
        "prompt_tokens": int(getattr(usage, "input_tokens", 0) or 0),
        "completion_tokens": int(getattr(usage, "output_tokens", 0) or 0),
        "total_tokens": int(getattr(usage, "total_tokens", 0) or 0),
    }


def _budget_dict(budget: BulletOutputTokenBudget | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(budget, BulletOutputTokenBudget):
        return budget.model_dump()
    return dict(budget)


def _apply_optional_cap(value: int, max_value: int | None) -> int:
    return min(value, max_value) if max_value is not None else value


def resolve_bulletpoint_max_output_tokens(
    *,
    prompt_payload: str,
    count_range: BulletCountRange,
    highlight_count: int,
    max_output_tokens: int | None = None,
    output_token_budget: BulletOutputTokenBudget | Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    budget = (
        output_token_budget
        if output_token_budget is not None
        else DEFAULT_BULLET_OUTPUT_TOKEN_BUDGET
    )
    budget_config = _budget_dict(budget)
    evidence_1k_chars = math.ceil(len(prompt_payload) / 1000)
    if max_output_tokens is not None:
        return {
            "mode": "override",
            "requested_llm_max_output_tokens": max_output_tokens,
            "resolved_llm_max_output_tokens": max_output_tokens,
            "config": budget_config,
            "inputs": {
                "requested_max_bullets": count_range.max,
                "highlight_count": highlight_count,
                "evidence_json_chars": len(prompt_payload),
                "evidence_1k_chars": evidence_1k_chars,
            },
        }

    calculated = (
        int(budget_config["base"])
        + int(budget_config["per_bullet"]) * count_range.max
        + int(budget_config["per_highlight"]) * highlight_count
        + int(budget_config["per_evidence_1k_chars"]) * evidence_1k_chars
    )
    resolved = max(int(budget_config["min"]), calculated)
    resolved = _apply_optional_cap(resolved, budget_config.get("max"))
    return {
        "mode": "dynamic",
        "requested_llm_max_output_tokens": None,
        "resolved_llm_max_output_tokens": resolved,
        "config": budget_config,
        "inputs": {
            "requested_max_bullets": count_range.max,
            "highlight_count": highlight_count,
            "evidence_json_chars": len(prompt_payload),
            "evidence_1k_chars": evidence_1k_chars,
            "calculated_max_output_tokens": calculated,
        },
    }


def resolve_resume_section_bulletpoint_max_output_tokens(
    *,
    prompt_payload: str,
    requested_max_bullets: int,
    highlight_count: int,
    max_output_tokens: int | None = None,
    output_token_budget: BulletOutputTokenBudget | Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    budget = (
        output_token_budget
        if output_token_budget is not None
        else DEFAULT_BULLET_OUTPUT_TOKEN_BUDGET
    )
    budget_config = _budget_dict(budget)
    evidence_1k_chars = math.ceil(len(prompt_payload) / 1000)
    if max_output_tokens is not None:
        return {
            "mode": "override",
            "requested_llm_max_output_tokens": max_output_tokens,
            "resolved_llm_max_output_tokens": max_output_tokens,
            "config": budget_config,
            "inputs": {
                "requested_max_bullets": requested_max_bullets,
                "highlight_count": highlight_count,
                "evidence_json_chars": len(prompt_payload),
                "evidence_1k_chars": evidence_1k_chars,
            },
        }

    calculated = (
        int(budget_config["base"])
        + int(budget_config["per_bullet"]) * requested_max_bullets
        + int(budget_config["per_highlight"]) * highlight_count
        + int(budget_config["per_evidence_1k_chars"]) * evidence_1k_chars
    )
    resolved = max(int(budget_config["min"]), calculated)
    resolved = _apply_optional_cap(resolved, budget_config.get("max"))
    return {
        "mode": "dynamic",
        "requested_llm_max_output_tokens": None,
        "resolved_llm_max_output_tokens": resolved,
        "config": budget_config,
        "inputs": {
            "requested_max_bullets": requested_max_bullets,
            "highlight_count": highlight_count,
            "evidence_json_chars": len(prompt_payload),
            "evidence_1k_chars": evidence_1k_chars,
            "calculated_max_output_tokens": calculated,
        },
    }


def _aggregate_attempt_metadata(
    attempts: list[dict[str, Any]],
    *,
    model: str,
    latency_ms: float,
    token_budget: dict[str, Any],
) -> dict[str, Any]:
    return {
        "model": model,
        "api_calls": len(attempts),
        "latency_ms": round(latency_ms, 3),
        "prompt_tokens": sum(int(attempt.get("prompt_tokens", 0) or 0) for attempt in attempts),
        "completion_tokens": sum(
            int(attempt.get("completion_tokens", 0) or 0) for attempt in attempts
        ),
        "total_tokens": sum(int(attempt.get("total_tokens", 0) or 0) for attempt in attempts),
        "attempts": attempts,
        "requested_llm_max_output_tokens": token_budget["requested_llm_max_output_tokens"],
        "resolved_llm_max_output_tokens": token_budget["resolved_llm_max_output_tokens"],
        "llm_output_token_budget_mode": token_budget["mode"],
        "llm_output_token_budget": token_budget["config"],
        "llm_output_token_budget_inputs": token_budget["inputs"],
    }


def build_bulletpoint_response_create_kwargs(
    *,
    model: str,
    instructions: str,
    prompt_payload: str,
    schema: dict[str, Any],
    max_output_tokens: int,
    schema_name: str = "project_bullet_points",
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "model": model,
        "instructions": instructions,
        "input": prompt_payload,
        "max_output_tokens": max_output_tokens,
        "tools": [],
        "text": {
            "format": {
                "type": "json_schema",
                "name": schema_name,
                "schema": schema,
                "strict": True,
            }
        },
    }
    if supports_temperature(model):
        kwargs["temperature"] = 0
    return kwargs


def _validate_bullet_points(raw_response: Any, count_range: BulletCountRange) -> list[str]:
    if not isinstance(raw_response, dict):
        raise BulletPointLLMClientError("Bullet-point LLM response must be a JSON object")

    raw_bullets = raw_response.get("bullet_points")
    if not isinstance(raw_bullets, list):
        raise BulletPointLLMClientError("Bullet-point LLM response must include bullet_points")

    bullets: list[str] = []
    for index, bullet in enumerate(raw_bullets, start=1):
        bullets.append(_normalize_bullet_point(bullet, index=index))

    if len(bullets) < count_range.min or len(bullets) > count_range.max:
        raise BulletPointLLMClientError(
            "Bullet-point LLM response count was outside the requested range"
        )

    return bullets


def _normalize_bullet_point(raw_bullet: Any, *, index: int) -> str:
    if not isinstance(raw_bullet, str):
        raise BulletPointLLMClientError(f"Bullet point {index} must be a string")
    normalized = raw_bullet.strip()
    if not normalized:
        raise BulletPointLLMClientError(f"Bullet point {index} must not be empty")
    cleaned = normalized.lstrip("-* ").strip()
    if not cleaned:
        raise BulletPointLLMClientError(f"Bullet point {index} must not be empty")
    if cleaned[-1] not in ".!?":
        cleaned = f"{cleaned}."
    return cleaned


def _validate_resume_section_bullet_points(
    raw_response: Any,
    *,
    project_ids: list[str],
    experience_ids: list[str],
    project_count_range: BulletCountRange,
    experience_count_range: BulletCountRange,
) -> tuple[list[ProjectBulletPointSet], list[ExperienceBulletPointSet]]:
    if not isinstance(raw_response, dict):
        raise BulletPointLLMClientError(
            "Resume section bullet-point LLM response must be a JSON object"
        )

    project_items = _validate_section_items(
        raw_response.get("project_bullet_points"),
        id_field="project_id",
        expected_ids=project_ids,
        count_range=project_count_range,
        label="project",
    )
    experience_items = _validate_section_items(
        raw_response.get("experience_bullet_points"),
        id_field="experience_id",
        expected_ids=experience_ids,
        count_range=experience_count_range,
        label="experience",
    )

    project_by_id = {
        item["id"]: ProjectBulletPointSet(
            project_id=item["id"],
            bullet_points=item["bullet_points"],
        )
        for item in project_items
    }
    experience_by_id = {
        item["id"]: ExperienceBulletPointSet(
            experience_id=item["id"],
            bullet_points=item["bullet_points"],
        )
        for item in experience_items
    }
    return (
        [project_by_id[project_id] for project_id in project_ids],
        [experience_by_id[experience_id] for experience_id in experience_ids],
    )


def _validate_section_items(
    raw_items: Any,
    *,
    id_field: str,
    expected_ids: list[str],
    count_range: BulletCountRange,
    label: str,
) -> list[dict[str, Any]]:
    if not isinstance(raw_items, list):
        raise BulletPointLLMClientError(
            f"Resume section response must include {label} bullet-point objects"
        )
    if len(raw_items) != len(expected_ids):
        raise BulletPointLLMClientError(
            f"Resume section response returned the wrong number of {label} records"
        )

    expected_id_set = set(expected_ids)
    seen_ids: set[str] = set()
    validated: list[dict[str, Any]] = []
    for item_index, item in enumerate(raw_items, start=1):
        if not isinstance(item, dict):
            raise BulletPointLLMClientError(
                f"{label.title()} bullet-point item {item_index} must be an object"
            )
        raw_id = item.get(id_field)
        if not isinstance(raw_id, str) or not raw_id.strip():
            raise BulletPointLLMClientError(
                f"{label.title()} bullet-point item {item_index} must include {id_field}"
            )
        item_id = raw_id.strip()
        if item_id not in expected_id_set:
            raise BulletPointLLMClientError(f"Unknown {label} id in response: {item_id}")
        if item_id in seen_ids:
            raise BulletPointLLMClientError(f"Duplicate {label} id in response: {item_id}")
        seen_ids.add(item_id)
        bullets = _validate_bullet_points(
            {"bullet_points": item.get("bullet_points")},
            count_range,
        )
        validated.append({"id": item_id, "bullet_points": bullets})

    missing_ids = [item_id for item_id in expected_ids if item_id not in seen_ids]
    if missing_ids:
        raise BulletPointLLMClientError(
            f"Resume section response missed {label} ids: {', '.join(missing_ids)}"
        )
    return validated


def generate_bulletpoints_with_llm(
    *,
    context: BulletJobContext,
    count_range: BulletCountRange,
    project: ProjectRecord | None = None,
    experience: ExperienceRecord | None = None,
    model: str | None = None,
    max_output_tokens: int | None = None,
    output_token_budget: BulletOutputTokenBudget | Mapping[str, Any] | None = None,
) -> LLMBulletPointResult:
    evidence_type, _ = _build_evidence_payload(
        project=project,
        experience=experience,
    )
    prompt_payload = build_bulletpoint_prompt_payload(
        context=context,
        project=project,
        experience=experience,
        count_range=count_range,
    )
    schema = build_bulletpoint_schema(count_range)
    instructions = build_bulletpoint_instructions(count_range, evidence_type=evidence_type)

    provider_config = resolve_llm_provider_config(
        stage="bulletpoints_generation",
        requested_model=model,
        default_openai_model=settings.BULLETPOINTS_LLM_MODEL,
    )
    if not provider_config.api_key.strip():
        raise BulletPointLLMClientError(
            f"{provider_config.api_key_setting_name} is required for bullet-point generation"
        )

    effective_model = provider_config.model
    source_record = project if project is not None else experience
    highlight_count = len(source_record.highlights) if source_record is not None else 0
    token_budget = resolve_bulletpoint_max_output_tokens(
        prompt_payload=prompt_payload,
        count_range=count_range,
        highlight_count=highlight_count,
        max_output_tokens=max_output_tokens,
        output_token_budget=output_token_budget,
    )
    effective_max_output_tokens = token_budget["resolved_llm_max_output_tokens"]

    start = time.perf_counter()
    attempts: list[dict[str, Any]] = []
    retry_reason: str | None = None

    try:
        client = OpenAI(**provider_config.client_kwargs())
    except Exception as exc:
        logger.exception(
            "bulletpoints_llm_request_failed",
            extra={
                "event": "bulletpoints_llm_request_failed",
                "subsystem": "bulletpoints_generation",
                "model": effective_model,
                "attempt": 0,
                "resolved_llm_max_output_tokens": effective_max_output_tokens,
            },
        )
        raise BulletPointLLMClientError(
            f"Bullet-point LLM request failed: {exc}"
        ) from exc
    max_output_tokens_by_attempt = [
        effective_max_output_tokens,
        _apply_optional_cap(
            max(effective_max_output_tokens * 2, 3000),
            token_budget["config"].get("max"),
        ),
    ]
    max_output_tokens_by_attempt = list(dict.fromkeys(max_output_tokens_by_attempt))

    for attempt_index, attempt_max_output_tokens in enumerate(
        max_output_tokens_by_attempt,
        start=1,
    ):
        try:
            create_kwargs = build_bulletpoint_response_create_kwargs(
                model=effective_model,
                instructions=instructions,
                prompt_payload=prompt_payload,
                schema=schema,
                max_output_tokens=attempt_max_output_tokens,
                schema_name=f"{evidence_type}_bullet_points",
            )
            apply_provider_response_options(create_kwargs, provider_config)
            response = client.responses.create(**create_kwargs)
        except Exception as exc:
            attempt_metadata = {
                "attempt": attempt_index,
                "max_output_tokens": attempt_max_output_tokens,
                "error": f"Bullet-point LLM request failed: {exc}",
            }
            attempts.append(attempt_metadata)
            latency_ms = (time.perf_counter() - start) * 1000.0
            metadata = _aggregate_attempt_metadata(
                attempts,
                model=effective_model,
                latency_ms=latency_ms,
                token_budget=token_budget,
            )
            metadata.update(provider_config.metadata())
            logger.exception(
                "bulletpoints_llm_request_failed",
                extra={
                    "event": "bulletpoints_llm_request_failed",
                    "subsystem": "bulletpoints_generation",
                    "model": effective_model,
                    "attempt": attempt_index,
                    "resolved_llm_max_output_tokens": attempt_max_output_tokens,
                },
            )
            raise BulletPointLLMClientError(
                f"Bullet-point LLM request failed: {exc}",
                metadata=metadata,
            ) from exc

        attempt_metadata = {
            "attempt": attempt_index,
            "max_output_tokens": attempt_max_output_tokens,
            **_usage_metadata(response),
        }
        attempts.append(attempt_metadata)

        output_text = _extract_output_text(response)
        if not output_text:
            retry_reason = "Bullet-point LLM response did not include output_text"
            attempt_metadata["error"] = retry_reason
        else:
            try:
                raw_response = json.loads(output_text)
            except json.JSONDecodeError as exc:
                retry_reason = f"Bullet-point LLM response was not valid JSON: {exc}"
                attempt_metadata["error"] = retry_reason
            else:
                bullets = _validate_bullet_points(raw_response, count_range)
                latency_ms = (time.perf_counter() - start) * 1000.0
                metadata = _aggregate_attempt_metadata(
                    attempts,
                    model=effective_model,
                    latency_ms=latency_ms,
                    token_budget=token_budget,
                )
                metadata.update(provider_config.metadata())
                if retry_reason is not None:
                    metadata["retry_reason"] = retry_reason
                return LLMBulletPointResult(bullet_points=bullets, metadata=metadata)

        if attempt_index == len(max_output_tokens_by_attempt):
            latency_ms = (time.perf_counter() - start) * 1000.0
            metadata = _aggregate_attempt_metadata(
                attempts,
                model=effective_model,
                latency_ms=latency_ms,
                token_budget=token_budget,
            )
            metadata.update(provider_config.metadata())
            if retry_reason is not None:
                metadata["retry_reason"] = retry_reason
            raise BulletPointLLMClientError(
                retry_reason or "Bullet-point LLM response could not be parsed",
                metadata=metadata,
            )

        logger.warning(
            "bulletpoints_llm_response_retry",
            extra={
                "event": "bulletpoints_llm_response_retry",
                "subsystem": "bulletpoints_generation",
                "model": effective_model,
                "attempt": attempt_index,
                "resolved_llm_max_output_tokens": attempt_max_output_tokens,
                "retry_reason": retry_reason,
            },
        )

    raise BulletPointLLMClientError("Bullet-point LLM response could not be parsed")


def generate_resume_section_bulletpoints_with_llm(
    *,
    context: BulletJobContext,
    projects: list[ProjectRecord],
    experiences: list[ExperienceRecord],
    project_count_range: BulletCountRange,
    experience_count_range: BulletCountRange,
    model: str | None = None,
    max_output_tokens: int | None = None,
    output_token_budget: BulletOutputTokenBudget | Mapping[str, Any] | None = None,
) -> LLMResumeSectionBulletPointResult:
    project_ids = [project.id for project in projects]
    experience_ids = [experience.id for experience in experiences]
    prompt_payload = build_resume_section_bulletpoint_prompt_payload(
        context=context,
        projects=projects,
        experiences=experiences,
        project_count_range=project_count_range,
        experience_count_range=experience_count_range,
    )
    schema = build_resume_section_bulletpoint_schema(
        project_ids=project_ids,
        experience_ids=experience_ids,
        project_count_range=project_count_range,
        experience_count_range=experience_count_range,
    )
    instructions = build_resume_section_bulletpoint_instructions(
        project_count_range=project_count_range,
        experience_count_range=experience_count_range,
    )

    provider_config = resolve_llm_provider_config(
        stage="bulletpoints_generation",
        requested_model=model,
        default_openai_model=settings.BULLETPOINTS_LLM_MODEL,
    )
    if not provider_config.api_key.strip():
        raise BulletPointLLMClientError(
            f"{provider_config.api_key_setting_name} is required for bullet-point generation"
        )

    effective_model = provider_config.model
    highlight_count = sum(len(project.highlights) for project in projects) + sum(
        len(experience.highlights) for experience in experiences
    )
    requested_max_bullets = (
        len(projects) * project_count_range.max
        + len(experiences) * experience_count_range.max
    )
    token_budget = resolve_resume_section_bulletpoint_max_output_tokens(
        prompt_payload=prompt_payload,
        requested_max_bullets=requested_max_bullets,
        highlight_count=highlight_count,
        max_output_tokens=max_output_tokens,
        output_token_budget=output_token_budget,
    )
    effective_max_output_tokens = token_budget["resolved_llm_max_output_tokens"]

    start = time.perf_counter()
    attempts: list[dict[str, Any]] = []
    retry_reason: str | None = None

    try:
        client = OpenAI(**provider_config.client_kwargs())
    except Exception as exc:
        logger.exception(
            "resume_section_bulletpoints_llm_request_failed",
            extra={
                "event": "resume_section_bulletpoints_llm_request_failed",
                "subsystem": "bulletpoints_generation",
                "model": effective_model,
                "attempt": 0,
                "resolved_llm_max_output_tokens": effective_max_output_tokens,
            },
        )
        raise BulletPointLLMClientError(
            f"Resume section bullet-point LLM request failed: {exc}"
        ) from exc

    max_output_tokens_by_attempt = [
        effective_max_output_tokens,
        _apply_optional_cap(
            max(effective_max_output_tokens * 2, 3000),
            token_budget["config"].get("max"),
        ),
    ]
    max_output_tokens_by_attempt = list(dict.fromkeys(max_output_tokens_by_attempt))

    for attempt_index, attempt_max_output_tokens in enumerate(
        max_output_tokens_by_attempt,
        start=1,
    ):
        try:
            create_kwargs = build_bulletpoint_response_create_kwargs(
                model=effective_model,
                instructions=instructions,
                prompt_payload=prompt_payload,
                schema=schema,
                max_output_tokens=attempt_max_output_tokens,
                schema_name="resume_section_bullet_points",
            )
            apply_provider_response_options(create_kwargs, provider_config)
            response = client.responses.create(**create_kwargs)
        except Exception as exc:
            attempt_metadata = {
                "attempt": attempt_index,
                "max_output_tokens": attempt_max_output_tokens,
                "error": f"Resume section bullet-point LLM request failed: {exc}",
            }
            attempts.append(attempt_metadata)
            latency_ms = (time.perf_counter() - start) * 1000.0
            metadata = _aggregate_attempt_metadata(
                attempts,
                model=effective_model,
                latency_ms=latency_ms,
                token_budget=token_budget,
            )
            metadata.update(provider_config.metadata())
            logger.exception(
                "resume_section_bulletpoints_llm_request_failed",
                extra={
                    "event": "resume_section_bulletpoints_llm_request_failed",
                    "subsystem": "bulletpoints_generation",
                    "model": effective_model,
                    "attempt": attempt_index,
                    "resolved_llm_max_output_tokens": attempt_max_output_tokens,
                },
            )
            raise BulletPointLLMClientError(
                f"Resume section bullet-point LLM request failed: {exc}",
                metadata=metadata,
            ) from exc

        attempt_metadata = {
            "attempt": attempt_index,
            "max_output_tokens": attempt_max_output_tokens,
            **_usage_metadata(response),
        }
        attempts.append(attempt_metadata)

        output_text = _extract_output_text(response)
        if not output_text:
            retry_reason = "Resume section bullet-point LLM response did not include output_text"
            attempt_metadata["error"] = retry_reason
        else:
            try:
                raw_response = json.loads(output_text)
            except json.JSONDecodeError as exc:
                retry_reason = (
                    f"Resume section bullet-point LLM response was not valid JSON: {exc}"
                )
                attempt_metadata["error"] = retry_reason
            else:
                project_bullets, experience_bullets = (
                    _validate_resume_section_bullet_points(
                        raw_response,
                        project_ids=project_ids,
                        experience_ids=experience_ids,
                        project_count_range=project_count_range,
                        experience_count_range=experience_count_range,
                    )
                )
                latency_ms = (time.perf_counter() - start) * 1000.0
                metadata = _aggregate_attempt_metadata(
                    attempts,
                    model=effective_model,
                    latency_ms=latency_ms,
                    token_budget=token_budget,
                )
                metadata.update(provider_config.metadata())
                if retry_reason is not None:
                    metadata["retry_reason"] = retry_reason
                return LLMResumeSectionBulletPointResult(
                    project_bullet_points=project_bullets,
                    experience_bullet_points=experience_bullets,
                    metadata=metadata,
                )

        if attempt_index == len(max_output_tokens_by_attempt):
            latency_ms = (time.perf_counter() - start) * 1000.0
            metadata = _aggregate_attempt_metadata(
                attempts,
                model=effective_model,
                latency_ms=latency_ms,
                token_budget=token_budget,
            )
            metadata.update(provider_config.metadata())
            if retry_reason is not None:
                metadata["retry_reason"] = retry_reason
            raise BulletPointLLMClientError(
                retry_reason
                or "Resume section bullet-point LLM response could not be parsed",
                metadata=metadata,
            )

        logger.warning(
            "resume_section_bulletpoints_llm_response_retry",
            extra={
                "event": "resume_section_bulletpoints_llm_response_retry",
                "subsystem": "bulletpoints_generation",
                "model": effective_model,
                "attempt": attempt_index,
                "resolved_llm_max_output_tokens": attempt_max_output_tokens,
                "retry_reason": retry_reason,
            },
        )

    raise BulletPointLLMClientError(
        "Resume section bullet-point LLM response could not be parsed"
    )


async def generate_bulletpoints_with_llm_async(
    *,
    context: BulletJobContext,
    count_range: BulletCountRange,
    project: ProjectRecord | None = None,
    experience: ExperienceRecord | None = None,
    model: str | None = None,
    max_output_tokens: int | None = None,
    output_token_budget: BulletOutputTokenBudget | Mapping[str, Any] | None = None,
) -> LLMBulletPointResult:
    evidence_type, _ = _build_evidence_payload(
        project=project,
        experience=experience,
    )
    prompt_payload = build_bulletpoint_prompt_payload(
        context=context,
        project=project,
        experience=experience,
        count_range=count_range,
    )
    schema = build_bulletpoint_schema(count_range)
    instructions = build_bulletpoint_instructions(count_range, evidence_type=evidence_type)

    provider_config = resolve_llm_provider_config(
        stage="bulletpoints_generation",
        requested_model=model,
        default_openai_model=settings.BULLETPOINTS_LLM_MODEL,
    )
    if not provider_config.api_key.strip():
        raise BulletPointLLMClientError(
            f"{provider_config.api_key_setting_name} is required for bullet-point generation"
        )

    effective_model = provider_config.model
    source_record = project if project is not None else experience
    highlight_count = len(source_record.highlights) if source_record is not None else 0
    token_budget = resolve_bulletpoint_max_output_tokens(
        prompt_payload=prompt_payload,
        count_range=count_range,
        highlight_count=highlight_count,
        max_output_tokens=max_output_tokens,
        output_token_budget=output_token_budget,
    )
    effective_max_output_tokens = token_budget["resolved_llm_max_output_tokens"]

    start = time.perf_counter()
    attempts: list[dict[str, Any]] = []
    retry_reason: str | None = None

    try:
        client = AsyncOpenAI(**provider_config.client_kwargs())
    except Exception as exc:
        logger.exception(
            "bulletpoints_llm_request_failed",
            extra={
                "event": "bulletpoints_llm_request_failed",
                "subsystem": "bulletpoints_generation",
                "model": effective_model,
                "attempt": 0,
                "resolved_llm_max_output_tokens": effective_max_output_tokens,
            },
        )
        raise BulletPointLLMClientError(
            f"Bullet-point LLM request failed: {exc}"
        ) from exc

    max_output_tokens_by_attempt = [
        effective_max_output_tokens,
        _apply_optional_cap(
            max(effective_max_output_tokens * 2, 3000),
            token_budget["config"].get("max"),
        ),
    ]
    max_output_tokens_by_attempt = list(dict.fromkeys(max_output_tokens_by_attempt))

    try:
        for attempt_index, attempt_max_output_tokens in enumerate(
            max_output_tokens_by_attempt,
            start=1,
        ):
            try:
                create_kwargs = build_bulletpoint_response_create_kwargs(
                    model=effective_model,
                    instructions=instructions,
                    prompt_payload=prompt_payload,
                    schema=schema,
                    max_output_tokens=attempt_max_output_tokens,
                    schema_name=f"{evidence_type}_bullet_points",
                )
                apply_provider_response_options(create_kwargs, provider_config)
                response = await client.responses.create(**create_kwargs)
            except Exception as exc:
                attempt_metadata = {
                    "attempt": attempt_index,
                    "max_output_tokens": attempt_max_output_tokens,
                    "error": f"Bullet-point LLM request failed: {exc}",
                }
                attempts.append(attempt_metadata)
                latency_ms = (time.perf_counter() - start) * 1000.0
                metadata = _aggregate_attempt_metadata(
                    attempts,
                    model=effective_model,
                    latency_ms=latency_ms,
                    token_budget=token_budget,
                )
                metadata.update(provider_config.metadata())
                logger.exception(
                    "bulletpoints_llm_request_failed",
                    extra={
                        "event": "bulletpoints_llm_request_failed",
                        "subsystem": "bulletpoints_generation",
                        "model": effective_model,
                        "attempt": attempt_index,
                        "resolved_llm_max_output_tokens": attempt_max_output_tokens,
                    },
                )
                raise BulletPointLLMClientError(
                    f"Bullet-point LLM request failed: {exc}",
                    metadata=metadata,
                ) from exc

            attempt_metadata = {
                "attempt": attempt_index,
                "max_output_tokens": attempt_max_output_tokens,
                **_usage_metadata(response),
            }
            attempts.append(attempt_metadata)

            output_text = _extract_output_text(response)
            if not output_text:
                retry_reason = "Bullet-point LLM response did not include output_text"
                attempt_metadata["error"] = retry_reason
            else:
                try:
                    raw_response = json.loads(output_text)
                except json.JSONDecodeError as exc:
                    retry_reason = f"Bullet-point LLM response was not valid JSON: {exc}"
                    attempt_metadata["error"] = retry_reason
                else:
                    bullets = _validate_bullet_points(raw_response, count_range)
                    latency_ms = (time.perf_counter() - start) * 1000.0
                    metadata = _aggregate_attempt_metadata(
                        attempts,
                        model=effective_model,
                        latency_ms=latency_ms,
                        token_budget=token_budget,
                    )
                    metadata.update(provider_config.metadata())
                    if retry_reason is not None:
                        metadata["retry_reason"] = retry_reason
                    return LLMBulletPointResult(bullet_points=bullets, metadata=metadata)

            if attempt_index == len(max_output_tokens_by_attempt):
                latency_ms = (time.perf_counter() - start) * 1000.0
                metadata = _aggregate_attempt_metadata(
                    attempts,
                    model=effective_model,
                    latency_ms=latency_ms,
                    token_budget=token_budget,
                )
                metadata.update(provider_config.metadata())
                if retry_reason is not None:
                    metadata["retry_reason"] = retry_reason
                raise BulletPointLLMClientError(
                    retry_reason or "Bullet-point LLM response could not be parsed",
                    metadata=metadata,
                )

            logger.warning(
                "bulletpoints_llm_response_retry",
                extra={
                    "event": "bulletpoints_llm_response_retry",
                    "subsystem": "bulletpoints_generation",
                    "model": effective_model,
                    "attempt": attempt_index,
                    "resolved_llm_max_output_tokens": attempt_max_output_tokens,
                    "retry_reason": retry_reason,
                },
            )
    finally:
        await client.close()

    raise BulletPointLLMClientError("Bullet-point LLM response could not be parsed")


async def generate_resume_section_bulletpoints_with_llm_async(
    *,
    context: BulletJobContext,
    projects: list[ProjectRecord],
    experiences: list[ExperienceRecord],
    project_count_range: BulletCountRange,
    experience_count_range: BulletCountRange,
    model: str | None = None,
    max_output_tokens: int | None = None,
    output_token_budget: BulletOutputTokenBudget | Mapping[str, Any] | None = None,
) -> LLMResumeSectionBulletPointResult:
    project_ids = [project.id for project in projects]
    experience_ids = [experience.id for experience in experiences]
    prompt_payload = build_resume_section_bulletpoint_prompt_payload(
        context=context,
        projects=projects,
        experiences=experiences,
        project_count_range=project_count_range,
        experience_count_range=experience_count_range,
    )
    schema = build_resume_section_bulletpoint_schema(
        project_ids=project_ids,
        experience_ids=experience_ids,
        project_count_range=project_count_range,
        experience_count_range=experience_count_range,
    )
    instructions = build_resume_section_bulletpoint_instructions(
        project_count_range=project_count_range,
        experience_count_range=experience_count_range,
    )

    provider_config = resolve_llm_provider_config(
        stage="bulletpoints_generation",
        requested_model=model,
        default_openai_model=settings.BULLETPOINTS_LLM_MODEL,
    )
    if not provider_config.api_key.strip():
        raise BulletPointLLMClientError(
            f"{provider_config.api_key_setting_name} is required for bullet-point generation"
        )

    effective_model = provider_config.model
    highlight_count = sum(len(project.highlights) for project in projects) + sum(
        len(experience.highlights) for experience in experiences
    )
    requested_max_bullets = (
        len(projects) * project_count_range.max
        + len(experiences) * experience_count_range.max
    )
    token_budget = resolve_resume_section_bulletpoint_max_output_tokens(
        prompt_payload=prompt_payload,
        requested_max_bullets=requested_max_bullets,
        highlight_count=highlight_count,
        max_output_tokens=max_output_tokens,
        output_token_budget=output_token_budget,
    )
    effective_max_output_tokens = token_budget["resolved_llm_max_output_tokens"]

    start = time.perf_counter()
    attempts: list[dict[str, Any]] = []
    retry_reason: str | None = None

    try:
        client = AsyncOpenAI(**provider_config.client_kwargs())
    except Exception as exc:
        logger.exception(
            "resume_section_bulletpoints_llm_request_failed",
            extra={
                "event": "resume_section_bulletpoints_llm_request_failed",
                "subsystem": "bulletpoints_generation",
                "model": effective_model,
                "attempt": 0,
                "resolved_llm_max_output_tokens": effective_max_output_tokens,
            },
        )
        raise BulletPointLLMClientError(
            f"Resume section bullet-point LLM request failed: {exc}"
        ) from exc

    max_output_tokens_by_attempt = [
        effective_max_output_tokens,
        _apply_optional_cap(
            max(effective_max_output_tokens * 2, 3000),
            token_budget["config"].get("max"),
        ),
    ]
    max_output_tokens_by_attempt = list(dict.fromkeys(max_output_tokens_by_attempt))

    try:
        for attempt_index, attempt_max_output_tokens in enumerate(
            max_output_tokens_by_attempt,
            start=1,
        ):
            try:
                create_kwargs = build_bulletpoint_response_create_kwargs(
                    model=effective_model,
                    instructions=instructions,
                    prompt_payload=prompt_payload,
                    schema=schema,
                    max_output_tokens=attempt_max_output_tokens,
                    schema_name="resume_section_bullet_points",
                )
                apply_provider_response_options(create_kwargs, provider_config)
                response = await client.responses.create(**create_kwargs)
            except Exception as exc:
                attempt_metadata = {
                    "attempt": attempt_index,
                    "max_output_tokens": attempt_max_output_tokens,
                    "error": f"Resume section bullet-point LLM request failed: {exc}",
                }
                attempts.append(attempt_metadata)
                latency_ms = (time.perf_counter() - start) * 1000.0
                metadata = _aggregate_attempt_metadata(
                    attempts,
                    model=effective_model,
                    latency_ms=latency_ms,
                    token_budget=token_budget,
                )
                metadata.update(provider_config.metadata())
                logger.exception(
                    "resume_section_bulletpoints_llm_request_failed",
                    extra={
                        "event": "resume_section_bulletpoints_llm_request_failed",
                        "subsystem": "bulletpoints_generation",
                        "model": effective_model,
                        "attempt": attempt_index,
                        "resolved_llm_max_output_tokens": attempt_max_output_tokens,
                    },
                )
                raise BulletPointLLMClientError(
                    f"Resume section bullet-point LLM request failed: {exc}",
                    metadata=metadata,
                ) from exc

            attempt_metadata = {
                "attempt": attempt_index,
                "max_output_tokens": attempt_max_output_tokens,
                **_usage_metadata(response),
            }
            attempts.append(attempt_metadata)

            output_text = _extract_output_text(response)
            if not output_text:
                retry_reason = (
                    "Resume section bullet-point LLM response did not include output_text"
                )
                attempt_metadata["error"] = retry_reason
            else:
                try:
                    raw_response = json.loads(output_text)
                except json.JSONDecodeError as exc:
                    retry_reason = (
                        "Resume section bullet-point LLM response was not valid "
                        f"JSON: {exc}"
                    )
                    attempt_metadata["error"] = retry_reason
                else:
                    project_bullets, experience_bullets = (
                        _validate_resume_section_bullet_points(
                            raw_response,
                            project_ids=project_ids,
                            experience_ids=experience_ids,
                            project_count_range=project_count_range,
                            experience_count_range=experience_count_range,
                        )
                    )
                    latency_ms = (time.perf_counter() - start) * 1000.0
                    metadata = _aggregate_attempt_metadata(
                        attempts,
                        model=effective_model,
                        latency_ms=latency_ms,
                        token_budget=token_budget,
                    )
                    metadata.update(provider_config.metadata())
                    if retry_reason is not None:
                        metadata["retry_reason"] = retry_reason
                    return LLMResumeSectionBulletPointResult(
                        project_bullet_points=project_bullets,
                        experience_bullet_points=experience_bullets,
                        metadata=metadata,
                    )

            if attempt_index == len(max_output_tokens_by_attempt):
                latency_ms = (time.perf_counter() - start) * 1000.0
                metadata = _aggregate_attempt_metadata(
                    attempts,
                    model=effective_model,
                    latency_ms=latency_ms,
                    token_budget=token_budget,
                )
                metadata.update(provider_config.metadata())
                if retry_reason is not None:
                    metadata["retry_reason"] = retry_reason
                raise BulletPointLLMClientError(
                    retry_reason
                    or "Resume section bullet-point LLM response could not be parsed",
                    metadata=metadata,
                )

            logger.warning(
                "resume_section_bulletpoints_llm_response_retry",
                extra={
                    "event": "resume_section_bulletpoints_llm_response_retry",
                    "subsystem": "bulletpoints_generation",
                    "model": effective_model,
                    "attempt": attempt_index,
                    "resolved_llm_max_output_tokens": attempt_max_output_tokens,
                    "retry_reason": retry_reason,
                },
            )
    finally:
        await client.close()

    raise BulletPointLLMClientError(
        "Resume section bullet-point LLM response could not be parsed"
    )
