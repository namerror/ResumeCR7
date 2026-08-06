from __future__ import annotations

import base64

import pytest
import requests

from app.link_scanning.github_client import (
    GitHubRepoScanError,
    fetch_github_repo_context,
    parse_github_repo_url,
)


class DummyResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


class DummySession:
    def __init__(self, responses: dict[str, DummyResponse]):
        self.headers = {}
        self.responses = responses
        self.calls: list[tuple[str, dict | None]] = []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params))
        response = self.responses.get(url)
        if response is None:
            raise AssertionError(f"Unexpected URL: {url}")
        return response


def test_parse_github_repo_url_extracts_repo_and_subpath():
    root = parse_github_repo_url("https://github.com/openai/resumecr7")
    blob = parse_github_repo_url(
        "https://github.com/openai/resumecr7/blob/main/docs/setup.md"
    )
    tree = parse_github_repo_url("https://github.com/openai/resumecr7/tree/main/app")

    assert root is not None
    assert root.owner == "openai"
    assert root.repo == "resumecr7"
    assert root.requested_path is None
    assert blob is not None
    assert blob.requested_path == "docs/setup.md"
    assert tree is not None
    assert tree.requested_path == "app"


def test_fetch_github_repo_context_uses_auth_and_deterministic_file_selection(monkeypatch):
    sessions: list[DummySession] = []
    readme_content = base64.b64encode(b"# ResumeCR7\nFastAPI evidence scanner.").decode()
    app_content = base64.b64encode(b"def scan():\n    return 'grounded'\n").decode()
    responses = {
        "https://api.github.com/repos/openai/resumecr7": DummyResponse(
            200,
            {
                "default_branch": "main",
                "html_url": "https://github.com/openai/resumecr7",
                "description": "Resume evidence workbench.",
            },
        ),
        "https://api.github.com/repos/openai/resumecr7/git/trees/main": DummyResponse(
            200,
            {
                "tree": [
                    {"path": "image.png", "type": "blob", "size": 100},
                    {"path": "app/scanner.py", "type": "blob", "size": 30},
                    {"path": "README.md", "type": "blob", "size": 35},
                ]
            },
        ),
        "https://api.github.com/repos/openai/resumecr7/contents/app/scanner.py": DummyResponse(
            200,
            {"content": app_content, "encoding": "base64"},
        ),
        "https://api.github.com/repos/openai/resumecr7/contents/README.md": DummyResponse(
            200,
            {"content": readme_content, "encoding": "base64"},
        ),
    }

    def session_factory():
        session = DummySession(responses)
        sessions.append(session)
        return session

    monkeypatch.setattr("app.link_scanning.github_client.requests.Session", session_factory)

    context = fetch_github_repo_context(
        repo_scope="https://github.com/openai/resumecr7",
        source_url="https://github.com/openai/resumecr7/tree/main/app",
        token="github-token",
    )

    assert sessions[0].headers["Authorization"] == "Bearer github-token"
    assert [file.path for file in context.files] == ["app/scanner.py", "README.md"]
    assert context.files[0].html_url == (
        "https://github.com/openai/resumecr7/blob/main/app/scanner.py"
    )
    assert "grounded" in context.files[0].text


def test_fetch_github_repo_context_maps_auth_failures(monkeypatch):
    def session_factory():
        return DummySession(
            {
                "https://api.github.com/repos/openai/private": DummyResponse(
                    403,
                    {"message": "Forbidden"},
                )
            }
        )

    monkeypatch.setattr("app.link_scanning.github_client.requests.Session", session_factory)

    with pytest.raises(GitHubRepoScanError, match="not authorized"):
        fetch_github_repo_context(
            repo_scope="https://github.com/openai/private",
            source_url="https://github.com/openai/private",
            token="github-token",
        )
