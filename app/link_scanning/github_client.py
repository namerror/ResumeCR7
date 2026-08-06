from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any, Iterable
from urllib.parse import quote, urlparse

import requests


class GitHubRepoScanError(RuntimeError):
    """Raised when an authorized GitHub repository cannot be scanned."""


@dataclass(frozen=True)
class GitHubRepoRef:
    owner: str
    repo: str
    requested_path: str | None = None


@dataclass(frozen=True)
class GitHubRepoFileContext:
    path: str
    html_url: str
    text: str


@dataclass(frozen=True)
class GitHubRepoContext:
    repo_scope: str
    owner: str
    repo: str
    default_branch: str
    html_url: str
    description: str | None
    files: tuple[GitHubRepoFileContext, ...]


GITHUB_API_BASE_URL = "https://api.github.com"
GITHUB_API_VERSION = "2026-03-10"
MAX_REPO_CONTEXT_FILES = 14
MAX_REPO_CONTEXT_TOTAL_CHARS = 24000
MAX_REPO_CONTEXT_FILE_CHARS = 5000
MAX_FETCHABLE_FILE_SIZE_BYTES = 120000

_GITHUB_HOSTS = {"github.com", "www.github.com"}
_TEXT_EXTENSIONS = {
    ".cfg",
    ".conf",
    ".css",
    ".go",
    ".h",
    ".hpp",
    ".html",
    ".ini",
    ".java",
    ".js",
    ".json",
    ".jsx",
    ".kt",
    ".md",
    ".mjs",
    ".py",
    ".rb",
    ".rs",
    ".sh",
    ".sql",
    ".swift",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}
_BINARY_EXTENSIONS = {
    ".7z",
    ".avif",
    ".bmp",
    ".class",
    ".dll",
    ".dmg",
    ".doc",
    ".docx",
    ".eot",
    ".exe",
    ".gif",
    ".gz",
    ".ico",
    ".jar",
    ".jpeg",
    ".jpg",
    ".lock",
    ".mp3",
    ".mp4",
    ".otf",
    ".pdf",
    ".png",
    ".pyc",
    ".so",
    ".tar",
    ".ttf",
    ".webm",
    ".webp",
    ".woff",
    ".woff2",
    ".xls",
    ".xlsx",
    ".zip",
}
_MANIFEST_NAMES = {
    "cargo.toml",
    "composer.json",
    "go.mod",
    "package.json",
    "pom.xml",
    "pyproject.toml",
    "requirements.txt",
    "setup.cfg",
    "setup.py",
    "uv.lock",
}


def parse_github_repo_url(url: str) -> GitHubRepoRef | None:
    parsed = urlparse(url.strip())
    hostname = (parsed.hostname or "").lower()
    path_parts = [part for part in parsed.path.split("/") if part]
    if parsed.scheme not in {"http", "https"} or hostname not in _GITHUB_HOSTS:
        return None
    if len(path_parts) < 2:
        return None

    owner = path_parts[0]
    repo = path_parts[1].removesuffix(".git")
    requested_path = None
    if len(path_parts) >= 5 and path_parts[2] in {"blob", "tree"}:
        requested_path = "/".join(path_parts[4:]) or None
    return GitHubRepoRef(owner=owner, repo=repo, requested_path=requested_path)


def fetch_github_repo_context(
    *,
    repo_scope: str,
    source_url: str,
    token: str,
    timeout_seconds: float = 15.0,
    max_files: int = MAX_REPO_CONTEXT_FILES,
    max_total_chars: int = MAX_REPO_CONTEXT_TOTAL_CHARS,
    max_file_chars: int = MAX_REPO_CONTEXT_FILE_CHARS,
) -> GitHubRepoContext:
    ref = parse_github_repo_url(source_url) or parse_github_repo_url(repo_scope)
    if ref is None:
        raise GitHubRepoScanError(f"Invalid GitHub repository URL: {source_url}")

    session = requests.Session()
    session.headers.update(
        {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": GITHUB_API_VERSION,
        }
    )

    repo_payload = _get_json(
        session,
        f"/repos/{quote(ref.owner)}/{quote(ref.repo)}",
        timeout_seconds=timeout_seconds,
        owner=ref.owner,
        repo=ref.repo,
    )
    default_branch = _required_string(repo_payload, "default_branch")
    html_url = _required_string(repo_payload, "html_url")
    description = repo_payload.get("description")
    if not isinstance(description, str):
        description = None

    tree_payload = _get_json(
        session,
        f"/repos/{quote(ref.owner)}/{quote(ref.repo)}/git/trees/{quote(default_branch)}",
        params={"recursive": "1"},
        timeout_seconds=timeout_seconds,
        owner=ref.owner,
        repo=ref.repo,
    )
    tree = tree_payload.get("tree")
    if not isinstance(tree, list):
        raise GitHubRepoScanError(f"GitHub tree response was invalid for {ref.owner}/{ref.repo}")

    selected_entries = _select_file_entries(
        tree,
        requested_path=ref.requested_path,
        max_files=max_files,
    )
    files: list[GitHubRepoFileContext] = []
    total_chars = 0
    for entry in selected_entries:
        path = entry["path"]
        remaining = max_total_chars - total_chars
        if remaining <= 0:
            break
        text = _fetch_file_text(
            session,
            owner=ref.owner,
            repo=ref.repo,
            path=path,
            ref=default_branch,
            timeout_seconds=timeout_seconds,
        )
        if not text.strip():
            continue
        clipped = text[: min(max_file_chars, remaining)]
        total_chars += len(clipped)
        files.append(
            GitHubRepoFileContext(
                path=path,
                html_url=f"{html_url}/blob/{default_branch}/{path}",
                text=clipped,
            )
        )

    return GitHubRepoContext(
        repo_scope=repo_scope,
        owner=ref.owner,
        repo=ref.repo,
        default_branch=default_branch,
        html_url=html_url,
        description=description,
        files=tuple(files),
    )


def _get_json(
    session: requests.Session,
    path: str,
    *,
    timeout_seconds: float,
    owner: str,
    repo: str,
    params: dict[str, str] | None = None,
) -> dict[str, Any]:
    url = f"{GITHUB_API_BASE_URL}{path}"
    try:
        response = session.get(url, params=params, timeout=timeout_seconds)
    except requests.RequestException as exc:
        raise GitHubRepoScanError(f"GitHub request failed for {owner}/{repo}: {exc}") from exc

    if response.status_code in {401, 403}:
        raise GitHubRepoScanError(
            f"GitHub token is not authorized to read {owner}/{repo}"
        )
    if response.status_code == 404:
        raise GitHubRepoScanError(
            f"GitHub repository {owner}/{repo} was not found or token lacks access"
        )
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        raise GitHubRepoScanError(
            f"GitHub request failed for {owner}/{repo}: HTTP {response.status_code}"
        ) from exc

    payload = response.json()
    if not isinstance(payload, dict):
        raise GitHubRepoScanError(f"GitHub response was invalid for {owner}/{repo}")
    return payload


def _fetch_file_text(
    session: requests.Session,
    *,
    owner: str,
    repo: str,
    path: str,
    ref: str,
    timeout_seconds: float,
) -> str:
    payload = _get_json(
        session,
        f"/repos/{quote(owner)}/{quote(repo)}/contents/{quote(path, safe='/')}",
        params={"ref": ref},
        timeout_seconds=timeout_seconds,
        owner=owner,
        repo=repo,
    )
    content = payload.get("content")
    encoding = payload.get("encoding")
    if not isinstance(content, str) or encoding != "base64":
        return ""
    try:
        return base64.b64decode(content, validate=False).decode("utf-8", errors="replace")
    except (ValueError, UnicodeDecodeError):
        return ""


def _select_file_entries(
    tree: Iterable[Any],
    *,
    requested_path: str | None,
    max_files: int,
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for raw_entry in tree:
        if not isinstance(raw_entry, dict):
            continue
        path = raw_entry.get("path")
        entry_type = raw_entry.get("type")
        size = raw_entry.get("size", 0)
        if not isinstance(path, str) or entry_type != "blob":
            continue
        if isinstance(size, int) and size > MAX_FETCHABLE_FILE_SIZE_BYTES:
            continue
        if not _is_scannable_text_path(path):
            continue
        score = _path_priority(path, requested_path)
        if score is None:
            continue
        entries.append({"path": path, "score": score})

    entries.sort(key=lambda entry: (entry["score"], entry["path"].casefold()))
    return entries[:max_files]


def _path_priority(path: str, requested_path: str | None) -> int | None:
    normalized = path.casefold()
    filename = normalized.rsplit("/", 1)[-1]

    if requested_path:
        requested = requested_path.strip("/").casefold()
        if normalized == requested or normalized.startswith(f"{requested}/"):
            return 0
    if filename == "readme" or filename.startswith("readme."):
        return 1
    if filename in _MANIFEST_NAMES:
        return 2
    if normalized.startswith(".github/workflows/") or filename in {
        ".gitlab-ci.yml",
        "dockerfile",
    }:
        return 3
    if normalized.startswith("docs/") or filename.endswith(".md"):
        return 4
    if normalized.startswith(("tests/", "test/", "__tests__/")) or "/tests/" in normalized:
        return 5
    if normalized.startswith(("app/", "src/", "frontend/src/", "backend/", "lib/")):
        return 6
    return None


def _is_scannable_text_path(path: str) -> bool:
    normalized = path.casefold()
    if any(
        part in {"node_modules", ".git", "dist", "build", "target", ".venv", "venv"}
        for part in normalized.split("/")
    ):
        return False

    filename = normalized.rsplit("/", 1)[-1]
    if (
        filename == "readme"
        or filename.startswith("readme.")
        or filename in _MANIFEST_NAMES
        or filename in {".gitlab-ci.yml", "dockerfile"}
    ):
        return True
    extension = ""
    if "." in filename:
        extension = f".{filename.rsplit('.', 1)[-1]}"
    if extension in _BINARY_EXTENSIONS:
        return False
    return extension in _TEXT_EXTENSIONS


def _required_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise GitHubRepoScanError(f"GitHub response missing {key}")
    return value
