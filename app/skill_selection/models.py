from pydantic import BaseModel
from typing import Any, List, Dict

from app.job_focus_generation.models import JobFocus


class SkillSelectRequest(BaseModel):
    job_role: str
    technology: List[str]
    programming: List[str]
    concepts: List[str]
    job_text: str | None = None  # Optional full job description text for context
    job_focus: JobFocus | None = None  # Optional distilled job focus for stronger tailoring
    top_n: int | None = None  # Optional override for how many skills to select per category
    method: str | None = None  # Optional override for selection method (e.g., "baseline", "embeddings", "llm")
    baseline_filter: bool | None = None  # Optional override for baseline pre-filtering before model-backed scoring
    dev_mode: bool | None = None  # Optional override for whether to include dev-only
    llm_model: str | None = None  # Optional override for LLM-backed skill selection model
    llm_max_output_tokens: int | None = None  # Optional override for LLM-backed skill selection token budget


class SkillSelectResponse(BaseModel):
    technology: List[str]
    programming: List[str]
    concepts: List[str]
    details: Dict[str, Any] | None = None  # Optional field for dev mode
