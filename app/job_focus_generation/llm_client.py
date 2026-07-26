from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any

from openai import OpenAI

from app.config import get_openai_api_key, settings
from app.job_focus_generation.models import JobFocus
from app.skill_selection.llm_client import _extract_output_text, supports_temperature

logger = logging.getLogger("job_focus_llm_client")


class JobFocusLLMClientError(RuntimeError):
    """Raised when a job-focus LLM request or response cannot be used."""


@dataclass
class LLMJobFocusResult:
    job_focus: JobFocus
    metadata: dict[str, Any]


def build_job_focus_schema() -> dict[str, Any]:
    string_array_schema = {
        "type": "array",
        "items": {"type": "string", "minLength": 1},
        "maxItems": 12,
    }
    return {
        "type": "object",
        "properties": {
            "summary": {"type": "string", "minLength": 1},
            "required_skills": string_array_schema,
            "preferred_skills": string_array_schema,
            "responsibilities": string_array_schema,
            "domain_emphasis": string_array_schema,
            "resume_relevant_constraints": string_array_schema,
            "excluded_context": string_array_schema,
        },
        "required": [
            "summary",
            "required_skills",
            "preferred_skills",
            "responsibilities",
            "domain_emphasis",
            "resume_relevant_constraints",
            "excluded_context",
        ],
        "additionalProperties": False,
    }


def build_job_focus_prompt_payload(*, title: str, description: str | None) -> str:
    payload = {
        "job": {
            "title": title,
            "description": description or "",
        },
        "extraction_goal": (
            "Distill the job posting into compact resume-generation context. "
            "Keep skills, responsibilities, technical/domain emphasis, and constraints "
            "that should influence evidence selection and bullet emphasis."
        ),
        "exclude": [
            "company offerings",
            "company culture",
            "benefits",
            "equal opportunity or legal boilerplate",
            "application logistics",
            "recruiter marketing copy",
            "generic soft-skill filler unless it is central to the work",
        ],
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def build_job_focus_instructions() -> str:
    return (
        "You are a deterministic job-posting distiller for grounded resume generation. "
        "Return JSON only. Extract the qualities in the job posting that should guide "
        "resume content: important skills, responsibilities, domain emphasis, and "
        "resume-relevant constraints. Do not include company culture, benefits, company "
        "offerings, legal boilerplate, application instructions, or unrelated marketing "
        "copy except in excluded_context. Keep every field concise and avoid inventing "
        "requirements not supported by the job posting."
    )


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


def build_job_focus_response_create_kwargs(
    *,
    model: str,
    instructions: str,
    prompt_payload: str,
    schema: dict[str, Any],
    max_output_tokens: int,
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
                "name": "job_focus",
                "schema": schema,
                "strict": True,
            }
        },
    }
    if supports_temperature(model):
        kwargs["temperature"] = 0
    return kwargs


def _validate_job_focus(raw_response: Any) -> JobFocus:
    if not isinstance(raw_response, dict):
        raise JobFocusLLMClientError("Job-focus LLM response must be a JSON object")
    try:
        return JobFocus.model_validate(raw_response)
    except ValueError as exc:
        raise JobFocusLLMClientError(f"Job-focus LLM response was invalid: {exc}") from exc


def derive_job_focus_with_llm(
    *,
    title: str,
    description: str | None,
    model: str | None = None,
    max_output_tokens: int | None = None,
) -> LLMJobFocusResult:
    prompt_payload = build_job_focus_prompt_payload(
        title=title,
        description=description,
    )
    schema = build_job_focus_schema()
    instructions = build_job_focus_instructions()

    api_key = get_openai_api_key()
    if not api_key.strip():
        raise JobFocusLLMClientError("OPENAI_API_KEY is required for job-focus generation")

    effective_model = model if model is not None else settings.JOB_FOCUS_LLM_MODEL
    effective_max_output_tokens = (
        max_output_tokens
        if max_output_tokens is not None
        else settings.JOB_FOCUS_LLM_MAX_OUTPUT_TOKENS
    )

    start = time.perf_counter()
    attempts: list[dict[str, Any]] = []
    retry_reason: str | None = None

    try:
        client = OpenAI(api_key=api_key)
    except Exception as exc:
        logger.exception(
            "job_focus_llm_request_failed",
            extra={
                "event": "job_focus_llm_request_failed",
                "subsystem": "job_focus_generation",
                "model": effective_model,
                "attempt": 0,
            },
        )
        raise JobFocusLLMClientError(f"Job-focus LLM request failed: {exc}") from exc

    max_output_tokens_by_attempt = [
        effective_max_output_tokens,
        max(effective_max_output_tokens * 2, 1200),
    ]

    for attempt_index, attempt_max_output_tokens in enumerate(
        max_output_tokens_by_attempt,
        start=1,
    ):
        try:
            create_kwargs = build_job_focus_response_create_kwargs(
                model=effective_model,
                instructions=instructions,
                prompt_payload=prompt_payload,
                schema=schema,
                max_output_tokens=attempt_max_output_tokens,
            )
            response = client.responses.create(**create_kwargs)
        except Exception as exc:
            logger.exception(
                "job_focus_llm_request_failed",
                extra={
                    "event": "job_focus_llm_request_failed",
                    "subsystem": "job_focus_generation",
                    "model": effective_model,
                    "attempt": attempt_index,
                },
            )
            raise JobFocusLLMClientError(f"Job-focus LLM request failed: {exc}") from exc

        attempt_metadata = {
            "attempt": attempt_index,
            "max_output_tokens": attempt_max_output_tokens,
            **_usage_metadata(response),
        }
        attempts.append(attempt_metadata)

        output_text = _extract_output_text(response)
        if not output_text:
            retry_reason = "Job-focus LLM response did not include output_text"
            attempt_metadata["error"] = retry_reason
        else:
            try:
                raw_response = json.loads(output_text)
            except json.JSONDecodeError as exc:
                retry_reason = f"Job-focus LLM response was not valid JSON: {exc}"
                attempt_metadata["error"] = retry_reason
            else:
                job_focus = _validate_job_focus(raw_response)
                latency_ms = (time.perf_counter() - start) * 1000.0
                metadata = _aggregate_attempt_metadata(
                    attempts,
                    model=effective_model,
                    latency_ms=latency_ms,
                )
                if retry_reason is not None:
                    metadata["retry_reason"] = retry_reason
                return LLMJobFocusResult(job_focus=job_focus, metadata=metadata)

        if attempt_index == len(max_output_tokens_by_attempt):
            raise JobFocusLLMClientError(
                retry_reason or "Job-focus LLM response could not be parsed"
            )

        logger.warning(
            "job_focus_llm_response_retry",
            extra={
                "event": "job_focus_llm_response_retry",
                "subsystem": "job_focus_generation",
                "model": effective_model,
                "attempt": attempt_index,
                "retry_reason": retry_reason,
            },
        )

    raise JobFocusLLMClientError("Job-focus LLM response could not be parsed")
