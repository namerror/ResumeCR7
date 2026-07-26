from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from openai import OpenAI

from app.config import get_openai_api_key, settings
from app.link_scanning.models import LinkScanHighlight
from app.skill_selection.llm_client import _extract_output_text, supports_temperature
from app.resume_evidence.models import ExperienceRecord, ProjectRecord

logger = logging.getLogger("link_scanning_llm_client")


class LinkScanningLLMClientError(RuntimeError):
    """Raised when a link-scanning request or response cannot be used."""


@dataclass
class LLMLinkScanResult:
    highlights: list[LinkScanHighlight]
    metadata: dict[str, Any]


@dataclass(frozen=True)
class LinkScanTarget:
    url: str
    mode: str
    repo_scope: str | None = None


LinkScannableEvidence = ProjectRecord | ExperienceRecord

_GITHUB_HOSTS = {"github.com", "www.github.com"}
_NON_REPO_GITHUB_PATHS = {
    "about",
    "collections",
    "customer-stories",
    "enterprise",
    "events",
    "explore",
    "features",
    "gist",
    "issues",
    "login",
    "marketplace",
    "new",
    "notifications",
    "organizations",
    "orgs",
    "pricing",
    "pulls",
    "search",
    "settings",
    "signup",
    "sponsors",
    "topics",
    "trending",
}


def classify_link_scan_target(url: str) -> LinkScanTarget:
    normalized_url = url.strip()
    parsed = urlparse(normalized_url)
    hostname = (parsed.hostname or "").lower()
    path_parts = [part for part in parsed.path.split("/") if part]

    if (
        parsed.scheme in {"http", "https"}
        and hostname in _GITHUB_HOSTS
        and len(path_parts) >= 2
        and path_parts[0].lower() not in _NON_REPO_GITHUB_PATHS
    ):
        owner, repo = path_parts[0], path_parts[1]
        repo = repo[:-4] if repo.endswith(".git") else repo
        return LinkScanTarget(
            url=normalized_url,
            mode="github_repo",
            repo_scope=f"https://github.com/{owner}/{repo}",
        )

    return LinkScanTarget(url=normalized_url, mode="single_page")


def build_link_scan_targets(links: list[str]) -> list[LinkScanTarget]:
    return [classify_link_scan_target(link) for link in links]


def build_link_scan_schema() -> dict[str, Any]:
    highlight_schema = {
        "type": "object",
        "properties": {
            "text": {"type": "string", "minLength": 1},
            "source_url": {"type": "string", "minLength": 1},
        },
        "required": ["text", "source_url"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "highlights": {
                "type": "array",
                "items": highlight_schema,
                "maxItems": 12,
            }
        },
        "required": ["highlights"],
        "additionalProperties": False,
    }


def _build_evidence_payload(
    *,
    evidence_type: str,
    evidence: LinkScannableEvidence,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "type": evidence_type,
        "id": evidence.id,
        "name": evidence.name,
        "summary": evidence.summary,
        "highlights": evidence.highlights,
        "active": evidence.active,
        "skills": evidence.skills.model_dump(),
        "links": evidence.links or [],
    }
    if isinstance(evidence, ExperienceRecord):
        payload.update(
            {
                "role": evidence.role,
                "location": evidence.location,
                "start": evidence.start,
                "end": evidence.end,
            }
        )
    return payload


def build_link_scan_prompt_payload(
    *,
    evidence_type: str,
    evidence: LinkScannableEvidence,
    requested_highlight_count: int,
) -> str:
    scan_targets = build_link_scan_targets(evidence.links or [])
    payload = {
        "enrichment_goal": {
            "requested_highlight_count": requested_highlight_count,
            "count_is_guidance_not_a_hard_requirement": True,
            "purpose": (
                "Add durable resume evidence highlights with enough technical detail "
                "to show the skills, engineering judgment, and project or experience "
                "knowledge that recruiters can evaluate later."
            ),
        },
        "evidence": _build_evidence_payload(
            evidence_type=evidence_type,
            evidence=evidence,
        ),
        "scan_targets": [
            {
                "url": target.url,
                "mode": target.mode,
                "repo_scope": target.repo_scope,
                "instructions": (
                    "Inspect the GitHub repository under repo_scope. You may move between "
                    "repository pages such as README, source tree, docs, manifests, tests, "
                    "and CI/config files, but do not leave this repository."
                    if target.mode == "github_repo"
                    else "Inspect only the single page this URL resolves to after normal redirects."
                ),
            }
            for target in scan_targets
        ],
        "grounding_rules": [
            "Read every supplied evidence link using web search.",
            "For single_page targets, use only the single page the URL resolves to after normal redirects.",
            "For github_repo targets, repository-scoped exploration under repo_scope is allowed.",
            "Collect factual evidence supported by the linked page or repository target.",
            "Return concise evidence highlights, not polished resume bullets.",
            "Prefer technical details, implementation facts, architecture, tests, tooling, integrations, scale cues, reliability work, and concrete accomplishments when directly supported.",
            "Make each highlight useful without the original page open by naming the specific technology, system behavior, implementation detail, or engineering result it demonstrates.",
            "Do not add skills or infer technologies beyond what the page directly supports.",
            "Avoid repeating existing highlights unless the scanned source adds a new technical detail.",
            "Omit unsupported claims instead of guessing.",
        ],
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def build_link_scan_instructions() -> str:
    return (
        "You are a deterministic evidence collector for grounded resume generation. "
        "Use web search to inspect every item in scan_targets. For single_page targets, "
        "inspect only the page that URL resolves to after normal redirects and do not crawl "
        "additional pages. For github_repo targets, inspect the GitHub repository under "
        "repo_scope; you may move between pages within that same repository, including README, "
        "source tree, docs, manifests, tests, CI/config, and other repository files when useful. "
        "Extract concise factual highlights about the evidence record that are directly "
        "supported by the scanned pages and useful for later resume refinement. "
        "Aim for the requested highlight count when enough grounded facts exist, but return "
        "fewer highlights or an empty array when the sources do not support more. "
        "Return JSON only. Do not include skills, technologies, metrics, dates, ownership, "
        "affiliations, or outcomes unless the scanned page directly supports them. "
        "Prefer recruiter-useful technical details: implementation facts, architecture, tests, "
        "tooling, integrations, reliability work, and concrete achievements when directly "
        "supported by source content. Set source_url to the linked, final resolved, or repository "
        "page URL supporting the highlight. "
        "If the pages do not provide new grounded facts, return an empty highlights array."
    )


def build_link_scan_response_create_kwargs(
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
        "tools": [{"type": "web_search"}],
        "tool_choice": "required",
        "include": ["web_search_call.action.sources"],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "link_evidence_enrichment",
                "schema": schema,
                "strict": True,
            }
        },
    }
    if supports_temperature(model):
        kwargs["temperature"] = 0
    return kwargs


def _usage_metadata(response: Any) -> dict[str, int]:
    usage = getattr(response, "usage", None)
    return {
        "prompt_tokens": int(getattr(usage, "input_tokens", 0) or 0),
        "completion_tokens": int(getattr(usage, "output_tokens", 0) or 0),
        "total_tokens": int(getattr(usage, "total_tokens", 0) or 0),
    }


def _extract_source_urls(value: Any) -> list[str]:
    urls: list[str] = []

    def visit(item: Any) -> None:
        if isinstance(item, dict):
            raw_url = item.get("url")
            if isinstance(raw_url, str) and raw_url.strip():
                urls.append(raw_url.strip())
            for child in item.values():
                visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)
        else:
            for attr in ("url",):
                raw_url = getattr(item, attr, None)
                if isinstance(raw_url, str) and raw_url.strip():
                    urls.append(raw_url.strip())
            output = getattr(item, "output", None)
            if output is not None:
                visit(output)
            action = getattr(item, "action", None)
            if action is not None:
                visit(action)
            sources = getattr(item, "sources", None)
            if sources is not None:
                visit(sources)

    visit(getattr(value, "output", None))
    return list(dict.fromkeys(urls))


def _canonical_exact_url(url: str) -> str:
    return url.strip().rstrip("/")


def _github_scope_key(repo_scope: str) -> tuple[str, str] | None:
    parsed = urlparse(repo_scope)
    path_parts = [part for part in parsed.path.split("/") if part]
    if len(path_parts) < 2:
        return None
    return (path_parts[0].casefold(), path_parts[1].removesuffix(".git").casefold())


def _source_matches_github_scope(source_url: str, repo_scope: str) -> bool:
    scope_key = _github_scope_key(repo_scope)
    if scope_key is None:
        return False

    parsed = urlparse(source_url.strip())
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or hostname not in _GITHUB_HOSTS:
        return False

    path_parts = [part for part in parsed.path.split("/") if part]
    if len(path_parts) < 2:
        return False

    source_key = (path_parts[0].casefold(), path_parts[1].removesuffix(".git").casefold())
    return source_key == scope_key


def _source_url_is_allowed(
    source_url: str,
    *,
    scanned_links: list[str],
    cited_source_urls: list[str],
    github_repo_scopes: list[str],
) -> bool:
    canonical_source = _canonical_exact_url(source_url)
    scanned_exact = {_canonical_exact_url(url) for url in scanned_links}
    if canonical_source in scanned_exact:
        return True

    if any(
        _source_matches_github_scope(source_url, repo_scope)
        for repo_scope in github_repo_scopes
    ):
        return True

    if github_repo_scopes and classify_link_scan_target(source_url).mode == "github_repo":
        return False

    cited_exact = {_canonical_exact_url(url) for url in cited_source_urls}
    return canonical_source in cited_exact


def _validate_link_scan_response(
    raw_response: Any,
    *,
    scanned_links: list[str],
    cited_source_urls: list[str],
    github_repo_scopes: list[str],
) -> list[LinkScanHighlight]:
    if not isinstance(raw_response, dict):
        raise LinkScanningLLMClientError("Link-scanning LLM response must be a JSON object")

    raw_highlights = raw_response.get("highlights")
    if not isinstance(raw_highlights, list):
        raise LinkScanningLLMClientError("Link-scanning LLM response must include highlights")

    highlights: list[LinkScanHighlight] = []
    seen: set[tuple[str, str]] = set()
    for index, raw_highlight in enumerate(raw_highlights, start=1):
        if not isinstance(raw_highlight, dict):
            raise LinkScanningLLMClientError(f"Highlight {index} must be an object")

        try:
            highlight = LinkScanHighlight.model_validate(raw_highlight)
        except Exception as exc:
            raise LinkScanningLLMClientError(f"Highlight {index} was invalid: {exc}") from exc

        if not _source_url_is_allowed(
            highlight.source_url,
            scanned_links=scanned_links,
            cited_source_urls=cited_source_urls,
            github_repo_scopes=github_repo_scopes,
        ):
            raise LinkScanningLLMClientError(
                f"Highlight {index} source_url was not one of the scanned or cited URLs"
            )

        key = (highlight.text.casefold(), highlight.source_url)
        if key in seen:
            continue
        seen.add(key)
        highlights.append(highlight)

    return highlights


def resolve_link_scan_max_output_tokens(
    *,
    max_output_tokens: int | None = None,
    requested_highlight_count: int | None = None,
    max_tokens_per_highlight: int | None = None,
) -> int:
    if max_output_tokens is not None:
        return max_output_tokens

    effective_highlight_count = (
        requested_highlight_count
        if requested_highlight_count is not None
        else settings.LINK_SCANNING_DEFAULT_HIGHLIGHT_COUNT
    )
    effective_max_tokens_per_highlight = (
        max_tokens_per_highlight
        if max_tokens_per_highlight is not None
        else settings.LINK_SCANNING_MAX_TOKENS_PER_HIGHLIGHT
    )
    return effective_highlight_count * effective_max_tokens_per_highlight


def scan_evidence_links_with_llm(
    *,
    evidence_type: str,
    evidence: LinkScannableEvidence,
    model: str | None = None,
    max_output_tokens: int | None = None,
    requested_highlight_count: int | None = None,
    max_tokens_per_highlight: int | None = None,
) -> LLMLinkScanResult:
    links = evidence.links or []
    scan_targets = build_link_scan_targets(links)
    effective_model = model if model is not None else settings.LINK_SCANNING_LLM_MODEL
    effective_requested_highlight_count = (
        requested_highlight_count
        if requested_highlight_count is not None
        else settings.LINK_SCANNING_DEFAULT_HIGHLIGHT_COUNT
    )
    effective_max_tokens_per_highlight = (
        max_tokens_per_highlight
        if max_tokens_per_highlight is not None
        else settings.LINK_SCANNING_MAX_TOKENS_PER_HIGHLIGHT
    )
    effective_max_output_tokens = resolve_link_scan_max_output_tokens(
        max_output_tokens=max_output_tokens,
        requested_highlight_count=effective_requested_highlight_count,
        max_tokens_per_highlight=effective_max_tokens_per_highlight,
    )
    if not links:
        return LLMLinkScanResult(
            highlights=[],
            metadata={
                "model": effective_model,
                "api_calls": 0,
                "scanned_links": [],
                "scan_targets": [],
                "source_urls": [],
                "requested_highlight_count": effective_requested_highlight_count,
                "max_tokens_per_highlight": effective_max_tokens_per_highlight,
                "max_output_tokens": effective_max_output_tokens,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "latency_ms": 0.0,
            },
        )

    api_key = get_openai_api_key()
    if not api_key.strip():
        raise LinkScanningLLMClientError("OPENAI_API_KEY is required for link scanning")

    prompt_payload = build_link_scan_prompt_payload(
        evidence_type=evidence_type,
        evidence=evidence,
        requested_highlight_count=effective_requested_highlight_count,
    )
    schema = build_link_scan_schema()
    instructions = build_link_scan_instructions()

    start = time.perf_counter()
    try:
        client = OpenAI(api_key=api_key)
        create_kwargs = build_link_scan_response_create_kwargs(
            model=effective_model,
            instructions=instructions,
            prompt_payload=prompt_payload,
            schema=schema,
            max_output_tokens=effective_max_output_tokens,
        )
        response = client.responses.create(**create_kwargs)
    except Exception as exc:
        logger.exception(
            "link_scanning_llm_request_failed",
            extra={
                "event": "link_scanning_llm_request_failed",
                "subsystem": "link_scanning",
                "model": effective_model,
                "evidence_type": evidence_type,
                "evidence_id": evidence.id,
            },
        )
        raise LinkScanningLLMClientError(f"Link-scanning LLM request failed: {exc}") from exc

    latency_ms = (time.perf_counter() - start) * 1000.0
    output_text = _extract_output_text(response)
    if not output_text:
        raise LinkScanningLLMClientError("Link-scanning LLM response did not include output_text")

    try:
        raw_response = json.loads(output_text)
    except json.JSONDecodeError as exc:
        raise LinkScanningLLMClientError(
            f"Link-scanning LLM response was not valid JSON: {exc}"
        ) from exc

    source_urls = _extract_source_urls(response)
    github_repo_scopes = [
        target.repo_scope
        for target in scan_targets
        if target.mode == "github_repo" and target.repo_scope is not None
    ]
    highlights = _validate_link_scan_response(
        raw_response,
        scanned_links=links,
        cited_source_urls=source_urls,
        github_repo_scopes=github_repo_scopes,
    )
    metadata = {
        "model": effective_model,
        "api_calls": 1,
        "latency_ms": round(latency_ms, 3),
        "scanned_links": links,
        "requested_highlight_count": effective_requested_highlight_count,
        "max_tokens_per_highlight": effective_max_tokens_per_highlight,
        "max_output_tokens": effective_max_output_tokens,
        "scan_targets": [
            {
                "url": target.url,
                "mode": target.mode,
                "repo_scope": target.repo_scope,
            }
            for target in scan_targets
        ],
        "source_urls": source_urls,
        **_usage_metadata(response),
    }
    return LLMLinkScanResult(highlights=highlights, metadata=metadata)
