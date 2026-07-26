import asyncio

import httpx

from app.main import app


def api_request(method: str, path: str, **kwargs):
    async def _request():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.request(method, path, **kwargs)

    return asyncio.run(_request())


# === Health endpoint tests ===

def test_health():
    """Test health endpoint returns OK."""
    res = api_request("GET", "/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert "method" not in data
    assert "top_n" not in data
    assert "baseline_filter" not in data
    assert data["skill_selection"]["method"] == "baseline"
    assert data["skill_selection"]["top_n"] == 10
    assert data["skill_selection"]["baseline_filter"] is False
    assert data["project_selection"]["method"] == "llm"
    assert data["project_selection"]["top_n"] is None
    assert data["project_selection"]["llm_output_token_budget"]["min"] == 1200
    assert data["project_selection"]["llm_output_token_budget"]["max"] is None
    assert data["bulletpoints_generation"]["llm_model"] == "gpt-5-mini"
    assert data["bulletpoints_generation"]["llm_output_token_budget"]["min"] == 1800
    assert data["bulletpoints_generation"]["llm_output_token_budget"]["max"] is None
    assert data["bulletpoints_generation"]["default_count"] == 3
    assert data["job_focus_generation"]["llm_model"] == "gpt-5-mini"
    assert data["job_focus_generation"]["llm_max_output_tokens"] == 1200
    assert data["link_scanning"]["enabled"] is False
    assert data["link_scanning"]["llm_model"] == "gpt-5.6-terra"
    assert data["link_scanning"]["llm_max_output_tokens"] is None
    assert data["link_scanning"]["default_highlight_count"] == 6
    assert data["link_scanning"]["max_tokens_per_highlight"] == 500
    assert data["paths"]["data_dir"].endswith("user")
    assert data["paths"]["resume_evidence_root"].endswith("user/resume_evidence")
    assert data["paths"]["resume_generation_root"].endswith("user/resume_generation")
    assert data["paths"]["log_file"].endswith("user/logs/resumecr7.log")


def test_health_method_not_allowed():
    """Test health endpoint only accepts GET."""
    res = api_request("POST", "/health")
    assert res.status_code == 405


def test_health_allows_tauri_vite_origin():
    """Desktop dev webview can call the sidecar backend directly."""
    res = api_request("GET", "/health", headers={"Origin": "http://127.0.0.1:5173"})
    assert res.status_code == 200
    assert res.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"


# === Select skills endpoint tests ===

def test_select_skills_basic():
    """Test basic select-skills endpoint functionality."""
    payload = {
        "job_role": "backend",
        "technology": ["Python", "Django", "PostgreSQL"],
        "programming": ["Python", "Java"],
        "concepts": ["API", "Microservices"],
    }

    res = api_request("POST", "/select-skills", json=payload)
    assert res.status_code == 200

    data = res.json()
    assert "technology" in data
    assert "programming" in data
    assert "concepts" in data
    assert isinstance(data["technology"], list)
    assert isinstance(data["programming"], list)
    assert isinstance(data["concepts"], list)


def test_select_skills_empty_lists():
    """Test select-skills with empty skill lists."""
    payload = {
        "job_role": "backend",
        "technology": [],
        "programming": [],
        "concepts": [],
    }

    res = api_request("POST", "/select-skills", json=payload)
    assert res.status_code == 200

    data = res.json()
    assert data["technology"] == []
    assert data["programming"] == []
    assert data["concepts"] == []


def test_select_skills_missing_field():
    """Test select-skills with missing required fields."""
    payload = {
        "job_role": "backend",
        "technology": ["Python"],
        # Missing programming and concepts
    }

    res = api_request("POST", "/select-skills", json=payload)
    assert res.status_code == 422  # Unprocessable Entity


def test_select_skills_invalid_types():
    """Test select-skills with invalid data types."""
    payload = {
        "job_role": "backend",
        "technology": "not a list",  # Should be a list
        "programming": ["Python"],
        "concepts": ["API"],
    }

    res = api_request("POST", "/select-skills", json=payload)
    assert res.status_code == 422


def test_select_skills_method_not_allowed():
    """Test select-skills endpoint only accepts POST."""
    res = api_request("GET", "/select-skills")
    assert res.status_code == 405


# === Response validation tests ===

def test_select_skills_response_structure():
    """Test that response matches expected structure."""
    payload = {
        "job_role": "frontend",
        "technology": ["React", "Vue", "Angular"],
        "programming": ["JavaScript", "TypeScript"],
        "concepts": ["UI", "UX"],
    }

    res = api_request("POST", "/select-skills", json=payload)
    assert res.status_code == 200

    data = res.json()
    # Check all required fields are present (details may also appear in dev mode)
    required_fields = {"technology", "programming", "concepts"}
    assert required_fields.issubset(set(data.keys()))


def test_select_skills_maintains_subset():
    """Test that output is a subset of input (no invented skills)."""
    payload = {
        "job_role": "backend",
        "technology": ["Python", "Django", "FastAPI"],
        "programming": ["Python", "Java", "C#"],
        "concepts": ["API", "Database", "Cloud"],
    }

    res = api_request("POST", "/select-skills", json=payload)
    assert res.status_code == 200

    data = res.json()
    # Currently the placeholder just returns all input, but future scorer
    # should only return subsets
    assert set(data["technology"]).issubset(set(payload["technology"]))
    assert set(data["programming"]).issubset(set(payload["programming"]))
    assert set(data["concepts"]).issubset(set(payload["concepts"]))


# === Different role tests ===


    res = api_request("POST", "/select-skills", json=payload)
    assert res.status_code == 200


def test_select_skills_fullstack_role():
    """Test select-skills for fullstack role."""
    payload = {
        "job_role": "fullstack",
        "technology": ["React", "Django", "Docker"],
        "programming": ["Python", "JavaScript"],
        "concepts": ["API", "UI"],
    }

    res = api_request("POST", "/select-skills", json=payload)
    assert res.status_code == 200


def test_select_skills_devops_role():
    """Test select-skills for devops role."""
    payload = {
        "job_role": "devops",
        "technology": ["Docker", "Kubernetes", "AWS", "Terraform"],
        "programming": ["Python", "Bash"],
        "concepts": ["CI/CD", "Infrastructure", "Automation"],
    }

    res = api_request("POST", "/select-skills", json=payload)
    assert res.status_code == 200


def test_select_skills_mlai_role():
    """Test select-skills for ML/AI role."""
    payload = {
        "job_role": "ml/ai",
        "technology": ["TensorFlow", "PyTorch", "Scikit-learn"],
        "programming": ["Python", "C++"],
        "concepts": ["Machine Learning", "Deep Learning", "NLP"],
    }

    res = api_request("POST", "/select-skills", json=payload)
    assert res.status_code == 200
