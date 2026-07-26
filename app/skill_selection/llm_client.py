from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any

from openai import OpenAI

from app.config import get_openai_api_key, settings

logger = logging.getLogger("llm_client")

CATEGORIES = ("technology", "programming", "concepts")
TEMPERATURE_UNSUPPORTED_MODELS = {
    "gpt-5",
    "gpt-5-mini",
    "gpt-5-nano",
    "gpt-5.6-terra",
}


class LLMClientError(RuntimeError):
    """Raised when the LLM request or response cannot be used."""

    def __init__(self, message: str, metadata: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.metadata = metadata or {}


@dataclass
class LLMScoreResult:
    scores: dict[str, dict[str, Any]]
    metadata: dict[str, Any]


def build_score_schema(category_inputs: dict[str, list[str]]) -> dict[str, Any]:
    """Build a strict JSON schema for the exact candidate skill names."""
    properties: dict[str, Any] = {}
    for category in CATEGORIES:
        unique_skills = list(dict.fromkeys(category_inputs.get(category, [])))
        properties[category] = {
            "type": "object",
            "properties": {
                skill: {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 3,
                    "description": "0=not relevant, 1=weak, 2=good, 3=strong",
                }
                for skill in unique_skills
            },
            "required": unique_skills,
            "additionalProperties": False,
        }

    return {
        "type": "object",
        "properties": properties,
        "required": list(CATEGORIES),
        "additionalProperties": False,
    }


def build_prompt_payload(
    *,
    job_role: str,
    job_text: str | None,
    technology: list[str],
    programming: list[str],
    concepts: list[str],
) -> str:
    """Serialize the scorer input as compact JSON for the fixed prompt."""
    payload = {
        "job_role": job_role,
        "job_text": job_text or "",
        "skills": {
            "technology": technology,
            "programming": programming,
            "concepts": concepts,
        },
        "score_scale": {
            "0": "not relevant",
            "1": "weak relevance",
            "2": "good relevance",
            "3": "strong relevance",
        },
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _usage_metadata(response: Any) -> dict[str, int]:
    usage = getattr(response, "usage", None)
    return {
        "prompt_tokens": int(getattr(usage, "input_tokens", 0) or 0),
        "completion_tokens": int(getattr(usage, "output_tokens", 0) or 0),
        "total_tokens": int(getattr(usage, "total_tokens", 0) or 0),
    }


def _aggregate_attempt_metadata(
    attempts: list[dict[str, Any]],
    *,
    model: str,
    latency_ms: float,
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
    }


def _extract_output_text(response: Any) -> str | None:
    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str) and output_text.strip():
        return output_text

    return _extract_text_from_part(getattr(response, "output", None))


def _extract_text_from_part(part: Any, seen: set[int] | None = None) -> str | None:
    if part is None:
        return None

    if isinstance(part, str):
        stripped = part.strip()
        return stripped or None

    if seen is None:
        seen = set()
    part_id = id(part)
    if part_id in seen:
        return None
    seen.add(part_id)

    if isinstance(part, list):
        for item in part:
            extracted = _extract_text_from_part(item, seen)
            if extracted is not None:
                return extracted
        return None

    if isinstance(part, dict):
        for key in ("output_text", "text"):
            value = part.get(key)
            if isinstance(value, str) and value.strip():
                return value
        for key in ("content", "output"):
            extracted = _extract_text_from_part(part.get(key), seen)
            if extracted is not None:
                return extracted
        return None

    for key in ("output_text", "text"):
        value = getattr(part, key, None)
        if isinstance(value, str) and value.strip():
            return value
    for key in ("content", "output"):
        extracted = _extract_text_from_part(getattr(part, key, None), seen)
        if extracted is not None:
            return extracted
    return None


def supports_temperature(model: str) -> bool:
    """Return whether this model accepts the Responses API temperature parameter."""
    return model not in TEMPERATURE_UNSUPPORTED_MODELS


def _estimated_default_max_output_tokens(
    *,
    category_inputs: dict[str, list[str]],
    schema: dict[str, Any],
    configured_default: int,
) -> int:
    unique_inputs = {
        category: list(dict.fromkeys(category_inputs.get(category, [])))
        for category in CATEGORIES
    }
    candidate_count = sum(len(skills) for skills in unique_inputs.values())
    minimal_output = {
        category: {skill: 0 for skill in skills}
        for category, skills in unique_inputs.items()
    }
    output_size = len(json.dumps(minimal_output, ensure_ascii=False, separators=(",", ":")))
    schema_size = len(json.dumps(schema, ensure_ascii=False, separators=(",", ":")))
    estimated = 128 + (candidate_count * 24) + (output_size // 2) + (schema_size // 20)
    return max(configured_default, estimated)


def build_response_create_kwargs(
    *,
    model: str,
    instructions: str,
    prompt_payload: str,
    schema: dict[str, Any],
    max_output_tokens: int,
) -> dict[str, Any]:
    """Build Responses API kwargs with model-specific parameter compatibility."""
    kwargs: dict[str, Any] = {
        "model": model,
        "instructions": instructions,
        "input": prompt_payload,
        "max_output_tokens": max_output_tokens,
        "tools": [],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "skill_scores",
                "schema": schema,
                "strict": True,
            }
        },
    }
    if supports_temperature(model):
        kwargs["temperature"] = 0
    return kwargs


def score_skills_with_llm(
    *,
    job_role: str,
    job_text: str | None,
    technology: list[str],
    programming: list[str],
    concepts: list[str],
    model: str | None = None,
    max_output_tokens: int | None = None,
) -> LLMScoreResult:
    """Score every candidate skill through the OpenAI Responses API."""
    category_inputs = {
        "technology": technology,
        "programming": programming,
        "concepts": concepts,
    }
    prompt_payload = build_prompt_payload(
        job_role=job_role,
        job_text=job_text,
        technology=technology,
        programming=programming,
        concepts=concepts,
    )
    schema = build_score_schema(category_inputs)

    instructions = (
        "You are a deterministic skill relevance scorer. "
        "Return JSON only. Score every provided candidate skill for the given job role "
        "and optional job text. Do not add, remove, rename, or move skills between "
        "categories. Scores must be integers from 0 to 3."
    )

    api_key = get_openai_api_key()
    if not api_key.strip():
        raise LLMClientError("OPENAI_API_KEY is required for LLM scoring")

    effective_model = model if model is not None else settings.SKILL_LLM_MODEL
    effective_max_output_tokens = (
        max_output_tokens
        if max_output_tokens is not None
        else _estimated_default_max_output_tokens(
            category_inputs=category_inputs,
            schema=schema,
            configured_default=settings.SKILL_LLM_MAX_OUTPUT_TOKENS,
        )
    )

    start = time.perf_counter()
    attempts: list[dict[str, Any]] = []
    retry_reason: str | None = None
    try:
        client = OpenAI(api_key=api_key)
    except Exception as exc:
        logger.exception(
            "llm_request_failed",
            extra={
                "event": "llm_request_failed",
                "subsystem": "skill_selection",
                "model": effective_model,
                "attempt": 0,
                "llm_max_output_tokens": effective_max_output_tokens,
            },
        )
        raise LLMClientError(f"LLM request failed: {exc}") from exc

    retry_max_output_tokens = max(effective_max_output_tokens * 2, 3000)
    max_output_tokens_by_attempt = [
        effective_max_output_tokens,
        retry_max_output_tokens,
    ]

    for attempt_index, attempt_max_output_tokens in enumerate(
        max_output_tokens_by_attempt,
        start=1,
    ):
        try:
            create_kwargs = build_response_create_kwargs(
                model=effective_model,
                instructions=instructions,
                prompt_payload=prompt_payload,
                schema=schema,
                max_output_tokens=attempt_max_output_tokens,
            )
            response = client.responses.create(**create_kwargs)
        except Exception as exc:
            attempt_metadata = {
                "attempt": attempt_index,
                "max_output_tokens": attempt_max_output_tokens,
                "error": f"LLM request failed: {exc}",
            }
            attempts.append(attempt_metadata)
            latency_ms = (time.perf_counter() - start) * 1000.0
            metadata = _aggregate_attempt_metadata(
                attempts,
                model=effective_model,
                latency_ms=latency_ms,
            )
            logger.exception(
                "llm_request_failed",
                extra={
                    "event": "llm_request_failed",
                    "subsystem": "skill_selection",
                    "model": effective_model,
                    "attempt": attempt_index,
                    "llm_max_output_tokens": attempt_max_output_tokens,
                },
            )
            raise LLMClientError(f"LLM request failed: {exc}", metadata=metadata) from exc

        attempt_metadata = {
            "attempt": attempt_index,
            "max_output_tokens": attempt_max_output_tokens,
            **_usage_metadata(response),
        }
        attempts.append(attempt_metadata)

        output_text = _extract_output_text(response)
        if not output_text:
            retry_reason = "LLM response did not include output_text"
            attempt_metadata["error"] = retry_reason
        else:
            try:
                scores = json.loads(output_text)
            except json.JSONDecodeError as exc:
                retry_reason = f"LLM response was not valid JSON: {exc}"
                attempt_metadata["error"] = retry_reason
            else:
                latency_ms = (time.perf_counter() - start) * 1000.0
                metadata = _aggregate_attempt_metadata(
                    attempts,
                    model=effective_model,
                    latency_ms=latency_ms,
                )
                if retry_reason is not None:
                    metadata["retry_reason"] = retry_reason
                return LLMScoreResult(scores=scores, metadata=metadata)

        if attempt_index == len(max_output_tokens_by_attempt):
            latency_ms = (time.perf_counter() - start) * 1000.0
            metadata = _aggregate_attempt_metadata(
                attempts,
                model=effective_model,
                latency_ms=latency_ms,
            )
            if retry_reason is not None:
                metadata["retry_reason"] = retry_reason
            raise LLMClientError(
                retry_reason or "LLM response could not be parsed",
                metadata=metadata,
            )

        logger.warning(
            "llm_response_retry",
            extra={
                "event": "llm_response_retry",
                "subsystem": "skill_selection",
                "model": effective_model,
                "attempt": attempt_index,
                "llm_max_output_tokens": attempt_max_output_tokens,
                "next_llm_max_output_tokens": max_output_tokens_by_attempt[attempt_index],
                "retry_reason": retry_reason,
            },
        )

    raise LLMClientError("LLM response could not be parsed")
