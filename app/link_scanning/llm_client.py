from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from openai import OpenAI

from app.config import get_github_token, settings
from app.llm_provider import (
    apply_provider_response_options,
    qwen_chat_completion_response_format,
    resolve_llm_provider_config,
)
from app.link_scanning.github_client import (
    GitHubRepoContext,
    GitHubRepoScanError,
    fetch_github_repo_context,
)
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
    authorized_github_contexts: list[GitHubRepoContext] | None = None,
    web_search_enabled: bool = True,
) -> str:
    scan_targets = build_link_scan_targets(evidence.links or [])
    context_scope_keys = {
        _github_scope_key(context.repo_scope)
        for context in authorized_github_contexts or []
    }
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
                "instructions": _target_instruction(target, context_scope_keys),
            }
            for target in scan_targets
        ],
        "authorized_github_repositories": [
            _github_context_payload(context)
            for context in authorized_github_contexts or []
        ],
        "grounding_rules": [
            (
                "Read every supplied evidence link using web search unless an authorized GitHub repository context is supplied for that repository."
                if web_search_enabled
                else "Read supplied GitHub repository targets using authorized_github_repositories context."
            ),
            "For single_page targets, use only the single page the URL resolves to after normal redirects.",
            "For github_repo targets, repository-scoped exploration under repo_scope is allowed.",
            "For authorized GitHub repositories, use only the supplied repository context as source material for that repository.",
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


def _target_instruction(
    target: LinkScanTarget,
    authorized_context_scope_keys: set[tuple[str, str] | None],
) -> str:
    if target.mode != "github_repo":
        return "Inspect only the single page this URL resolves to after normal redirects."
    if (
        target.repo_scope is not None
        and _github_scope_key(target.repo_scope) in authorized_context_scope_keys
    ):
        return (
            "Use the supplied authorized_github_repositories context for this "
            "repository. Do not rely on public web search for this repository."
        )
    return (
        "Inspect the GitHub repository under repo_scope. You may move between "
        "repository pages such as README, source tree, docs, manifests, tests, "
        "and CI/config files, but do not leave this repository."
    )


def _github_context_payload(context: GitHubRepoContext) -> dict[str, Any]:
    return {
        "repo_scope": context.repo_scope,
        "owner": context.owner,
        "repo": context.repo,
        "default_branch": context.default_branch,
        "html_url": context.html_url,
        "description": context.description,
        "files": [
            {
                "path": file.path,
                "source_url": file.html_url,
                "text": file.text,
            }
            for file in context.files
        ],
    }


def build_link_scan_instructions(
    *,
    authorized_github_contexts_available: bool = False,
    web_search_enabled: bool = True,
) -> str:
    opening = (
        "Use supplied repository context and web search to inspect every item in scan_targets. "
        if web_search_enabled and authorized_github_contexts_available
        else "Use web search to inspect every item in scan_targets. "
        if web_search_enabled
        else "Use the supplied authorized_github_repositories context to inspect every item in scan_targets. "
    )
    return (
        "You are a deterministic evidence collector for grounded resume generation. "
        f"{opening}For single_page targets, "
        "inspect only the page that URL resolves to after normal redirects and do not crawl "
        "additional pages. For github_repo targets, inspect the GitHub repository under "
        "repo_scope; you may move between pages within that same repository, including README, "
        "source tree, docs, manifests, tests, CI/config, and other repository files when useful. "
        "When authorized_github_repositories contains a repo_scope, use the supplied file "
        "contexts as the source material for that repository. "
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
    use_web_search: bool = True,
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "model": model,
        "instructions": instructions,
        "input": prompt_payload,
        "max_output_tokens": max_output_tokens,
        "text": {
            "format": {
                "type": "json_schema",
                "name": "link_evidence_enrichment",
                "schema": schema,
                "strict": True,
            }
        },
    }
    if use_web_search:
        kwargs["tools"] = [{"type": "web_search"}]
        kwargs["tool_choice"] = "required"
        kwargs["include"] = ["web_search_call.action.sources"]
    if supports_temperature(model):
        kwargs["temperature"] = 0
    return kwargs


def _usage_metadata(response: Any) -> dict[str, int]:
    usage = getattr(response, "usage", None)
    return {
        "prompt_tokens": int(
            (
                getattr(usage, "input_tokens", None)
                if getattr(usage, "input_tokens", None) is not None
                else getattr(usage, "prompt_tokens", 0)
            )
            or 0
        ),
        "completion_tokens": int(
            (
                getattr(usage, "output_tokens", None)
                if getattr(usage, "output_tokens", None) is not None
                else getattr(usage, "completion_tokens", 0)
            )
            or 0
        ),
        "total_tokens": int(getattr(usage, "total_tokens", 0) or 0),
    }


def _combine_usage_metadata(*items: dict[str, int]) -> dict[str, int]:
    return {
        "prompt_tokens": sum(item.get("prompt_tokens", 0) for item in items),
        "completion_tokens": sum(item.get("completion_tokens", 0) for item in items),
        "total_tokens": sum(item.get("total_tokens", 0) for item in items),
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


def _fetch_authorized_github_contexts(
    scan_targets: list[LinkScanTarget],
    *,
    github_token: str,
) -> list[GitHubRepoContext]:
    if not github_token.strip():
        return []

    contexts: list[GitHubRepoContext] = []
    seen_scopes: set[str] = set()
    for target in scan_targets:
        if target.mode != "github_repo" or target.repo_scope is None:
            continue
        scope_key = target.repo_scope.casefold()
        if scope_key in seen_scopes:
            continue
        seen_scopes.add(scope_key)
        try:
            contexts.append(
                fetch_github_repo_context(
                    repo_scope=target.repo_scope,
                    source_url=target.url,
                    token=github_token,
                )
            )
        except GitHubRepoScanError as exc:
            raise LinkScanningLLMClientError(str(exc)) from exc
    return contexts


def _web_search_required(
    scan_targets: list[LinkScanTarget],
    authorized_github_contexts: list[GitHubRepoContext],
) -> bool:
    context_scope_keys = {
        _github_scope_key(context.repo_scope)
        for context in authorized_github_contexts
    }
    for target in scan_targets:
        if target.mode != "github_repo" or target.repo_scope is None:
            return True
        if _github_scope_key(target.repo_scope) not in context_scope_keys:
            return True
    return False


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


def _repair_qwen_link_scan_response(
    *,
    client: OpenAI,
    model: str,
    schema: dict[str, Any],
    invalid_output: str,
    failure_reason: str,
    scanned_links: list[str],
    cited_source_urls: list[str],
    github_repo_scopes: list[str],
) -> tuple[dict[str, Any], dict[str, int]]:
    repair_payload = json.dumps(
        {
            "failure_reason": failure_reason,
            "invalid_output": invalid_output,
            "scanned_links": scanned_links,
            "allowed_cited_source_urls": cited_source_urls,
            "allowed_github_repo_scopes": github_repo_scopes,
            "repair_rules": [
                "Return only JSON conforming to the schema.",
                "Keep only highlights directly supported by the invalid output.",
                "Use only scanned_links, allowed_cited_source_urls, or allowed_github_repo_scopes for source_url.",
                "If a highlight cannot be repaired safely, omit it.",
            ],
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    kwargs = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You repair link-scanning JSON for grounded resume evidence. "
                    "Do not add new facts. Return JSON only."
                ),
            },
            {"role": "user", "content": repair_payload},
        ],
        "response_format": qwen_chat_completion_response_format(
            schema_name="link_evidence_enrichment",
            schema=schema,
        ),
        "temperature": 0,
    }
    response = client.chat.completions.create(**kwargs)
    output_text = _extract_output_text(response)
    if not output_text:
        raise LinkScanningLLMClientError(
            "Link-scanning LLM repair response did not include output text"
        )

    try:
        repaired = json.loads(output_text)
    except json.JSONDecodeError as exc:
        raise LinkScanningLLMClientError(
            f"Link-scanning LLM repair response was not valid JSON: {exc}"
        ) from exc
    if not isinstance(repaired, dict):
        raise LinkScanningLLMClientError(
            "Link-scanning LLM repair response must be a JSON object"
        )
    return repaired, _usage_metadata(response)


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

    provider_config = resolve_llm_provider_config(
        stage="link_scanning",
        requested_model=model,
        default_openai_model=settings.LINK_SCANNING_LLM_MODEL,
    )
    if not provider_config.api_key.strip():
        raise LinkScanningLLMClientError(
            f"{provider_config.api_key_setting_name} is required for link scanning"
        )
    effective_model = provider_config.model

    authorized_github_contexts = _fetch_authorized_github_contexts(
        scan_targets,
        github_token=get_github_token(),
    )
    web_search_enabled = _web_search_required(scan_targets, authorized_github_contexts)
    prompt_payload = build_link_scan_prompt_payload(
        evidence_type=evidence_type,
        evidence=evidence,
        requested_highlight_count=effective_requested_highlight_count,
        authorized_github_contexts=authorized_github_contexts,
        web_search_enabled=web_search_enabled,
    )
    schema = build_link_scan_schema()
    instructions = build_link_scan_instructions(
        authorized_github_contexts_available=bool(authorized_github_contexts),
        web_search_enabled=web_search_enabled,
    )

    start = time.perf_counter()
    try:
        client = OpenAI(**provider_config.client_kwargs())
        create_kwargs = build_link_scan_response_create_kwargs(
            model=effective_model,
            instructions=instructions,
            prompt_payload=prompt_payload,
            schema=schema,
            max_output_tokens=effective_max_output_tokens,
            use_web_search=web_search_enabled,
        )
        apply_provider_response_options(create_kwargs, provider_config)
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

    source_urls = _extract_source_urls(response)
    github_repo_scopes = [
        target.repo_scope
        for target in scan_targets
        if target.mode == "github_repo" and target.repo_scope is not None
    ]
    primary_usage = _usage_metadata(response)
    repair_usage: dict[str, int] | None = None
    repair_reason: str | None = None
    try:
        try:
            raw_response = json.loads(output_text)
        except json.JSONDecodeError as exc:
            raise LinkScanningLLMClientError(
                f"Link-scanning LLM response was not valid JSON: {exc}"
            ) from exc
        highlights = _validate_link_scan_response(
            raw_response,
            scanned_links=links,
            cited_source_urls=source_urls,
            github_repo_scopes=github_repo_scopes,
        )
    except LinkScanningLLMClientError as exc:
        if provider_config.provider != "qwen":
            raise
        repair_reason = str(exc)
        raw_response, repair_usage = _repair_qwen_link_scan_response(
            client=client,
            model=effective_model,
            schema=schema,
            invalid_output=output_text,
            failure_reason=repair_reason,
            scanned_links=links,
            cited_source_urls=source_urls,
            github_repo_scopes=github_repo_scopes,
        )
        highlights = _validate_link_scan_response(
            raw_response,
            scanned_links=links,
            cited_source_urls=source_urls,
            github_repo_scopes=github_repo_scopes,
        )

    combined_usage = (
        _combine_usage_metadata(primary_usage, repair_usage)
        if repair_usage is not None
        else primary_usage
    )
    metadata = {
        **provider_config.metadata(),
        "model": effective_model,
        "api_calls": 2 if repair_usage is not None else 1,
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
        "authorized_github_repositories": [
            {
                "repo_scope": context.repo_scope,
                "default_branch": context.default_branch,
                "file_count": len(context.files),
                "source_urls": [file.html_url for file in context.files],
            }
            for context in authorized_github_contexts
        ],
        "web_search_enabled": web_search_enabled,
        "source_urls": source_urls,
        **combined_usage,
    }
    if repair_reason is not None:
        metadata["repair_reason"] = repair_reason
    return LLMLinkScanResult(highlights=highlights, metadata=metadata)
