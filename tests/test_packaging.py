from __future__ import annotations

import os
import tomllib
import importlib
from pathlib import Path

from app import __version__
from app import api_launcher
from app import desktop_backend
from scripts import build_desktop_sidecar

resume_generation_main = importlib.import_module("app.resume_generation.main")


def test_pyproject_exposes_package_metadata():
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["name"] == "resumecr7"
    assert pyproject["project"]["requires-python"] == ">=3.12"
    assert pyproject["tool"]["setuptools"]["dynamic"]["version"] == {
        "attr": "app.__version__",
    }
    assert __version__


def test_pyproject_exposes_expected_console_scripts():
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["scripts"] == {
        "resumecr7-api": "app.api_launcher:main",
        "resumecr7-desktop-backend": "app.desktop_backend:main",
        "resumecr7-resume-evidence": "resume_evidence.cli:main",
        "resumecr7-resume-generation": "app.resume_generation.main:main",
    }


def test_pyproject_exposes_desktop_optional_dependencies():
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    desktop_dependencies = pyproject["project"]["optional-dependencies"]["desktop"]
    assert any(dependency.startswith("pyinstaller") for dependency in desktop_dependencies)


def test_api_launcher_dispatches_uvicorn(monkeypatch):
    calls: list[dict[str, object]] = []

    def fake_run(app_path: str, **kwargs: object) -> None:
        calls.append({"app_path": app_path, **kwargs})

    monkeypatch.setattr("uvicorn.run", fake_run)

    exit_code = api_launcher.main(["--host", "127.0.0.2", "--port", "8765", "--reload"])

    assert exit_code == 0
    assert calls == [
        {
            "app_path": "app.main:app",
            "host": "127.0.0.2",
            "port": 8765,
            "reload": True,
        }
    ]


def test_desktop_backend_launcher_sets_packaged_runtime_environment(monkeypatch, tmp_path):
    calls: list[dict[str, object]] = []

    def fake_run(app_path: str, **kwargs: object) -> None:
        calls.append({"app_path": app_path, **kwargs})

    monkeypatch.delenv("RESUMECR7_PACKAGED", raising=False)
    monkeypatch.delenv("RESUMECR7_DATA_DIR", raising=False)
    monkeypatch.setattr("uvicorn.run", fake_run)

    exit_code = desktop_backend.main(
        [
            "--host",
            "127.0.0.1",
            "--port",
            "43210",
            "--packaged",
            "--data-dir",
            str(tmp_path),
        ]
    )

    assert exit_code == 0
    assert calls == [
        {
            "app_path": "app.main:app",
            "host": "127.0.0.1",
            "port": 43210,
            "reload": False,
            "access_log": False,
        }
    ]
    assert os.environ["RESUMECR7_PACKAGED"] == "true"
    assert os.environ["RESUMECR7_DATA_DIR"] == str(tmp_path)


def test_sidecar_executable_name_includes_target_triple():
    assert (
        build_desktop_sidecar.executable_name(
            "resumecr7-backend",
            "x86_64-unknown-linux-gnu",
        )
        == "resumecr7-backend-x86_64-unknown-linux-gnu"
    )


def test_sidecar_executable_name_uses_windows_extension():
    assert (
        build_desktop_sidecar.executable_name(
            "resumecr7-backend",
            "x86_64-pc-windows-msvc",
        )
        == "resumecr7-backend-x86_64-pc-windows-msvc.exe"
    )


def test_resume_generation_console_script_dispatches_pipeline(monkeypatch):
    calls: list[str] = []

    def fake_run_resume_generation_pipeline():
        calls.append("pipeline")
        return object()

    def fake_write_resume_latex_from_config(resume_result: object):
        assert resume_result is not None
        calls.append("latex")
        return Path("resume.tex")

    def fake_write_resume_pdf_from_config(tex_path: Path):
        assert tex_path == Path("resume.tex")
        calls.append("pdf")
        return None

    monkeypatch.setattr(
        resume_generation_main,
        "run_resume_generation_pipeline",
        fake_run_resume_generation_pipeline,
    )
    monkeypatch.setattr(
        resume_generation_main,
        "write_resume_latex_from_config",
        fake_write_resume_latex_from_config,
    )
    monkeypatch.setattr(
        resume_generation_main,
        "write_resume_pdf_from_config",
        fake_write_resume_pdf_from_config,
    )

    assert resume_generation_main.main([]) == 0
    assert calls == ["pipeline", "latex", "pdf"]
