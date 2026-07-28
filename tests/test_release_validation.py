from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import validate_release


def write_release_repo(root: Path, *, app_version: str = "0.1.0") -> None:
    (root / "app").mkdir(parents=True)
    (root / "app" / "__init__.py").write_text(
        f'__version__ = "{app_version}"\n',
        encoding="utf-8",
    )
    tauri_root = root / "frontend" / "src-tauri"
    tauri_root.mkdir(parents=True)
    (tauri_root / "tauri.conf.json").write_text(
        json.dumps({"version": "0.1.0"}),
        encoding="utf-8",
    )
    (tauri_root / "Cargo.toml").write_text(
        '[package]\nname = "resumecr7-desktop"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    (root / "docs").mkdir()
    (root / "docs" / "CHANGELOG.md").write_text(
        "\n".join(
            [
                "# Changelog",
                "",
                "## [0.1.0] - 2026-07-28",
                "",
                "### Added",
                "- Linux AppImage desktop preview.",
                "",
                "## [0.0.1] - 2026-07-23",
                "",
                "### Added",
                "- Prior release.",
                "",
            ]
        ),
        encoding="utf-8",
    )


def test_validate_release_accepts_matching_metadata(tmp_path):
    write_release_repo(tmp_path)

    assert validate_release.validate_release("v0.1.0", tmp_path) == "0.1.0"


def test_validate_release_rejects_invalid_tag(tmp_path):
    write_release_repo(tmp_path)

    with pytest.raises(validate_release.ReleaseValidationError, match="vX.Y.Z"):
        validate_release.validate_release("0.1.0", tmp_path)


def test_validate_release_rejects_app_version_mismatch(tmp_path):
    write_release_repo(tmp_path, app_version="0.3.0")

    with pytest.raises(validate_release.ReleaseValidationError, match="app.__version__"):
        validate_release.validate_release("v0.1.0", tmp_path)


def test_release_notes_for_version_uses_latest_changelog_section(tmp_path):
    write_release_repo(tmp_path)

    notes = validate_release.release_notes_for_version("0.1.0", tmp_path)

    assert "Linux AppImage desktop preview" in notes
    assert "Prior release" not in notes


def test_release_notes_rejects_non_latest_changelog_version(tmp_path):
    write_release_repo(tmp_path)

    with pytest.raises(validate_release.ReleaseValidationError, match="Latest changelog"):
        validate_release.release_notes_for_version("0.0.1", tmp_path)


def test_main_writes_release_notes(monkeypatch, tmp_path):
    write_release_repo(tmp_path)
    notes_path = tmp_path / "release-notes.md"
    monkeypatch.setattr(validate_release, "REPO_ROOT", tmp_path)

    assert validate_release.main(["--tag", "v0.1.0", "--notes-out", str(notes_path)]) == 0
    assert "Linux AppImage desktop preview" in notes_path.read_text(encoding="utf-8")
