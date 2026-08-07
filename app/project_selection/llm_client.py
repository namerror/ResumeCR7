from __future__ import annotations

import json
import logging
import math
import time
from dataclasses import dataclass
from typing import Any, Mapping

from openai import OpenAI

from app.config import get_openai_api_key, settings
from app.project_selection.models import (
    ProjectCandidate,
    ProjectJobContext,
    ProjectOutputTokenBudget,
)
from app.skill_selection.llm_client import _extract_output_text, supports_temperature

logger = logging.getLogger("project_llm_client")


class ProjectLLMClientError(RuntimeError):
    """Raised when a project LLM request or response cannot be used."""

    def __init__(self, message: str, metadata: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.metadata = metadata or {}


@dataclass
class LLMProjectScoreResult:
    scores: dict[str, Any]
    metadata: dict[str, Any]


def build_project_score_schema(project_ids: list[str]) -> dict[str, Any]:
    unique_ids = list(dict.fromkeys(project_ids))
    return {
        "type": "object",
        "properties": {
            project_id: {
                "type": "integer",
                "minimum": 0,
                "maximum": 3,
                "description": "0=not relevant, 1=weak, 2=good, 3=strong",
            }
            for project_id in unique_ids
        },
        "required": unique_ids,
        "additionalProperties": False,
    }


def build_project_prompt_payload(
    *,
    context: ProjectJobContext,
    candidates: list[ProjectCandidate],
) -> str:
    payload = {
        "job": {
            "title": context.title,
            "description": context.description or "",
        },
        "projects": [
            {
                "id": candidate.id,
                "name": candidate.name,
                "summary": candidate.summary,
                "skills": candidate.skills.model_dump(),
            }
            for candidate in candidates
        ],
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


def _budget_dict(budget: ProjectOutputTokenBudget | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(budget, ProjectOutputTokenBudget):
        return budget.model_dump()
    return dict(budget)


def _apply_optional_cap(value: int, max_value: int | None) -> int:
    return min(value, max_value) if max_value is not None else value


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


def resolve_project_max_output_tokens(
    *,
    prompt_payload: str,
    candidate_count: int,
    max_output_tokens: int | None = None,
    output_token_budget: ProjectOutputTokenBudget | Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    token_budget_inputs = {
        "candidate_count": candidate_count,
        "prompt_json_chars": len(prompt_payload),
        "prompt_1k_chars": math.ceil(len(prompt_payload) / 1000),
    }
    if max_output_tokens is not None:
        return {
            "mode": "override",
            "requested_llm_max_output_tokens": max_output_tokens,
            "resolved_llm_max_output_tokens": max_output_tokens,
            "config": (
                _budget_dict(output_token_budget)
                if output_token_budget is not None
                else None
            ),
            "inputs": token_budget_inputs,
        }

    if output_token_budget is None:
        return {
            "mode": "uncapped",
            "requested_llm_max_output_tokens": None,
            "resolved_llm_max_output_tokens": None,
            "config": None,
            "inputs": token_budget_inputs,
        }

    budget_config = _budget_dict(output_token_budget)
    prompt_1k_chars = math.ceil(len(prompt_payload) / 1000)
    calculated = (
        int(budget_config["base"])
        + int(budget_config["per_candidate"]) * candidate_count
        + int(budget_config["per_prompt_1k_chars"]) * prompt_1k_chars
    )
    resolved = max(int(budget_config["min"]), calculated)
    resolved = _apply_optional_cap(resolved, budget_config.get("max"))
    return {
        "mode": "dynamic",
        "requested_llm_max_output_tokens": None,
        "resolved_llm_max_output_tokens": resolved,
        "config": budget_config,
        "inputs": {
            "candidate_count": candidate_count,
            "prompt_json_chars": len(prompt_payload),
            "prompt_1k_chars": prompt_1k_chars,
            "calculated_max_output_tokens": calculated,
        },
    }


def build_project_response_create_kwargs(
    *,
    model: str,
    instructions: str,
    prompt_payload: str,
    schema: dict[str, Any],
    max_output_tokens: int | None,
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "model": model,
        "instructions": instructions,
        "input": prompt_payload,
        "tools": [],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "project_scores",
                "schema": schema,
                "strict": True,
            }
        },
    }
    if max_output_tokens is not None:
        kwargs["max_output_tokens"] = max_output_tokens
    if supports_temperature(model):
        kwargs["temperature"] = 0
    return kwargs


def score_projects_with_llm(
    *,
    context: ProjectJobContext,
    candidates: list[ProjectCandidate],
    model: str | None = None,
    max_output_tokens: int | None = None,
    output_token_budget: ProjectOutputTokenBudget | Mapping[str, Any] | None = None,
) -> LLMProjectScoreResult:
    prompt_payload = build_project_prompt_payload(context=context, candidates=candidates)
    schema = build_project_score_schema([candidate.id for candidate in candidates])
    instructions = (
        "You are a deterministic project relevance scorer. Return JSON only. "
        "Score every provided candidate project for the given job context using only "
        "the project summary and categorized skills. Do not add, remove, rename, or "
        "rewrite projects. Scores must be integers from 0 to 3."
    )

    api_key = get_openai_api_key()
    if not api_key.strip():
        raise ProjectLLMClientError("OPENAI_API_KEY is required for project LLM scoring")

    effective_model = model if model is not None else settings.PROJ_LLM_MODEL
    token_budget = resolve_project_max_output_tokens(
        prompt_payload=prompt_payload,
        candidate_count=len(candidates),
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
            "project_llm_request_failed",
            extra={
                "event": "project_llm_request_failed",
                "subsystem": "project_selection",
                "model": effective_model,
                "attempt": 0,
                "resolved_llm_max_output_tokens": effective_max_output_tokens,
            },
        )
        raise ProjectLLMClientError(f"Project LLM request failed: {exc}") from exc

    max_output_tokens_by_attempt: list[int | None]
    if effective_max_output_tokens is None:
        max_output_tokens_by_attempt = [None]
    else:
        retry_max_output_tokens = max(effective_max_output_tokens * 2, 3000)
        budget_config = (
            token_budget["config"]
            if isinstance(token_budget["config"], dict)
            else {}
        )
        retry_max_output_tokens = _apply_optional_cap(
            retry_max_output_tokens,
            budget_config.get("max"),
        )
        max_output_tokens_by_attempt = list(
            dict.fromkeys([effective_max_output_tokens, retry_max_output_tokens])
        )

    for attempt_index, attempt_max_output_tokens in enumerate(
        max_output_tokens_by_attempt,
        start=1,
    ):
        try:
            create_kwargs = build_project_response_create_kwargs(
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
                "error": f"Project LLM request failed: {exc}",
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
                "project_llm_request_failed",
                extra={
                    "event": "project_llm_request_failed",
                    "subsystem": "project_selection",
                    "model": effective_model,
                    "attempt": attempt_index,
                    "resolved_llm_max_output_tokens": attempt_max_output_tokens,
                },
            )
            raise ProjectLLMClientError(f"Project LLM request failed: {exc}", metadata=metadata) from exc

        attempt_metadata = {
            "attempt": attempt_index,
            "max_output_tokens": attempt_max_output_tokens,
            **_usage_metadata(response),
        }
        attempts.append(attempt_metadata)

        output_text = _extract_output_text(response)
        if not output_text:
            retry_reason = "Project LLM response did not include output_text"
            attempt_metadata["error"] = retry_reason
        else:
            try:
                scores = json.loads(output_text)
            except json.JSONDecodeError as exc:
                retry_reason = f"Project LLM response was not valid JSON: {exc}"
                attempt_metadata["error"] = retry_reason
            else:
                latency_ms = (time.perf_counter() - start) * 1000.0
                metadata = _aggregate_attempt_metadata(
                    attempts,
                    model=effective_model,
                    latency_ms=latency_ms,
                    token_budget=token_budget,
                )
                if retry_reason is not None:
                    metadata["retry_reason"] = retry_reason
                return LLMProjectScoreResult(scores=scores, metadata=metadata)

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
            raise ProjectLLMClientError(
                retry_reason or "Project LLM response could not be parsed",
                metadata=metadata,
            )

        logger.warning(
            "project_llm_response_retry",
            extra={
                "event": "project_llm_response_retry",
                "subsystem": "project_selection",
                "model": effective_model,
                "attempt": attempt_index,
                "resolved_llm_max_output_tokens": attempt_max_output_tokens,
                "next_resolved_llm_max_output_tokens": max_output_tokens_by_attempt[attempt_index],
                "retry_reason": retry_reason,
            },
        )

    raise ProjectLLMClientError("Project LLM response could not be parsed")
