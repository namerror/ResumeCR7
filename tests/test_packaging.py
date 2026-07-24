from __future__ import annotations

import tomllib
import importlib
from pathlib import Path

from app import __version__
from app import api_launcher

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
        "resumecr7-resume-evidence": "resume_evidence.cli:main",
        "resumecr7-resume-generation": "app.resume_generation.main:main",
    }


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
