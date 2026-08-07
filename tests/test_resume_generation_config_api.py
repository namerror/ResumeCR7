from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest
import yaml

from app.config import settings
from app.main import app
from app.resume_generation.config import default_generation_config_payload


def api_request(method: str, path: str, *, base_url: str = "http://testserver", **kwargs):
    async def _request():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url=base_url) as client:
            return await client.request(method, path, **kwargs)

    return asyncio.run(_request())


@pytest.fixture
def generation_root(tmp_path, monkeypatch) -> Path:
    root = tmp_path / "resume_generation"
    root.mkdir()
    monkeypatch.setattr(settings, "RESUME_GENERATION_ROOT", root)
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "")
    monkeypatch.setattr(settings, "RESUMECR7_GITHUB_TOKEN", "")
    monkeypatch.setattr(settings, "GITHUB_TOKEN", "")
    return root


def _write_config(path: Path, payload: dict) -> None:
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def test_resume_generation_config_get_redacts_openai_key(generation_root):
    payload = default_generation_config_payload()
    payload["openai"]["api_key"] = "sk-secret"
    payload["github"]["token"] = "github-secret"
    payload["project_selection"]["top_n"] = None
    _write_config(generation_root / "config.yaml", payload)

    response = api_request("GET", "/resume-generation/config")

    assert response.status_code == 200
    data = response.json()
    assert data["skill_selection"]["top_n"] == 20
    assert data["project_selection"]["top_n"] is None
    assert data["experience_selection"]["top_n"] is None
    assert data["display_defaults"]["project_selection_top_n"] == "unlimited (default)"
    assert data["display_defaults"]["experience_selection_top_n"] == "unlimited (default)"
    assert data["resume_output"] == {
        "output_dir": str(generation_root / "output"),
        "tex_path": str(generation_root / "output" / "resume.tex"),
        "pdf_path": str(generation_root / "output" / "resume.pdf"),
        "artifact_tex_path": str(generation_root / "artifacts" / "resume.tex"),
        "artifact_pdf_path": str(generation_root / "artifacts" / "resume.pdf"),
    }
    assert data["openai_api_key_configured"] is True
    assert data["openai_api_key_saved"] is True
    assert data["openai_api_key_source"] == "config"
    assert data["github_token_configured"] is True
    assert data["github_token_saved"] is True
    assert data["github_token_source"] == "config"
    assert "sk-secret" not in response.text
    assert "github-secret" not in response.text


def test_resume_generation_config_patch_preserves_hidden_yaml_values(generation_root):
    payload = default_generation_config_payload()
    payload["job_focus_generation"]["llm_model"] = "custom-job-focus"
    payload["project_selection"]["llm_output_token_budget"] = {
        "base": 900,
        "per_candidate": 40,
        "per_prompt_1k_chars": 40,
        "min": 1200,
        "max": None,
    }
    payload["project_selection"]["llm_output_token_budget"]["max"] = 5000
    output_dir = generation_root / "final"
    _write_config(generation_root / "config.yaml", payload)

    response = api_request(
        "PATCH",
        "/resume-generation/config",
        json={
            "skill_selection": {"top_n": 12},
            "project_selection": {"top_n": None},
            "experience_selection": {"top_n": 2},
            "link_scanning": {
                "highlight_count": 4,
                "max_tokens_per_highlight": 300,
            },
            "resume_output": {"output_dir": str(output_dir)},
            "bullet_count_range": {"min": 2, "max": 4},
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["skill_selection"]["top_n"] == 12
    assert data["experience_selection"]["top_n"] == 2
    assert data["resume_output"]["output_dir"] == str(output_dir)
    assert data["resume_output"]["tex_path"] == str(output_dir / "resume.tex")
    assert data["resume_output"]["pdf_path"] == str(output_dir / "resume.pdf")
    assert data["bullet_count_range"] == {"min": 2, "max": 4}
    saved = yaml.safe_load((generation_root / "config.yaml").read_text(encoding="utf-8"))
    assert saved["experience_selection"]["top_n"] == 2
    assert saved["job_focus_generation"]["llm_model"] == "custom-job-focus"
    assert saved["project_selection"]["llm_output_token_budget"]["max"] == 5000
    assert saved["project_bullet_point_generation"]["bullet_count_range"] == {
        "min": 2,
        "max": 4,
    }
    assert saved["experience_bullet_point_generation"]["bullet_count_range"] == {
        "min": 2,
        "max": 4,
    }
    assert saved["link_scanning"]["max_tokens_per_highlight"] == 300
    assert saved["resume_output"]["output_dir"] == str(output_dir)


def test_resume_generation_config_patch_rejects_artifact_output_dir(generation_root):
    payload = default_generation_config_payload()
    _write_config(generation_root / "config.yaml", payload)

    response = api_request(
        "PATCH",
        "/resume-generation/config",
        json={
            "resume_output": {
                "output_dir": str(generation_root / "artifacts"),
            },
        },
    )

    assert response.status_code == 400
    assert "outside the internal artifacts directory" in response.text


def test_resume_generation_config_patch_replaces_and_clears_openai_key(generation_root):
    payload = default_generation_config_payload()
    _write_config(generation_root / "config.yaml", payload)

    replace_response = api_request(
        "PATCH",
        "/resume-generation/config",
        json={"openai": {"api_key": "sk-new"}},
    )

    assert replace_response.status_code == 200
    assert "sk-new" not in replace_response.text
    saved = yaml.safe_load((generation_root / "config.yaml").read_text(encoding="utf-8"))
    assert saved["openai"]["api_key"] == "sk-new"

    clear_response = api_request(
        "PATCH",
        "/resume-generation/config",
        json={"openai": {"clear_api_key": True}},
    )

    assert clear_response.status_code == 200
    saved = yaml.safe_load((generation_root / "config.yaml").read_text(encoding="utf-8"))
    assert saved["openai"]["api_key"] is None


def test_resume_generation_config_patch_replaces_and_clears_github_token(generation_root):
    payload = default_generation_config_payload()
    _write_config(generation_root / "config.yaml", payload)

    replace_response = api_request(
        "PATCH",
        "/resume-generation/config",
        json={"github": {"token": "github_pat_new"}},
    )

    assert replace_response.status_code == 200
    assert "github_pat_new" not in replace_response.text
    data = replace_response.json()
    assert data["github_token_configured"] is True
    assert data["github_token_saved"] is True
    assert data["github_token_source"] == "config"
    saved = yaml.safe_load((generation_root / "config.yaml").read_text(encoding="utf-8"))
    assert saved["github"]["token"] == "github_pat_new"

    clear_response = api_request(
        "PATCH",
        "/resume-generation/config",
        json={"github": {"clear_token": True}},
    )

    assert clear_response.status_code == 200
    saved = yaml.safe_load((generation_root / "config.yaml").read_text(encoding="utf-8"))
    assert saved["github"]["token"] is None


def test_resume_generation_config_rejects_api_key_update_over_remote_http(generation_root):
    payload = default_generation_config_payload()
    _write_config(generation_root / "config.yaml", payload)

    response = api_request(
        "PATCH",
        "/resume-generation/config",
        base_url="http://resumecr7.example",
        json={"openai": {"api_key": "sk-new"}},
    )

    assert response.status_code == 403
    assert "HTTPS or a local loopback request" in response.text


def test_resume_generation_config_rejects_github_token_update_over_remote_http(
    generation_root,
):
    payload = default_generation_config_payload()
    _write_config(generation_root / "config.yaml", payload)

    response = api_request(
        "PATCH",
        "/resume-generation/config",
        base_url="http://resumecr7.example",
        json={"github": {"token": "github_pat_new"}},
    )

    assert response.status_code == 403
    assert "HTTPS or a local loopback request" in response.text


def test_resume_generation_job_target_get_reads_saved_yaml(generation_root):
    _write_config(
        generation_root / "job_target.yaml",
        {
            "schema_version": 1,
            "title": "Backend Engineer",
            "description": "Build Python APIs.",
        },
    )

    response = api_request("GET", "/resume-generation/job-target")

    assert response.status_code == 200
    data = response.json()
    assert data == {
        "schema_version": 1,
        "title": "Backend Engineer",
        "description": "Build Python APIs.",
        "job_target_path": str(generation_root / "job_target.yaml"),
    }


def test_resume_generation_job_target_put_persists_yaml(generation_root):
    _write_config(
        generation_root / "job_target.yaml",
        {
            "schema_version": 1,
            "title": "Original Role",
            "description": None,
        },
    )

    response = api_request(
        "PUT",
        "/resume-generation/job-target",
        json={
            "schema_version": 1,
            "title": " Frontend Engineer ",
            "description": " Build React interfaces. ",
        },
    )

    assert response.status_code == 200
    assert response.json()["title"] == "Frontend Engineer"
    assert response.json()["description"] == "Build React interfaces."
    saved = yaml.safe_load((generation_root / "job_target.yaml").read_text(encoding="utf-8"))
    assert saved == {
        "schema_version": 1,
        "title": "Frontend Engineer",
        "description": "Build React interfaces.",
    }


def test_resume_generation_job_target_put_rejects_blank_title_without_writing(
    generation_root,
):
    _write_config(
        generation_root / "job_target.yaml",
        {
            "schema_version": 1,
            "title": "Existing Role",
            "description": "Existing description.",
        },
    )

    response = api_request(
        "PUT",
        "/resume-generation/job-target",
        json={
            "schema_version": 1,
            "title": " ",
            "description": "New description.",
        },
    )

    assert response.status_code == 422
    saved = yaml.safe_load((generation_root / "job_target.yaml").read_text(encoding="utf-8"))
    assert saved == {
        "schema_version": 1,
        "title": "Existing Role",
        "description": "Existing description.",
    }
