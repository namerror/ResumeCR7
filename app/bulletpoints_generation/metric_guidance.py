from __future__ import annotations

import re
from typing import Literal

from app.resume_evidence.models import ExperienceRecord, ProjectRecord

EvidenceType = Literal["project", "experience"]

_NUMBER_PATTERN = re.compile(r"(?<![A-Za-z0-9])\d+(?:\.\d+)?(?:%|\+|x)?")
_METRIC_CUE_PATTERN = re.compile(
    r"\b("
    r"automation|capacity|complexity|concurrent|distributed|engagement|faster|"
    r"latency|load|optimized|parallel|performance|reduced|reliability|scale|"
    r"speed|throughput|uptime|users"
    r")\b",
    re.IGNORECASE,
)


def extract_numeric_evidence(texts: list[str], *, limit: int = 6) -> list[str]:
    snippets: list[str] = []
    seen: set[str] = set()
    for text in texts:
        normalized = " ".join(text.split())
        if not normalized or not _NUMBER_PATTERN.search(normalized):
            continue
        snippet = _trim_snippet(normalized)
        key = snippet.lower()
        if key in seen:
            continue
        seen.add(key)
        snippets.append(snippet)
        if len(snippets) >= limit:
            break
    return snippets


def build_record_numeric_evidence(
    record: ProjectRecord | ExperienceRecord,
    *,
    limit: int = 6,
) -> list[str]:
    return extract_numeric_evidence([record.summary, *record.highlights], limit=limit)


def build_metric_opportunity_notes(
    *,
    projects: list[ProjectRecord],
    experiences: list[ExperienceRecord],
) -> list[dict[str, object]]:
    notes: list[dict[str, object]] = []
    for project in projects:
        note = _metric_opportunity_note(
            evidence_type="project",
            evidence_id=project.id,
            name=project.name,
            texts=[
                project.summary,
                *project.highlights,
                *_flatten_skills(project.skills.model_dump()),
            ],
        )
        if note is not None:
            notes.append(note)
    for experience in experiences:
        note = _metric_opportunity_note(
            evidence_type="experience",
            evidence_id=experience.id,
            name=f"{experience.role} at {experience.name}",
            texts=[
                experience.summary,
                *experience.highlights,
                *_flatten_skills(experience.skills.model_dump()),
            ],
        )
        if note is not None:
            notes.append(note)
    return notes


def _metric_opportunity_note(
    *,
    evidence_type: EvidenceType,
    evidence_id: str,
    name: str,
    texts: list[str],
) -> dict[str, object] | None:
    combined = " ".join(texts)
    if _NUMBER_PATTERN.search(combined) or not _METRIC_CUE_PATTERN.search(combined):
        return None
    return {
        "evidence_type": evidence_type,
        "evidence_id": evidence_id,
        "name": name,
        "suggestions": _suggestions_for_text(combined),
    }


def _suggestions_for_text(text: str) -> list[str]:
    lower = text.lower()
    suggestions: list[str] = []
    if any(
        term in lower
        for term in ("performance", "latency", "speed", "faster", "optimized")
    ):
        suggestions.append(
            "Add a real runtime, latency, throughput, or speedup metric if known."
        )
    if any(
        term in lower
        for term in ("uptime", "reliability", "load", "scale", "capacity", "users")
    ):
        suggestions.append(
            "Add a real uptime, scale, user, request volume, or reliability metric if known."
        )
    if any(term in lower for term in ("automation", "reduced", "complexity")):
        suggestions.append(
            "Add a real time saved, manual work reduced, defect reduction, "
            "or complexity metric if known."
        )
    if any(
        term in lower
        for term in ("parallel", "distributed", "concurrent", "throughput")
    ):
        suggestions.append(
            "Add a real throughput, parallelism, worker count, or processing-time metric if known."
        )
    if any(term in lower for term in ("engagement", "conversion", "marketing")):
        suggestions.append(
            "Add a real engagement, conversion, reach, or adoption metric if known."
        )
    if suggestions:
        return suggestions[:3]
    return ["Add a real outcome metric for this record if known."]


def _trim_snippet(text: str, *, max_chars: int = 180) -> str:
    if len(text) <= max_chars:
        return text
    match = _NUMBER_PATTERN.search(text)
    if match is None:
        return text[:max_chars].rstrip()
    start = max(0, match.start() - max_chars // 2)
    end = min(len(text), start + max_chars)
    start = max(0, end - max_chars)
    snippet = text[start:end].strip()
    if start > 0:
        snippet = snippet.lstrip(" ,.;:")
    if end < len(text):
        snippet = snippet.rstrip(" ,.;:")
    return snippet


def _flatten_skills(skills: dict[str, list[str]]) -> list[str]:
    return [
        skill
        for category in ("technology", "programming", "concepts")
        for skill in skills.get(category, [])
    ]
