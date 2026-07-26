from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
TAG_RE = re.compile(r"^v(?P<version>\d+\.\d+\.\d+)$")
APP_VERSION_RE = re.compile(r'^__version__\s*=\s*"(?P<version>\d+\.\d+\.\d+)"\s*$')
CHANGELOG_HEADING_RE = re.compile(
    r"^## \[(?P<version>\d+\.\d+\.\d+)\] - (?P<date>\d{4}-\d{2}-\d{2})$"
)


class ReleaseValidationError(ValueError):
    pass


@dataclass(frozen=True)
class ChangelogSection:
    version: str
    body: str


def parse_tag_version(tag: str) -> str:
    match = TAG_RE.fullmatch(tag)
    if not match:
        raise ReleaseValidationError(f"Release tag must match vX.Y.Z: {tag}")
    return match.group("version")


def read_app_version(repo_root: Path = REPO_ROOT) -> str:
    init_file = repo_root / "app" / "__init__.py"
    for line in init_file.read_text(encoding="utf-8").splitlines():
        match = APP_VERSION_RE.match(line)
        if match:
            return match.group("version")
    raise ReleaseValidationError(f"Could not find __version__ in {init_file}")


def read_tauri_version(repo_root: Path = REPO_ROOT) -> str:
    config_path = repo_root / "frontend" / "src-tauri" / "tauri.conf.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    version = config.get("version")
    if not isinstance(version, str):
        raise ReleaseValidationError(f"Missing Tauri version in {config_path}")
    return version


def read_cargo_version(repo_root: Path = REPO_ROOT) -> str:
    manifest_path = repo_root / "frontend" / "src-tauri" / "Cargo.toml"
    manifest = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
    version = manifest.get("package", {}).get("version")
    if not isinstance(version, str):
        raise ReleaseValidationError(f"Missing Cargo package version in {manifest_path}")
    return version


def extract_changelog_sections(repo_root: Path = REPO_ROOT) -> list[ChangelogSection]:
    changelog_path = repo_root / "docs" / "CHANGELOG.md"
    lines = changelog_path.read_text(encoding="utf-8").splitlines()
    sections: list[ChangelogSection] = []
    current_version: str | None = None
    current_body: list[str] = []

    for line in lines:
        match = CHANGELOG_HEADING_RE.match(line)
        if match:
            if current_version is not None:
                sections.append(
                    ChangelogSection(
                        version=current_version,
                        body="\n".join(current_body).strip() + "\n",
                    )
                )
            current_version = match.group("version")
            current_body = []
            continue
        if current_version is not None:
            current_body.append(line)

    if current_version is not None:
        sections.append(
            ChangelogSection(
                version=current_version,
                body="\n".join(current_body).strip() + "\n",
            )
        )
    return sections


def latest_changelog_section(repo_root: Path = REPO_ROOT) -> ChangelogSection:
    sections = extract_changelog_sections(repo_root)
    if not sections:
        raise ReleaseValidationError("No released changelog sections found")
    return sections[0]


def release_notes_for_version(version: str, repo_root: Path = REPO_ROOT) -> str:
    section = latest_changelog_section(repo_root)
    if section.version != version:
        raise ReleaseValidationError(
            f"Latest changelog release is {section.version}, expected {version}"
        )
    if not section.body.strip():
        raise ReleaseValidationError(f"Changelog section for {version} is empty")
    return section.body


def assert_matches(label: str, actual: str, expected: str) -> None:
    if actual != expected:
        raise ReleaseValidationError(f"{label} version is {actual}, expected {expected}")


def validate_release(tag: str, repo_root: Path = REPO_ROOT) -> str:
    version = parse_tag_version(tag)
    assert_matches("app.__version__", read_app_version(repo_root), version)
    assert_matches("Tauri config", read_tauri_version(repo_root), version)
    assert_matches("Cargo package", read_cargo_version(repo_root), version)
    release_notes_for_version(version, repo_root)
    return version


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate ResumeCR7 release metadata.")
    parser.add_argument("--tag", required=True, help="Release tag, for example v0.4.0.")
    parser.add_argument(
        "--notes-out",
        type=Path,
        help="Write release notes extracted from docs/CHANGELOG.md to this path.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    try:
        version = validate_release(args.tag, REPO_ROOT)
        notes = release_notes_for_version(version, REPO_ROOT)
    except ReleaseValidationError as exc:
        print(f"Release validation failed: {exc}", file=sys.stderr)
        return 1

    if args.notes_out is not None:
        args.notes_out.write_text(notes, encoding="utf-8")
    print(f"Release metadata validated for v{version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
