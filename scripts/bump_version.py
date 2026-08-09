from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import validate_release


TAG_RE = re.compile(r"^v(?P<version>\d+\.\d+\.\d+)$")
APP_VERSION_RE = re.compile(r'(?m)^(__version__\s*=\s*")(\d+\.\d+\.\d+)(")\s*$')
TAURI_VERSION_RE = re.compile(r'(?m)^(  "version": ")(\d+\.\d+\.\d+)(",?)\s*$')
CARGO_PACKAGE_VERSION_RE = re.compile(
    r'(?ms)^(\[package\].*?^version\s*=\s*")(\d+\.\d+\.\d+)(")\s*$'
)
CARGO_LOCK_PACKAGE_RE = re.compile(
    r'(?ms)^(\[\[package\]\]\nname = "resumecr7-desktop"\nversion = ")'
    r'(\d+\.\d+\.\d+)(")'
)


VERSION_FILES = (
    Path("app/__init__.py"),
    Path("docs/CHANGELOG.md"),
    Path("frontend/src-tauri/Cargo.lock"),
    Path("frontend/src-tauri/Cargo.toml"),
    Path("frontend/src-tauri/tauri.conf.json"),
)
VERSION_FILE_NAMES = frozenset(str(path) for path in VERSION_FILES)


class VersionBumpError(RuntimeError):
    pass


def parse_tag_version(tag: str) -> str:
    match = TAG_RE.fullmatch(tag)
    if not match:
        raise VersionBumpError(f"Release tag must match vX.Y.Z: {tag}")
    return match.group("version")


def replace_once(text: str, pattern: re.Pattern[str], replacement: str, label: str) -> str:
    updated, count = pattern.subn(replacement, text, count=1)
    if count != 1:
        raise VersionBumpError(f"Could not update {label}")
    return updated


def update_app_version(repo_root: Path, version: str, *, dry_run: bool) -> None:
    path = repo_root / "app" / "__init__.py"
    text = path.read_text(encoding="utf-8")
    updated = replace_once(text, APP_VERSION_RE, rf'\g<1>{version}\g<3>', str(path))
    if not dry_run:
        path.write_text(updated, encoding="utf-8")


def update_tauri_config(repo_root: Path, version: str, *, dry_run: bool) -> None:
    path = repo_root / "frontend" / "src-tauri" / "tauri.conf.json"
    text = path.read_text(encoding="utf-8")
    json.loads(text)
    updated = replace_once(text, TAURI_VERSION_RE, rf'\g<1>{version}\g<3>', str(path))
    json.loads(updated)
    if not dry_run:
        path.write_text(updated, encoding="utf-8")


def update_cargo_manifest(repo_root: Path, version: str, *, dry_run: bool) -> None:
    path = repo_root / "frontend" / "src-tauri" / "Cargo.toml"
    text = path.read_text(encoding="utf-8")
    tomllib.loads(text)
    updated = replace_once(
        text,
        CARGO_PACKAGE_VERSION_RE,
        rf'\g<1>{version}\g<3>',
        str(path),
    )
    manifest = tomllib.loads(updated)
    if manifest.get("package", {}).get("version") != version:
        raise VersionBumpError(f"Could not verify Cargo package version in {path}")
    if not dry_run:
        path.write_text(updated, encoding="utf-8")


def update_cargo_lock(repo_root: Path, version: str, *, dry_run: bool) -> None:
    path = repo_root / "frontend" / "src-tauri" / "Cargo.lock"
    text = path.read_text(encoding="utf-8")
    updated, count = CARGO_LOCK_PACKAGE_RE.subn(rf'\g<1>{version}\g<3>', text)
    if count != 1:
        raise VersionBumpError(f"Could not update resumecr7-desktop package in {path}")
    if not dry_run:
        path.write_text(updated, encoding="utf-8")


def validate_changelog_ready(repo_root: Path, version: str) -> None:
    try:
        validate_release.release_notes_for_version(version, repo_root)
    except validate_release.ReleaseValidationError as exc:
        raise VersionBumpError(str(exc)) from exc


def apply_version_updates(repo_root: Path, tag: str, *, dry_run: bool = False) -> str:
    version = parse_tag_version(tag)
    validate_changelog_ready(repo_root, version)
    update_app_version(repo_root, version, dry_run=dry_run)
    update_tauri_config(repo_root, version, dry_run=dry_run)
    update_cargo_manifest(repo_root, version, dry_run=dry_run)
    update_cargo_lock(repo_root, version, dry_run=dry_run)
    if not dry_run:
        try:
            validate_release.validate_release(tag, repo_root)
        except validate_release.ReleaseValidationError as exc:
            raise VersionBumpError(str(exc)) from exc
    return version


def run_git(args: list[str], repo_root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=False,
        text=True,
        capture_output=True,
    )


def status_paths(status_output: str) -> list[str]:
    paths: list[str] = []
    for line in status_output.splitlines():
        if len(line) < 4:
            continue
        path = line[3:]
        if " -> " in path:
            paths.extend(path.split(" -> ", maxsplit=1))
        else:
            paths.append(path)
    return paths


def require_no_unrelated_worktree_changes(repo_root: Path) -> None:
    result = run_git(["status", "--porcelain"], repo_root)
    if result.returncode != 0:
        raise VersionBumpError(result.stderr.strip() or "Could not inspect git status")
    unrelated = sorted(
        path for path in status_paths(result.stdout) if path not in VERSION_FILE_NAMES
    )
    if unrelated:
        raise VersionBumpError(
            "Unrelated worktree changes present: " + ", ".join(unrelated)
        )


def require_tag_available(repo_root: Path, tag: str) -> None:
    result = run_git(["rev-parse", "-q", "--verify", f"refs/tags/{tag}"], repo_root)
    if result.returncode == 0:
        raise VersionBumpError(f"Tag already exists: {tag}")


def current_branch(repo_root: Path) -> str:
    result = run_git(["branch", "--show-current"], repo_root)
    if result.returncode != 0:
        raise VersionBumpError(result.stderr.strip() or "Could not inspect current branch")
    branch = result.stdout.strip()
    if not branch:
        raise VersionBumpError("Cannot push from detached HEAD")
    return branch


def run_checked_git(args: list[str], repo_root: Path) -> None:
    print("+ git " + " ".join(args))
    result = run_git(args, repo_root)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise VersionBumpError(detail or f"git {' '.join(args)} failed")


def commit_tag_and_push(
    repo_root: Path,
    tag: str,
    *,
    remote: str,
    push: bool,
) -> None:
    branch = current_branch(repo_root)
    run_checked_git(["add", *(str(path) for path in VERSION_FILES)], repo_root)
    run_checked_git(["commit", "-m", f"Bump version {tag}"], repo_root)
    run_checked_git(["tag", tag], repo_root)
    if push:
        run_checked_git(["push", remote, branch], repo_root)
        run_checked_git(["push", remote, tag], repo_root)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bump ResumeCR7 release metadata.")
    parser.add_argument("tag", help="Release tag, for example v0.1.4.")
    parser.add_argument("--remote", default="origin", help="Git remote to push to.")
    parser.add_argument(
        "--no-push",
        action="store_true",
        help="Commit and tag locally, but do not push the branch or tag.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate inputs and print planned actions without changing files.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    try:
        version = parse_tag_version(args.tag)
        require_no_unrelated_worktree_changes(REPO_ROOT)
        require_tag_available(REPO_ROOT, args.tag)
        apply_version_updates(REPO_ROOT, args.tag, dry_run=args.dry_run)
        if args.dry_run:
            print(f"Would update release metadata for v{version}")
            print(f"Would stage: {', '.join(str(path) for path in VERSION_FILES)}")
            print(f"Would commit: Bump version {args.tag}")
            print(f"Would create lightweight tag: {args.tag}")
            if not args.no_push:
                branch = current_branch(REPO_ROOT)
                print(f"Would push {branch} and {args.tag} to {args.remote}")
            return 0
        commit_tag_and_push(REPO_ROOT, args.tag, remote=args.remote, push=not args.no_push)
    except VersionBumpError as exc:
        print(f"Version bump failed: {exc}", file=sys.stderr)
        return 1
    print(f"Version bumped to v{version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
