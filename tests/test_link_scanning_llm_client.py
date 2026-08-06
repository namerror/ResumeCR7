from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import app.link_scanning.llm_client as link_llm_client
from app.link_scanning.github_client import GitHubRepoContext, GitHubRepoFileContext
from app.link_scanning.llm_client import (
    LinkScanningLLMClientError,
    build_link_scan_instructions,
    build_link_scan_prompt_payload,
    build_link_scan_response_create_kwargs,
    build_link_scan_schema,
    classify_link_scan_target,
    resolve_link_scan_max_output_tokens,
    scan_evidence_links_with_llm,
)
from resume_evidence.models import ExperienceRecord, ProjectRecord, ProjectSkills


@pytest.fixture(autouse=True)
def _disable_github_token(monkeypatch):
    monkeypatch.setattr(link_llm_client, "get_github_token", lambda: "")


def _project() -> ProjectRecord:
    return ProjectRecord(
        id="resumecr7",
        name="ResumeCR7",
        summary="FastAPI resume engine for grounded resume generation.",
        highlights=["Built project and skill selection APIs."],
        active=True,
        skills=ProjectSkills(
            technology=["FastAPI"],
            programming=["Python"],
            concepts=["API"],
        ),
        links=["https://example.com/resumecr7", "https://docs.example.com/resumecr7"],
    )


def _github_project() -> ProjectRecord:
    return ProjectRecord(
        id="resumecr7",
        name="ResumeCR7",
        summary="FastAPI resume engine for grounded resume generation.",
        highlights=["Built project and skill selection APIs."],
        active=True,
        skills=ProjectSkills(
            technology=["FastAPI"],
            programming=["Python"],
            concepts=["API"],
        ),
        links=[
            "https://github.com/openai/resumecr7",
            "https://example.com/resumecr7",
        ],
    )


def _github_context() -> GitHubRepoContext:
    return GitHubRepoContext(
        repo_scope="https://github.com/openai/resumecr7",
        owner="openai",
        repo="resumecr7",
        default_branch="main",
        html_url="https://github.com/openai/resumecr7",
        description="Resume evidence workbench.",
        files=(
            GitHubRepoFileContext(
                path="README.md",
                html_url="https://github.com/openai/resumecr7/blob/main/README.md",
                text="ResumeCR7 is a FastAPI and React workbench for grounded resume evidence.",
            ),
        ),
    )


def _experience() -> ExperienceRecord:
    return ExperienceRecord(
        id="backend-engineer",
        name="Example Company",
        role="Backend Engineer",
        summary="Built backend services for internal platforms.",
        highlights=["Designed schema-validated APIs."],
        active=True,
        skills=ProjectSkills(
            technology=["FastAPI"],
            programming=["Python"],
            concepts=["API"],
        ),
        location="Example City, ST",
        start="2024",
        end=None,
        links=["https://example.com/company"],
    )


def test_classify_link_scan_target_detects_github_repo_roots_and_subpaths():
    root = classify_link_scan_target("https://github.com/openai/resumecr7")
    blob = classify_link_scan_target(
        "https://github.com/openai/resumecr7/blob/main/README.md"
    )
    tree = classify_link_scan_target("https://www.github.com/openai/resumecr7/tree/main/app")

    assert root.mode == "github_repo"
    assert root.repo_scope == "https://github.com/openai/resumecr7"
    assert blob.mode == "github_repo"
    assert blob.repo_scope == "https://github.com/openai/resumecr7"
    assert tree.mode == "github_repo"
    assert tree.repo_scope == "https://github.com/openai/resumecr7"


def test_classify_link_scan_target_keeps_non_repo_github_urls_single_page():
    owner_only = classify_link_scan_target("https://github.com/openai")
    topics = classify_link_scan_target("https://github.com/topics/python")
    gist = classify_link_scan_target("https://gist.github.com/openai/abc123")
    raw = classify_link_scan_target(
        "https://raw.githubusercontent.com/openai/resumecr7/main/README.md"
    )

    assert owner_only.mode == "single_page"
    assert topics.mode == "single_page"
    assert gist.mode == "single_page"
    assert raw.mode == "single_page"


def test_build_link_scan_schema_returns_highlight_only_contract():
    schema = build_link_scan_schema()

    assert schema["required"] == ["highlights"]
    assert schema["additionalProperties"] is False
    highlight_schema = schema["properties"]["highlights"]["items"]
    assert highlight_schema["required"] == ["text", "source_url"]
    assert "skills" not in json.dumps(schema)


def test_build_link_scan_prompt_payload_includes_links_and_grounding_rules():
    payload = json.loads(
        build_link_scan_prompt_payload(
            evidence_type="project",
            evidence=_project(),
            requested_highlight_count=5,
        )
    )

    assert "job" not in payload
    assert payload["enrichment_goal"]["requested_highlight_count"] == 5
    assert payload["evidence"]["type"] == "project"
    assert payload["evidence"]["links"] == [
        "https://example.com/resumecr7",
        "https://docs.example.com/resumecr7",
    ]
    assert [target["mode"] for target in payload["scan_targets"]] == [
        "single_page",
        "single_page",
    ]
    assert any("single page" in rule for rule in payload["grounding_rules"])
    assert any("Do not add skills" in rule for rule in payload["grounding_rules"])


def test_build_link_scan_prompt_payload_supports_experience_records():
    payload = json.loads(
        build_link_scan_prompt_payload(
            evidence_type="experience",
            evidence=_experience(),
            requested_highlight_count=4,
        )
    )

    assert payload["evidence"]["type"] == "experience"
    assert payload["evidence"]["role"] == "Backend Engineer"
    assert payload["evidence"]["location"] == "Example City, ST"
    assert payload["scan_targets"][0]["url"] == "https://example.com/company"


def test_build_link_scan_prompt_payload_marks_github_repo_targets():
    payload = json.loads(
        build_link_scan_prompt_payload(
            evidence_type="project",
            evidence=_github_project(),
            requested_highlight_count=6,
        )
    )

    assert payload["scan_targets"][0] == {
        "url": "https://github.com/openai/resumecr7",
        "mode": "github_repo",
        "repo_scope": "https://github.com/openai/resumecr7",
        "instructions": (
            "Inspect the GitHub repository under repo_scope. You may move between "
            "repository pages such as README, source tree, docs, manifests, tests, "
            "and CI/config files, but do not leave this repository."
        ),
    }
    assert payload["scan_targets"][1]["mode"] == "single_page"
    assert any("github_repo targets" in rule for rule in payload["grounding_rules"])
    assert any("architecture" in rule for rule in payload["grounding_rules"])


def test_build_link_scan_prompt_payload_includes_authorized_github_context():
    payload = json.loads(
        build_link_scan_prompt_payload(
            evidence_type="project",
            evidence=_github_project(),
            requested_highlight_count=6,
            authorized_github_contexts=[_github_context()],
            web_search_enabled=False,
        )
    )

    assert payload["scan_targets"][0]["instructions"].startswith(
        "Use the supplied authorized_github_repositories context"
    )
    assert payload["authorized_github_repositories"] == [
        {
            "repo_scope": "https://github.com/openai/resumecr7",
            "owner": "openai",
            "repo": "resumecr7",
            "default_branch": "main",
            "html_url": "https://github.com/openai/resumecr7",
            "description": "Resume evidence workbench.",
            "files": [
                {
                    "path": "README.md",
                    "source_url": "https://github.com/openai/resumecr7/blob/main/README.md",
                    "text": (
                        "ResumeCR7 is a FastAPI and React workbench for grounded resume evidence."
                    ),
                }
            ],
        }
    ]
    assert payload["grounding_rules"][0].startswith(
        "Read supplied GitHub repository targets"
    )


def test_build_link_scan_instructions_forbids_skill_addition():
    instructions = build_link_scan_instructions()

    assert "Use web search" in instructions
    assert "do not crawl additional pages" in instructions
    assert "github_repo targets" in instructions
    assert "same repository" in instructions
    assert "Do not include skills" in instructions


def test_build_link_scan_response_create_kwargs_uses_web_search_and_strict_schema():
    kwargs = build_link_scan_response_create_kwargs(
        model="test-model",
        instructions="instructions",
        prompt_payload="{}",
        schema=build_link_scan_schema(),
        max_output_tokens=444,
    )

    assert kwargs["model"] == "test-model"
    assert kwargs["tools"] == [{"type": "web_search"}]
    assert kwargs["tool_choice"] == "required"
    assert kwargs["include"] == ["web_search_call.action.sources"]
    assert kwargs["temperature"] == 0
    assert kwargs["text"]["format"]["name"] == "link_evidence_enrichment"
    assert kwargs["text"]["format"]["strict"] is True


def test_build_link_scan_response_create_kwargs_can_disable_web_search():
    kwargs = build_link_scan_response_create_kwargs(
        model="test-model",
        instructions="instructions",
        prompt_payload="{}",
        schema=build_link_scan_schema(),
        max_output_tokens=444,
        use_web_search=False,
    )

    assert "tools" not in kwargs
    assert "tool_choice" not in kwargs
    assert "include" not in kwargs


def test_resolve_link_scan_max_output_tokens_uses_dynamic_highlight_budget(monkeypatch):
    monkeypatch.setattr(link_llm_client.settings, "LINK_SCANNING_DEFAULT_HIGHLIGHT_COUNT", 6)
    monkeypatch.setattr(link_llm_client.settings, "LINK_SCANNING_MAX_TOKENS_PER_HIGHLIGHT", 120)

    assert (
        resolve_link_scan_max_output_tokens(
            requested_highlight_count=4,
            max_tokens_per_highlight=90,
        )
        == 360
    )
    assert resolve_link_scan_max_output_tokens() == 720
    assert (
        resolve_link_scan_max_output_tokens(
            max_output_tokens=333,
            requested_highlight_count=4,
            max_tokens_per_highlight=90,
        )
        == 333
    )


def test_scan_evidence_links_with_llm_sends_web_search_request(monkeypatch):
    captured = {}

    class DummyResponses:
        def create(self, **kwargs):
            captured["kwargs"] = kwargs
            return SimpleNamespace(
                output_text=json.dumps(
                    {
                        "highlights": [
                            {
                                "text": "Scanned README confirms grounded resume orchestration.",
                                "source_url": "https://example.com/resumecr7",
                            }
                        ]
                    }
                ),
                output=[
                    SimpleNamespace(
                        action=SimpleNamespace(
                            sources=[SimpleNamespace(url="https://example.com/resumecr7")]
                        )
                    )
                ],
                usage=SimpleNamespace(input_tokens=20, output_tokens=10, total_tokens=30),
            )

    class DummyOpenAI:
        def __init__(self, **kwargs):
            captured["init"] = kwargs
            self.responses = DummyResponses()

    monkeypatch.setattr(link_llm_client, "OpenAI", DummyOpenAI)
    monkeypatch.setattr(link_llm_client.settings, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(link_llm_client.settings, "LINK_SCANNING_LLM_MODEL", "test-model")
    monkeypatch.setattr(link_llm_client.settings, "LINK_SCANNING_DEFAULT_HIGHLIGHT_COUNT", 5)
    monkeypatch.setattr(link_llm_client.settings, "LINK_SCANNING_MAX_TOKENS_PER_HIGHLIGHT", 111)

    result = scan_evidence_links_with_llm(
        evidence_type="project",
        evidence=_project(),
    )

    assert captured["init"]["api_key"] == "test-key"
    kwargs = captured["kwargs"]
    assert kwargs["model"] == "test-model"
    assert kwargs["max_output_tokens"] == 555
    assert kwargs["tools"] == [{"type": "web_search"}]
    assert kwargs["tool_choice"] == "required"
    payload = json.loads(kwargs["input"])
    assert payload["evidence"]["id"] == "resumecr7"
    assert payload["enrichment_goal"]["requested_highlight_count"] == 5
    assert len(payload["evidence"]["links"]) == 2
    assert result.highlights[0].text.startswith("Scanned README")
    assert result.metadata["source_urls"] == ["https://example.com/resumecr7"]
    assert result.metadata["total_tokens"] == 30


def test_scan_evidence_links_with_llm_accepts_same_github_repo_source(monkeypatch):
    class DummyResponses:
        def create(self, **_kwargs):
            return SimpleNamespace(
                output_text=json.dumps(
                    {
                        "highlights": [
                            {
                                "text": "README and tests show a FastAPI orchestration layer with deterministic evidence validation.",
                                "source_url": "https://github.com/openai/resumecr7/blob/main/README.md",
                            }
                        ]
                    }
                ),
                output=[
                    SimpleNamespace(
                        action=SimpleNamespace(
                            sources=[
                                SimpleNamespace(
                                    url="https://github.com/openai/other-repo/blob/main/README.md"
                                )
                            ]
                        )
                    )
                ],
                usage=None,
            )

    class DummyOpenAI:
        def __init__(self, **_kwargs):
            self.responses = DummyResponses()

    monkeypatch.setattr(link_llm_client, "OpenAI", DummyOpenAI)
    monkeypatch.setattr(link_llm_client.settings, "OPENAI_API_KEY", "test-key")

    result = scan_evidence_links_with_llm(
        evidence_type="project",
        evidence=_github_project(),
    )

    assert result.highlights[0].source_url == (
        "https://github.com/openai/resumecr7/blob/main/README.md"
    )
    assert result.metadata["scan_targets"][0]["mode"] == "github_repo"
    assert result.metadata["scan_targets"][0]["repo_scope"] == (
        "https://github.com/openai/resumecr7"
    )


def test_scan_evidence_links_with_llm_uses_authorized_github_context_without_web_search(
    monkeypatch,
):
    captured = {}
    project = ProjectRecord(
        id="resumecr7",
        name="ResumeCR7",
        summary="FastAPI resume engine for grounded resume generation.",
        highlights=["Built project and skill selection APIs."],
        active=True,
        skills=ProjectSkills(
            technology=["FastAPI"],
            programming=["Python"],
            concepts=["API"],
        ),
        links=["https://github.com/openai/resumecr7"],
    )

    class DummyResponses:
        def create(self, **kwargs):
            captured["kwargs"] = kwargs
            return SimpleNamespace(
                output_text=json.dumps(
                    {
                        "highlights": [
                            {
                                "text": "README shows ResumeCR7 uses FastAPI and React for grounded resume evidence.",
                                "source_url": "https://github.com/openai/resumecr7/blob/main/README.md",
                            }
                        ]
                    }
                ),
                output=[],
                usage=SimpleNamespace(input_tokens=30, output_tokens=12, total_tokens=42),
            )

    class DummyOpenAI:
        def __init__(self, **_kwargs):
            self.responses = DummyResponses()

    def fake_fetch_github_repo_context(**kwargs):
        captured["github_fetch"] = kwargs
        return _github_context()

    monkeypatch.setattr(link_llm_client, "OpenAI", DummyOpenAI)
    monkeypatch.setattr(link_llm_client.settings, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(link_llm_client, "get_github_token", lambda: "github-token")
    monkeypatch.setattr(
        link_llm_client,
        "fetch_github_repo_context",
        fake_fetch_github_repo_context,
    )

    result = scan_evidence_links_with_llm(
        evidence_type="project",
        evidence=project,
    )

    assert captured["github_fetch"]["token"] == "github-token"
    kwargs = captured["kwargs"]
    assert "tools" not in kwargs
    payload = json.loads(kwargs["input"])
    assert payload["authorized_github_repositories"][0]["files"][0]["path"] == "README.md"
    assert result.metadata["web_search_enabled"] is False
    assert result.metadata["authorized_github_repositories"][0]["file_count"] == 1


def test_scan_evidence_links_with_llm_omits_temperature_for_gpt_5_mini(monkeypatch):
    captured = {}

    class DummyResponses:
        def create(self, **kwargs):
            captured["kwargs"] = kwargs
            return SimpleNamespace(
                output_text='{"highlights":[]}',
                output=[],
                usage=None,
            )

    class DummyOpenAI:
        def __init__(self, **_kwargs):
            self.responses = DummyResponses()

    monkeypatch.setattr(link_llm_client, "OpenAI", DummyOpenAI)
    monkeypatch.setattr(link_llm_client.settings, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(link_llm_client.settings, "LINK_SCANNING_LLM_MODEL", "gpt-5-mini")

    scan_evidence_links_with_llm(
        evidence_type="project",
        evidence=_project(),
    )

    assert "temperature" not in captured["kwargs"]


def test_scan_evidence_links_with_llm_omits_temperature_for_gpt_5_6_terra(monkeypatch):
    captured = {}

    class DummyResponses:
        def create(self, **kwargs):
            captured["kwargs"] = kwargs
            return SimpleNamespace(
                output_text='{"highlights":[]}',
                output=[],
                usage=None,
            )

    class DummyOpenAI:
        def __init__(self, **_kwargs):
            self.responses = DummyResponses()

    monkeypatch.setattr(link_llm_client, "OpenAI", DummyOpenAI)
    monkeypatch.setattr(link_llm_client.settings, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        link_llm_client.settings,
        "LINK_SCANNING_LLM_MODEL",
        "gpt-5.6-terra",
    )

    scan_evidence_links_with_llm(
        evidence_type="project",
        evidence=_project(),
    )

    assert "temperature" not in captured["kwargs"]


def test_scan_evidence_links_with_llm_reads_structured_output_when_output_text_missing(
    monkeypatch,
):
    class DummyResponses:
        def create(self, **_kwargs):
            return SimpleNamespace(
                output=[
                    SimpleNamespace(
                        content=[
                            SimpleNamespace(
                                text=json.dumps(
                                    {
                                        "highlights": [
                                            {
                                                "text": "README documents a FastAPI link scanning workflow.",
                                                "source_url": "https://github.com/openai/resumecr7/blob/main/README.md",
                                            }
                                        ]
                                    }
                                )
                            )
                        ]
                    ),
                    SimpleNamespace(
                        action=SimpleNamespace(
                            sources=[
                                SimpleNamespace(
                                    url="https://github.com/openai/resumecr7/blob/main/README.md"
                                )
                            ]
                        )
                    ),
                ],
                usage=SimpleNamespace(input_tokens=12, output_tokens=8, total_tokens=20),
            )

    class DummyOpenAI:
        def __init__(self, **_kwargs):
            self.responses = DummyResponses()

    monkeypatch.setattr(link_llm_client, "OpenAI", DummyOpenAI)
    monkeypatch.setattr(link_llm_client.settings, "OPENAI_API_KEY", "test-key")

    result = scan_evidence_links_with_llm(
        evidence_type="project",
        evidence=_github_project(),
    )

    assert result.highlights[0].text == "README documents a FastAPI link scanning workflow."
    assert result.metadata["total_tokens"] == 20


def test_scan_evidence_links_with_llm_rejects_invalid_json(monkeypatch):
    class DummyResponses:
        def create(self, **_kwargs):
            return SimpleNamespace(output_text="{not-json", output=[], usage=None)

    class DummyOpenAI:
        def __init__(self, **_kwargs):
            self.responses = DummyResponses()

    monkeypatch.setattr(link_llm_client, "OpenAI", DummyOpenAI)
    monkeypatch.setattr(link_llm_client.settings, "OPENAI_API_KEY", "test-key")

    with pytest.raises(LinkScanningLLMClientError, match="valid JSON"):
        scan_evidence_links_with_llm(
            evidence_type="project",
            evidence=_project(),
        )


def test_scan_evidence_links_with_llm_rejects_unknown_source_url(monkeypatch):
    class DummyResponses:
        def create(self, **_kwargs):
            return SimpleNamespace(
                output_text=json.dumps(
                    {
                        "highlights": [
                            {
                                "text": "Unsupported source.",
                                "source_url": "https://unrelated.example.com/page",
                            }
                        ]
                    }
                ),
                output=[
                    SimpleNamespace(
                        action=SimpleNamespace(
                            sources=[
                                SimpleNamespace(
                                    url="https://github.com/openai/other-repo/blob/main/README.md"
                                )
                            ]
                        )
                    )
                ],
                usage=None,
            )

    class DummyOpenAI:
        def __init__(self, **_kwargs):
            self.responses = DummyResponses()

    monkeypatch.setattr(link_llm_client, "OpenAI", DummyOpenAI)
    monkeypatch.setattr(link_llm_client.settings, "OPENAI_API_KEY", "test-key")

    with pytest.raises(LinkScanningLLMClientError, match="source_url"):
        scan_evidence_links_with_llm(
            evidence_type="project",
            evidence=_project(),
        )


def test_scan_evidence_links_with_llm_rejects_other_github_repo_source(monkeypatch):
    class DummyResponses:
        def create(self, **_kwargs):
            return SimpleNamespace(
                output_text=json.dumps(
                    {
                        "highlights": [
                            {
                                "text": "Unsupported cross-repo source.",
                                "source_url": "https://github.com/openai/other-repo/blob/main/README.md",
                            }
                        ]
                    }
                ),
                output=[
                    SimpleNamespace(
                        action=SimpleNamespace(
                            sources=[
                                SimpleNamespace(
                                    url="https://github.com/openai/other-repo/blob/main/README.md"
                                )
                            ]
                        )
                    )
                ],
                usage=None,
            )

    class DummyOpenAI:
        def __init__(self, **_kwargs):
            self.responses = DummyResponses()

    monkeypatch.setattr(link_llm_client, "OpenAI", DummyOpenAI)
    monkeypatch.setattr(link_llm_client.settings, "OPENAI_API_KEY", "test-key")

    with pytest.raises(LinkScanningLLMClientError, match="source_url"):
        scan_evidence_links_with_llm(
            evidence_type="project",
            evidence=_github_project(),
        )


def test_scan_evidence_links_with_llm_requires_api_key(monkeypatch, tmp_path):
    monkeypatch.setattr(link_llm_client.settings, "OPENAI_API_KEY", "")
    monkeypatch.setattr(link_llm_client.settings, "RESUME_GENERATION_ROOT", tmp_path)

    with pytest.raises(LinkScanningLLMClientError, match="OPENAI_API_KEY"):
        scan_evidence_links_with_llm(
            evidence_type="project",
            evidence=_project(),
        )
