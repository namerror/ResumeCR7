from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable


TOKEN_USAGE_FIELDS = (
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "api_calls",
    "latency_ms",
)

_STAGE_DETAIL_KEYS = {
    "skill_selection": ("_llm",),
    "project_selection": ("_project_llm",),
    "job_focus_generation": ("_job_focus_llm",),
    "link_scanning": ("_link_scanning_llm",),
    "project_bullet_points": ("_bulletpoints_llm",),
    "experience_bullet_points": ("_bulletpoints_llm",),
    "resume_section_bullet_points": ("_bulletpoints_llm",),
}


@dataclass
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    api_calls: int = 0
    latency_ms: float = 0.0

    def add(self, other: "TokenUsage") -> None:
        self.prompt_tokens += other.prompt_tokens
        self.completion_tokens += other.completion_tokens
        self.total_tokens += other.total_tokens
        self.api_calls += other.api_calls
        self.latency_ms += other.latency_ms

    def model_dump(self) -> dict[str, int | float]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "api_calls": self.api_calls,
            "latency_ms": round(self.latency_ms, 3),
        }


@dataclass
class ResumeGenerationTokenUsageMonitor:
    _stage_usage: dict[str, TokenUsage] = field(default_factory=dict)

    def observe(self, stage: str, usage: TokenUsage) -> None:
        self._stage_usage.setdefault(stage, TokenUsage()).add(usage)

    def stage_total(self, stage: str) -> TokenUsage:
        return self._stage_usage.get(stage, TokenUsage())

    def combined_total(self, stages: Iterable[str]) -> TokenUsage:
        total = TokenUsage()
        for stage in stages:
            total.add(self.stage_total(stage))
        return total

    def pipeline_total(self) -> TokenUsage:
        total = TokenUsage()
        for usage in self._stage_usage.values():
            total.add(usage)
        return total

    def summary(self) -> dict[str, Any]:
        raw_stage_usage = {
            stage: usage.model_dump()
            for stage, usage in sorted(self._stage_usage.items())
        }
        return {
            "stages": {
                "selection": self.combined_total(
                    ("skill_selection", "project_selection")
                ).model_dump(),
                "skill_selection": self.stage_total("skill_selection").model_dump(),
                "project_selection": self.stage_total("project_selection").model_dump(),
                "job_focus_generation": self.stage_total(
                    "job_focus_generation"
                ).model_dump(),
                "link_scanning": self.stage_total("link_scanning").model_dump(),
                "project_bullet_points": self.stage_total(
                    "project_bullet_points"
                ).model_dump(),
                "experience_bullet_points": self.stage_total(
                    "experience_bullet_points"
                ).model_dump(),
                "resume_section_bullet_points": self.stage_total(
                    "resume_section_bullet_points"
                ).model_dump(),
                "assembly": TokenUsage().model_dump(),
            },
            "raw_stages": raw_stage_usage,
            "total": self.pipeline_total().model_dump(),
        }


def _coerce_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _coerce_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _usage_from_metadata(metadata: dict[str, Any] | None) -> TokenUsage:
    if not isinstance(metadata, dict):
        return TokenUsage()
    return TokenUsage(
        prompt_tokens=_coerce_int(metadata.get("prompt_tokens")),
        completion_tokens=_coerce_int(metadata.get("completion_tokens")),
        total_tokens=_coerce_int(metadata.get("total_tokens")),
        api_calls=_coerce_int(metadata.get("api_calls")),
        latency_ms=_coerce_float(metadata.get("latency_ms")),
    )


def extract_response_token_usage(stage: str, response_data: dict[str, Any]) -> TokenUsage:
    details = response_data.get("details")
    if not isinstance(details, dict):
        return TokenUsage()

    for detail_key in _STAGE_DETAIL_KEYS.get(stage, ()):
        metadata = details.get(detail_key)
        if isinstance(metadata, dict):
            return _usage_from_metadata(metadata)

    return TokenUsage()
