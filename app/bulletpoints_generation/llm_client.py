from __future__ import annotations

import json
import logging
import math
import time
from dataclasses import dataclass
from typing import Any, Literal, Mapping

from openai import OpenAI

from app.bulletpoints_generation.models import (
    BulletCountRange,
    BulletJobContext,
    BulletOutputTokenBudget,
)
from app.config import get_openai_api_key, settings
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
        f"{count_instruction} Tailor the supplied {evidence_type} evidence to the "
        "target job focus while staying grounded in the supplied "
        f"{evidence_type} summary, highlights, and skills. Treat the evidence "
        "as mostly raw, human-written factual context: it may be simple, poorly "
        "written, or stylistically unsuitable, and the bullets should not copy "
        "its logic, tone, or wording. Maximize the user's "
        "chances of getting an interview by creating strong, ATS-friendly "
        "resume bullets. Use strong action verbs + task + impact, prioritize "
        "measurable results, and follow best practices for resume bullet "
        "writing by extracting and reframing the most recruiting-relevant "
        "information from the live evidence. Do not fabricate any details that "
        "are not supported by the supplied evidence. "
        "Each string must be a polished resume bullet without a leading bullet marker."
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
                "active": project.active,
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
            "active": experience.active,
            "skills": experience.skills.model_dump(),
            "location": experience.location,
            "start": experience.start,
            "end": experience.end,
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
        if not isinstance(bullet, str):
            raise BulletPointLLMClientError(f"Bullet point {index} must be a string")
        normalized = bullet.strip()
        if not normalized:
            raise BulletPointLLMClientError(f"Bullet point {index} must not be empty")
        cleaned = normalized.lstrip("-* ").strip()
        if not cleaned:
            raise BulletPointLLMClientError(f"Bullet point {index} must not be empty")
        bullets.append(cleaned)

    if len(bullets) < count_range.min or len(bullets) > count_range.max:
        raise BulletPointLLMClientError(
            "Bullet-point LLM response count was outside the requested range"
        )

    return bullets


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

    api_key = get_openai_api_key()
    if not api_key.strip():
        raise BulletPointLLMClientError("OPENAI_API_KEY is required for bullet-point generation")

    effective_model = model if model is not None else settings.BULLETPOINTS_LLM_MODEL
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
        client = OpenAI(api_key=api_key)
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
