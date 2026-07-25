import pytest
from pydantic import ValidationError

from app.data_paths import resolve_default_data_dir
from app.config import Settings


SCOPED_ENV_VARS = [
    "SKILL_METHOD",
    "SKILL_TOP_N",
    "SKILL_BASELINE_FILTER",
    "PROJ_METHOD",
    "PROJ_TOP_N",
    "SKILL_LLM_MODEL",
    "SKILL_LLM_MAX_OUTPUT_TOKENS",
    "PROJ_LLM_MODEL",
    "PROJ_LLM_MAX_OUTPUT_TOKENS",
    "BULLETPOINTS_LLM_MODEL",
    "BULLETPOINTS_LLM_MAX_OUTPUT_TOKENS",
    "BULLETPOINTS_DEFAULT_COUNT",
    "LINK_SCANNING_ENABLED",
    "LINK_SCANNING_LLM_MODEL",
    "LINK_SCANNING_LLM_MAX_OUTPUT_TOKENS",
    "LINK_SCANNING_DEFAULT_HIGHLIGHT_COUNT",
    "LINK_SCANNING_MAX_TOKENS_PER_HIGHLIGHT",
    "RESUMECR7_PACKAGED",
    "RESUMECR7_DATA_DIR",
    "RESUME_EVIDENCE_ROOT",
    "RESUME_GENERATION_ROOT",
    "RESUMECR7_LOG_DIR",
]
LEGACY_ENV_VARS = [
    "METHOD",
    "TOP_N",
    "BASELINE_FILTER",
    "LLM_MODEL",
    "LLM_MAX_OUTPUT_TOKENS",
]


def _clear_selection_env(monkeypatch):
    for name in SCOPED_ENV_VARS + LEGACY_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def test_settings_scoped_defaults(monkeypatch):
    _clear_selection_env(monkeypatch)

    settings = Settings(_env_file=None)

    assert settings.SKILL_METHOD == "baseline"
    assert settings.SKILL_TOP_N == 10
    assert settings.SKILL_BASELINE_FILTER is False
    assert settings.PROJ_METHOD == "llm"
    assert settings.PROJ_TOP_N is None
    assert settings.SKILL_LLM_MODEL == "gpt-5-mini"
    assert settings.PROJ_LLM_MODEL == "gpt-5-mini"
    assert settings.SKILL_LLM_MAX_OUTPUT_TOKENS == 1200
    assert settings.PROJ_LLM_MAX_OUTPUT_TOKENS == 1200
    assert settings.BULLETPOINTS_LLM_MODEL == "gpt-5-mini"
    assert settings.BULLETPOINTS_LLM_MAX_OUTPUT_TOKENS == 3000
    assert settings.BULLETPOINTS_DEFAULT_COUNT == 3
    assert settings.LINK_SCANNING_ENABLED is False
    assert settings.LINK_SCANNING_LLM_MODEL == "gpt-5-mini"
    assert settings.LINK_SCANNING_LLM_MAX_OUTPUT_TOKENS == 1200
    assert settings.LINK_SCANNING_DEFAULT_HIGHLIGHT_COUNT == 6
    assert settings.LINK_SCANNING_MAX_TOKENS_PER_HIGHLIGHT == 120
    assert settings.RESUMECR7_PACKAGED is False
    assert str(settings.RESUMECR7_DATA_DIR).endswith("user")
    assert str(settings.RESUME_EVIDENCE_ROOT).endswith("user/resume_evidence")
    assert str(settings.RESUME_GENERATION_ROOT).endswith("user/resume_generation")
    assert str(settings.RESUMECR7_LOG_DIR).endswith("user/logs")
    assert str(settings.resume_generation_artifacts_root).endswith(
        "user/resume_generation/artifacts"
    )
    assert settings.generation_config_path.name == "config.yaml"
    assert settings.job_target_path.name == "job_target.yaml"
    assert settings.resume_result_artifact_path.name == "resume_result.json"
    assert settings.resume_run_manifest_artifact_path.name == "resume_run_manifest.json"
    assert settings.resume_tex_artifact_path.name == "resume.tex"
    assert settings.resume_pdf_artifact_path.name == "resume.pdf"
    assert settings.log_file_path.name == "resumecr7.log"


def test_settings_generation_llm_env_overrides(monkeypatch):
    _clear_selection_env(monkeypatch)
    monkeypatch.setenv("BULLETPOINTS_LLM_MODEL", "writer-model")
    monkeypatch.setenv("BULLETPOINTS_LLM_MAX_OUTPUT_TOKENS", "777")
    monkeypatch.setenv("BULLETPOINTS_DEFAULT_COUNT", "4")
    monkeypatch.setenv("LINK_SCANNING_ENABLED", "true")
    monkeypatch.setenv("LINK_SCANNING_LLM_MODEL", "scanner-model")
    monkeypatch.setenv("LINK_SCANNING_LLM_MAX_OUTPUT_TOKENS", "888")
    monkeypatch.setenv("LINK_SCANNING_DEFAULT_HIGHLIGHT_COUNT", "9")
    monkeypatch.setenv("LINK_SCANNING_MAX_TOKENS_PER_HIGHLIGHT", "80")

    settings = Settings(_env_file=None)

    assert settings.BULLETPOINTS_LLM_MODEL == "writer-model"
    assert settings.BULLETPOINTS_LLM_MAX_OUTPUT_TOKENS == 777
    assert settings.BULLETPOINTS_DEFAULT_COUNT == 4
    assert settings.LINK_SCANNING_ENABLED is True
    assert settings.LINK_SCANNING_LLM_MODEL == "scanner-model"
    assert settings.LINK_SCANNING_LLM_MAX_OUTPUT_TOKENS == 888
    assert settings.LINK_SCANNING_DEFAULT_HIGHLIGHT_COUNT == 9
    assert settings.LINK_SCANNING_MAX_TOKENS_PER_HIGHLIGHT == 80


def test_settings_data_dir_derives_runtime_paths(monkeypatch, tmp_path):
    _clear_selection_env(monkeypatch)
    data_dir = tmp_path / "resumecr7-data"
    monkeypatch.setenv("RESUMECR7_DATA_DIR", str(data_dir))

    settings = Settings(_env_file=None)

    assert settings.RESUMECR7_DATA_DIR == data_dir
    assert settings.RESUME_EVIDENCE_ROOT == data_dir / "resume_evidence"
    assert settings.RESUME_GENERATION_ROOT == data_dir / "resume_generation"
    assert settings.RESUMECR7_LOG_DIR == data_dir / "logs"
    assert settings.generation_config_path == data_dir / "resume_generation" / "config.yaml"
    assert settings.resume_generation_artifacts_root == (
        data_dir / "resume_generation" / "artifacts"
    )
    assert settings.resume_tex_artifact_path == (
        data_dir / "resume_generation" / "artifacts" / "resume.tex"
    )
    assert settings.log_file_path == data_dir / "logs" / "resumecr7.log"


def test_settings_preserves_specific_path_overrides(monkeypatch, tmp_path):
    _clear_selection_env(monkeypatch)
    data_dir = tmp_path / "data"
    evidence_root = tmp_path / "evidence"
    generation_root = tmp_path / "generation"
    log_dir = tmp_path / "runtime-logs"
    monkeypatch.setenv("RESUMECR7_DATA_DIR", str(data_dir))
    monkeypatch.setenv("RESUME_EVIDENCE_ROOT", str(evidence_root))
    monkeypatch.setenv("RESUME_GENERATION_ROOT", str(generation_root))
    monkeypatch.setenv("RESUMECR7_LOG_DIR", str(log_dir))

    settings = Settings(_env_file=None)

    assert settings.RESUMECR7_DATA_DIR == data_dir
    assert settings.RESUME_EVIDENCE_ROOT == evidence_root
    assert settings.RESUME_GENERATION_ROOT == generation_root
    assert settings.RESUMECR7_LOG_DIR == log_dir
    assert settings.generation_config_path == generation_root / "config.yaml"
    assert settings.log_file_path == log_dir / "resumecr7.log"


def test_settings_packaged_mode_uses_os_data_dir(monkeypatch, tmp_path):
    _clear_selection_env(monkeypatch)
    monkeypatch.setenv("RESUMECR7_PACKAGED", "true")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg-data"))

    settings = Settings(_env_file=None)

    assert settings.RESUMECR7_PACKAGED is True
    assert settings.RESUMECR7_DATA_DIR == tmp_path / "xdg-data" / "resumecr7"
    assert settings.RESUME_EVIDENCE_ROOT == settings.RESUMECR7_DATA_DIR / "resume_evidence"
    assert settings.resume_generation_artifacts_root == (
        settings.RESUMECR7_DATA_DIR / "resume_generation" / "artifacts"
    )


def test_settings_data_dir_override_wins_in_packaged_mode(monkeypatch, tmp_path):
    _clear_selection_env(monkeypatch)
    data_dir = tmp_path / "explicit-data"
    monkeypatch.setenv("RESUMECR7_PACKAGED", "true")
    monkeypatch.setenv("RESUMECR7_DATA_DIR", str(data_dir))

    settings = Settings(_env_file=None)

    assert settings.RESUMECR7_DATA_DIR == data_dir
    assert settings.RESUME_EVIDENCE_ROOT == data_dir / "resume_evidence"


def test_resolve_default_data_dir_for_supported_packaged_platforms(tmp_path):
    home = tmp_path / "home"

    assert resolve_default_data_dir(
        repo_root=tmp_path / "repo",
        packaged=False,
        platform="linux",
        environ={},
        home=home,
    ) == tmp_path / "repo" / "user"
    assert resolve_default_data_dir(
        repo_root=tmp_path / "repo",
        packaged=True,
        platform="linux",
        environ={},
        home=home,
    ) == home / ".local" / "share" / "resumecr7"
    assert resolve_default_data_dir(
        repo_root=tmp_path / "repo",
        packaged=True,
        platform="darwin",
        environ={},
        home=home,
    ) == home / "Library" / "Application Support" / "ResumeCR7"
    assert resolve_default_data_dir(
        repo_root=tmp_path / "repo",
        packaged=True,
        platform="win32",
        environ={"LOCALAPPDATA": str(tmp_path / "local-app-data")},
        home=home,
    ) == tmp_path / "local-app-data" / "ResumeCR7"


def test_settings_validates_bulletpoints_defaults(monkeypatch):
    _clear_selection_env(monkeypatch)
    monkeypatch.setenv("SKILL_LLM_MAX_OUTPUT_TOKENS", "0")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)

    _clear_selection_env(monkeypatch)
    monkeypatch.setenv("BULLETPOINTS_DEFAULT_COUNT", "0")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)

    _clear_selection_env(monkeypatch)
    monkeypatch.setenv("BULLETPOINTS_LLM_MAX_OUTPUT_TOKENS", "0")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)

    _clear_selection_env(monkeypatch)
    monkeypatch.setenv("LINK_SCANNING_LLM_MAX_OUTPUT_TOKENS", "0")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)

    _clear_selection_env(monkeypatch)
    monkeypatch.setenv("LINK_SCANNING_DEFAULT_HIGHLIGHT_COUNT", "0")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)

    _clear_selection_env(monkeypatch)
    monkeypatch.setenv("LINK_SCANNING_MAX_TOKENS_PER_HIGHLIGHT", "0")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_settings_normalizes_methods(monkeypatch):
    _clear_selection_env(monkeypatch)
    monkeypatch.setenv("SKILL_METHOD", " LLM ")
    monkeypatch.setenv("PROJ_METHOD", "BASELINE")

    settings = Settings(_env_file=None)

    assert settings.SKILL_METHOD == "llm"
    assert settings.PROJ_METHOD == "baseline"


def test_settings_validates_methods(monkeypatch):
    _clear_selection_env(monkeypatch)
    monkeypatch.setenv("SKILL_METHOD", "projector")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)

    _clear_selection_env(monkeypatch)
    monkeypatch.setenv("PROJ_METHOD", "embeddings")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_legacy_selection_env_vars_are_not_honored(monkeypatch):
    _clear_selection_env(monkeypatch)
    monkeypatch.setenv("METHOD", "llm")
    monkeypatch.setenv("TOP_N", "2")
    monkeypatch.setenv("BASELINE_FILTER", "true")
    monkeypatch.setenv("LLM_MODEL", "legacy-model")
    monkeypatch.setenv("LLM_MAX_OUTPUT_TOKENS", "77")

    settings = Settings(_env_file=None)

    assert settings.SKILL_METHOD == "baseline"
    assert settings.SKILL_TOP_N == 10
    assert settings.SKILL_BASELINE_FILTER is False
    assert settings.SKILL_LLM_MODEL == "gpt-5-mini"
    assert settings.PROJ_LLM_MODEL == "gpt-5-mini"
    assert settings.SKILL_LLM_MAX_OUTPUT_TOKENS == 1200
    assert settings.PROJ_LLM_MAX_OUTPUT_TOKENS == 1200
    assert settings.BULLETPOINTS_LLM_MODEL == "gpt-5-mini"
    assert settings.LINK_SCANNING_LLM_MODEL == "gpt-5-mini"
