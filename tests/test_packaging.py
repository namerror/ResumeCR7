from __future__ import annotations

import os
import tomllib
import importlib
from pathlib import Path

import pytest

from app import __version__
from app import api_launcher
from app import desktop_backend
from scripts import build_desktop_sidecar
from scripts import smoke_desktop_sidecar

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


def test_smoke_sidecar_reserves_bindable_loopback_port():
    port = smoke_desktop_sidecar.reserve_loopback_port()

    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((smoke_desktop_sidecar.BACKEND_HOST, port))


def test_smoke_wait_for_health_retries_until_ready(monkeypatch):
    calls: list[str] = []

    def fake_health_check(base_url: str) -> bool:
        calls.append(base_url)
        return len(calls) == 2

    monkeypatch.setattr(smoke_desktop_sidecar, "health_check_once", fake_health_check)
    monkeypatch.setattr(smoke_desktop_sidecar.time, "sleep", lambda _: None)

    smoke_desktop_sidecar.wait_for_health(
        "http://127.0.0.1:43210",
        timeout_seconds=1,
        poll_seconds=0,
    )

    assert calls == ["http://127.0.0.1:43210", "http://127.0.0.1:43210"]


def test_smoke_sidecar_launches_packaged_backend_and_terminates(monkeypatch, tmp_path):
    binary_path = tmp_path / "resumecr7-backend-x86_64-unknown-linux-gnu"
    binary_path.write_text("fake binary", encoding="utf-8")
    processes: list[FakeSidecarProcess] = []
    popen_calls: list[dict[str, object]] = []

    def fake_popen(command, **kwargs):
        process = FakeSidecarProcess()
        processes.append(process)
        popen_calls.append({"command": command, **kwargs})
        return process

    monkeypatch.setattr(smoke_desktop_sidecar.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(smoke_desktop_sidecar, "health_check_once", lambda _: True)

    base_url = smoke_desktop_sidecar.run_sidecar_smoke(
        binary_path,
        data_dir=tmp_path / "runtime-data",
        port=45678,
        timeout_seconds=1,
    )

    assert base_url == "http://127.0.0.1:45678"
    assert processes[0].terminated is True
    assert popen_calls[0]["command"] == [
        str(binary_path),
        "--host",
        "127.0.0.1",
        "--port",
        "45678",
        "--packaged",
        "--data-dir",
        str(tmp_path / "runtime-data"),
    ]
    assert popen_calls[0]["env"]["RESUMECR7_PACKAGED"] == "true"
    assert popen_calls[0]["env"]["RESUMECR7_DATA_DIR"] == str(tmp_path / "runtime-data")


def test_smoke_sidecar_reports_early_process_exit(monkeypatch, tmp_path):
    binary_path = tmp_path / "resumecr7-backend-x86_64-unknown-linux-gnu"
    binary_path.write_text("fake binary", encoding="utf-8")
    process = FakeSidecarProcess(returncode=7, stdout="", stderr="startup failed")

    monkeypatch.setattr(
        smoke_desktop_sidecar.subprocess,
        "Popen",
        lambda *_args, **_kwargs: process,
    )
    monkeypatch.setattr(smoke_desktop_sidecar, "health_check_once", lambda _: False)

    with pytest.raises(RuntimeError, match="startup failed"):
        smoke_desktop_sidecar.run_sidecar_smoke(
            binary_path,
            data_dir=tmp_path / "runtime-data",
            port=45678,
            timeout_seconds=1,
        )

    assert process.terminated is False


class FakeSidecarProcess:
    def __init__(self, *, returncode: int | None = None, stdout: str = "", stderr: str = ""):
        self.returncode = returncode
        self.stdout_text = stdout
        self.stderr_text = stderr
        self.terminated = False
        self.killed = False

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = 0

    def wait(self, timeout=None):
        return self.returncode

    def kill(self):
        self.killed = True
        self.returncode = -9

    def communicate(self, timeout=None):
        return self.stdout_text, self.stderr_text


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
