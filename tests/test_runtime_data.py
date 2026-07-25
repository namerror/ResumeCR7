import yaml

from app.resume_evidence.loader import default_evidence_paths, load_registered_evidence
from app.resume_generation.config import load_generation_config, load_job_target
from app.runtime_data import bootstrap_runtime_data


def _bootstrap(tmp_path):
    data_dir = tmp_path / "resumecr7-data"
    generation_root = data_dir / "resume_generation"
    bootstrap_runtime_data(
        data_dir=data_dir,
        evidence_root=data_dir / "resume_evidence",
        generation_root=generation_root,
        artifacts_root=generation_root / "artifacts",
        log_dir=data_dir / "logs",
    )
    return data_dir


def test_bootstrap_runtime_data_creates_desktop_safe_layout(tmp_path):
    data_dir = _bootstrap(tmp_path)

    assert (data_dir / "resume_evidence").is_dir()
    assert (data_dir / "resume_generation").is_dir()
    assert (data_dir / "resume_generation" / "artifacts").is_dir()
    assert (data_dir / "logs").is_dir()
    assert (data_dir / "resume_evidence" / "user.yaml").is_file()
    assert (data_dir / "resume_generation" / "config.yaml").is_file()
    assert (data_dir / "resume_generation" / "job_target.yaml").is_file()
    assert not list(data_dir.rglob("*.tmp"))


def test_bootstrap_runtime_data_writes_schema_valid_defaults(tmp_path):
    data_dir = _bootstrap(tmp_path)

    evidence = load_registered_evidence(
        default_evidence_paths(data_dir / "resume_evidence")
    )
    config = load_generation_config(data_dir / "resume_generation" / "config.yaml")
    job_target = load_job_target(data_dir / "resume_generation" / "job_target.yaml")

    assert evidence["projects"].projects == []
    assert evidence["experience"].experience == []
    assert evidence["education"].education == []
    assert evidence["skills"].skills.technology == []
    assert evidence["user"].name == "Your Name"
    assert config.schema_version == 1
    assert job_target.title == "Target Job Title"


def test_bootstrap_runtime_data_does_not_overwrite_existing_files(tmp_path):
    data_dir = tmp_path / "resumecr7-data"
    evidence_root = data_dir / "resume_evidence"
    evidence_root.mkdir(parents=True)
    projects_path = evidence_root / "projects.yaml"
    projects_path.write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "projects": [
                    {
                        "id": "existing",
                        "name": "Existing Project",
                        "summary": "Already present.",
                        "highlights": ["Kept during bootstrap."],
                        "active": True,
                        "skills": {
                            "technology": [],
                            "programming": ["Python"],
                            "concepts": [],
                        },
                        "links": None,
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    generation_root = data_dir / "resume_generation"
    bootstrap_runtime_data(
        data_dir=data_dir,
        evidence_root=evidence_root,
        generation_root=generation_root,
        artifacts_root=generation_root / "artifacts",
        log_dir=data_dir / "logs",
    )

    payload = yaml.safe_load(projects_path.read_text(encoding="utf-8"))
    assert payload["projects"][0]["name"] == "Existing Project"
