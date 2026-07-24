from __future__ import annotations

from io import StringIO

import pytest
import yaml

from resume_evidence import (
    EducationEvidenceSession,
    ExperienceEvidenceSession,
    ProjectsEvidenceSession,
    SkillsEvidenceSession,
    UserInfoEvidenceSession,
    load_evidence_yaml,
)
from resume_evidence.cli.base import EvidenceCLIBase
from resume_evidence.cli import main as cli_main
from resume_evidence.cli.experience import ExperienceEvidenceCLI
from resume_evidence.cli.projects import ProjectsEvidenceCLI
from resume_evidence.session import generate_experience_id, generate_project_id


def _valid_projects_payload() -> dict:
    return {
        "schema_version": 1,
        "projects": [
            {
                "id": "project-123",
                "name": "ResumeCR7",
                "summary": "Grounded resume tooling for deterministic resume generation.",
                "highlights": [
                    "Built a deterministic baseline skill selector.",
                    "Defined a file-based evidence pipeline for resume generation.",
                ],
                "active": True,
                "skills": {
                    "technology": ["FastAPI", "OpenAI"],
                    "programming": ["Python"],
                    "concepts": ["Deterministic systems", "Schema validation"],
                },
                "links": [
                    "https://github.com/example/resumecr7",
                ],
            }
        ],
    }


def _write_yaml(tmp_path, payload: dict, filename: str = "projects.yaml"):
    path = tmp_path / filename
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def _valid_skills_payload() -> dict:
    return {
        "schema_version": 1,
        "skills": {
            "technology": ["FastAPI"],
            "programming": ["Python"],
            "concepts": ["Schema validation"],
        },
    }


def _valid_education_payload() -> dict:
    return {
        "schema_version": 1,
        "education": [
            {
                "id": "example-university",
                "name": "Example University",
                "degree": "Bachelor of Science in Computer Science",
                "grade": "3.8 GPA",
                "start": "2020",
                "end": "2024",
                "location": "Example City, ST",
                "relevant_coursework": [
                    "Data Structures",
                    "Algorithms",
                    "Software Engineering",
                ],
            }
        ],
    }


def _valid_experience_payload() -> dict:
    return {
        "schema_version": 1,
        "experience": [
            {
                "id": "backend-engineer",
                "name": "Example Company",
                "role": "Backend Engineer",
                "summary": "Built reliable backend services for internal platforms.",
                "highlights": [
                    "Designed schema-validated APIs.",
                    "Improved test coverage for core services.",
                ],
                "active": True,
                "skills": {
                    "technology": ["FastAPI", "PostgreSQL"],
                    "programming": ["Python"],
                    "concepts": ["API", "Data validation"],
                },
                "location": "Example City, ST",
                "start": "2024",
                "end": None,
                "links": ["https://example.com/company"],
            }
        ],
    }


def _valid_user_payload() -> dict:
    return {
        "schema_version": 1,
        "name": "Example Candidate",
        "email": "candidate@example.com",
        "phone": "+1 555-0100",
        "linkedin": "https://www.linkedin.com/in/example-candidate",
        "github": "https://github.com/example-candidate",
        "website": "https://www.example-candidate.com",
    }


class InputFeeder:
    def __init__(self, responses: list[str]):
        self._responses = iter(responses)

    def __call__(self, _prompt: str) -> str:
        try:
            return next(self._responses)
        except StopIteration as exc:
            raise EOFError from exc


def test_comma_skill_parser_preserves_internal_spaces():
    cli = EvidenceCLIBase(output=StringIO())

    parsed = cli._parse_comma_list(
        "Technology skills",
        "FastAPI, Distributed Computing, Docker",
    )

    assert parsed == ["FastAPI", "Distributed Computing", "Docker"]


def test_comma_skill_parser_allows_empty_input_when_optional():
    cli = EvidenceCLIBase(output=StringIO())

    assert cli._parse_comma_list("Technology skills", "   ") == []


@pytest.mark.parametrize("raw_value", ["Python, , SQL", "Python,   , SQL", "Python,"])
def test_comma_skill_parser_rejects_empty_segments(raw_value):
    cli = EvidenceCLIBase(output=StringIO())

    with pytest.raises(ValueError, match="empty comma-separated items"):
        cli._parse_comma_list("Programming skills", raw_value)


def _run_cli(path, responses: list[str]) -> str:
    output = StringIO()
    exit_code = cli_main(["--path", str(path)], input_func=InputFeeder(responses), output=output)
    assert exit_code == 0
    return output.getvalue()


def _run_skills_cli(path, responses: list[str]) -> str:
    output = StringIO()
    exit_code = cli_main(
        ["--schema", "skills", "--path", str(path)],
        input_func=InputFeeder(responses),
        output=output,
    )
    assert exit_code == 0
    return output.getvalue()


def _run_schema_cli(schema: str, path, responses: list[str]) -> str:
    output = StringIO()
    exit_code = cli_main(
        ["--schema", schema, "--path", str(path)],
        input_func=InputFeeder(responses),
        output=output,
    )
    assert exit_code == 0
    return output.getvalue()


class FakePicker:
    def __init__(self, selections: list[int | None]):
        self._selections = iter(selections)
        self.calls: list[tuple[str, list[str]]] = []

    def __call__(self, message: str, labels) -> int | None:
        self.calls.append((message, list(labels)))
        try:
            return next(self._selections)
        except StopIteration:
            return None


class FakeChoicePicker:
    def __init__(self, selections: list[str | None]):
        self._selections = iter(selections)
        self.calls: list[tuple[str, list[tuple[str | None, str]]]] = []

    def __call__(self, message: str, choices) -> str | None:
        self.calls.append((message, list(choices)))
        try:
            return next(self._selections)
        except StopIteration:
            return None


def _run_projects_cli_with_picker(path, responses: list[str], picker: FakePicker) -> str:
    output = StringIO()
    session = ProjectsEvidenceSession.load(path)
    cli = ProjectsEvidenceCLI(
        session,
        input_func=InputFeeder(responses),
        output=output,
        picker=picker,
    )
    assert cli.run() == 0
    return output.getvalue()


def _run_projects_cli_with_action_picker(
    path,
    responses: list[str],
    action_picker: FakeChoicePicker,
    *,
    picker: FakePicker | None = None,
) -> str:
    output = StringIO()
    session = ProjectsEvidenceSession.load(path)
    cli = ProjectsEvidenceCLI(
        session,
        input_func=InputFeeder(responses),
        output=output,
        picker=picker,
        action_picker=action_picker,
    )
    assert cli.run() == 0
    return output.getvalue()


def _run_experience_cli_with_picker(path, responses: list[str], picker: FakePicker) -> str:
    output = StringIO()
    session = ExperienceEvidenceSession.load(path)
    cli = ExperienceEvidenceCLI(
        session,
        input_func=InputFeeder(responses),
        output=output,
        picker=picker,
    )
    assert cli.run() == 0
    return output.getvalue()


def _run_experience_cli_with_action_picker(
    path,
    responses: list[str],
    action_picker: FakeChoicePicker,
    *,
    picker: FakePicker | None = None,
) -> str:
    output = StringIO()
    session = ExperienceEvidenceSession.load(path)
    cli = ExperienceEvidenceCLI(
        session,
        input_func=InputFeeder(responses),
        output=output,
        picker=picker,
        action_picker=action_picker,
    )
    assert cli.run() == 0
    return output.getvalue()


def test_generate_project_id_adds_numeric_suffix_for_duplicates():
    existing_ids = {"resumecr7", "resumecr7-2"}

    assert generate_project_id("ResumeCR7", existing_ids) == "resumecr7-3"


def test_generate_experience_id_adds_numeric_suffix_for_duplicates():
    existing_ids = {"example-company", "example-company-2"}

    assert generate_experience_id("Example Company", existing_ids) == "example-company-3"


def test_session_create_stages_changes_without_writing_file(tmp_path):
    path = _write_yaml(tmp_path, _valid_projects_payload())
    session = ProjectsEvidenceSession.load(path)

    created = session.create_project(
        name="Portfolio Tracker",
        summary="Tracks resume-ready work samples.",
        highlights=["Built CRUD workflows for resume evidence."],
        active=True,
        technology=["FastAPI"],
        programming=["Python"],
        concepts=["CLI design"],
        links=None,
    )

    assert created.id == "portfolio-tracker"
    assert session.dirty is True
    loaded = load_evidence_yaml(path, "projects")
    assert loaded.model_dump()["projects"] == _valid_projects_payload()["projects"]


def test_session_update_keeps_original_id_on_rename(tmp_path):
    path = _write_yaml(tmp_path, _valid_projects_payload())
    session = ProjectsEvidenceSession.load(path)

    updated = session.update_project(
        1,
        name="ResumeCR7 CLI",
        summary="Updated summary",
        highlights=["Built a deterministic baseline skill selector."],
        active=True,
        technology=["FastAPI"],
        programming=["Python"],
        concepts=["Schema validation"],
        links=["https://github.com/example/resumecr7"],
    )

    assert updated.id == "project-123"
    assert updated.name == "ResumeCR7 CLI"


def test_session_delete_removes_project_from_staged_state(tmp_path):
    path = _write_yaml(tmp_path, _valid_projects_payload())
    session = ProjectsEvidenceSession.load(path)

    deleted = session.delete_project(1)

    assert deleted.name == "ResumeCR7"
    assert session.list_projects() == []


def test_session_rejects_invalid_edit_without_mutating_staged_state(tmp_path):
    path = _write_yaml(tmp_path, _valid_projects_payload())
    session = ProjectsEvidenceSession.load(path)
    before = session.staged.model_dump()

    with pytest.raises(ValueError):
        session.update_project(
            1,
            name="ResumeCR7",
            summary="Updated summary",
            highlights=[],
            active=True,
            technology=["FastAPI"],
            programming=["Python"],
            concepts=["Schema validation"],
            links=None,
        )

    assert session.staged.model_dump() == before


def test_session_apply_writes_schema_valid_yaml_and_clears_dirty_flag(tmp_path):
    path = _write_yaml(tmp_path, _valid_projects_payload())
    session = ProjectsEvidenceSession.load(path)

    session.create_project(
        name="Portfolio Tracker",
        summary="Tracks resume-ready work samples.",
        highlights=["Built CRUD workflows for resume evidence."],
        active=True,
        technology=["FastAPI"],
        programming=["Python"],
        concepts=["CLI design"],
        links=["https://example.com/portfolio-tracker"],
    )

    session.apply()

    reloaded = load_evidence_yaml(path, "projects")
    assert reloaded.schema_version == 1
    assert [project.name for project in reloaded.projects] == ["ResumeCR7", "Portfolio Tracker"]
    assert session.dirty is False


def test_skills_session_update_stages_changes_without_writing_file(tmp_path):
    path = _write_yaml(tmp_path, _valid_skills_payload(), filename="skills.yaml")
    session = SkillsEvidenceSession.load(path)

    updated = session.update_skills(
        technology=["FastAPI", "Docker"],
        programming=["Python", "SQL"],
        concepts=["Schema validation", "Deterministic systems"],
    )

    assert updated.skills.technology == ["FastAPI", "Docker"]
    assert session.dirty is True
    loaded = load_evidence_yaml(path, "skills")
    assert loaded.model_dump() == _valid_skills_payload()


def test_skills_session_rejects_invalid_edit_without_mutating_staged_state(tmp_path):
    path = _write_yaml(tmp_path, _valid_skills_payload(), filename="skills.yaml")
    session = SkillsEvidenceSession.load(path)
    before = session.staged.model_dump()

    with pytest.raises(ValueError):
        session.update_skills(
            technology="FastAPI",  # type: ignore[arg-type]
            programming=["Python"],
            concepts=["Schema validation"],
        )

    assert session.staged.model_dump() == before


def test_skills_session_apply_writes_schema_valid_yaml_and_clears_dirty_flag(tmp_path):
    path = _write_yaml(tmp_path, _valid_skills_payload(), filename="skills.yaml")
    session = SkillsEvidenceSession.load(path)

    session.update_skills(
        technology=["FastAPI", "Docker"],
        programming=["Python", "SQL"],
        concepts=["Schema validation"],
    )

    session.apply()

    reloaded = load_evidence_yaml(path, "skills")
    assert reloaded.skills.technology == ["FastAPI", "Docker"]
    assert reloaded.skills.programming == ["Python", "SQL"]
    assert session.dirty is False


def test_skills_session_reload_restores_baseline_state(tmp_path):
    path = _write_yaml(tmp_path, _valid_skills_payload(), filename="skills.yaml")
    session = SkillsEvidenceSession.load(path)

    session.update_skills(
        technology=["Docker"],
        programming=["Go"],
        concepts=["CLI design"],
    )

    session.reload()

    assert session.staged.model_dump() == _valid_skills_payload()


def test_education_session_create_stages_changes_without_writing_file(tmp_path):
    path = _write_yaml(tmp_path, _valid_education_payload(), filename="education.yaml")
    session = EducationEvidenceSession.load(path)

    created = session.create_education(
        name="Example College",
        degree="Master of Science in Software Engineering",
        grade="4.0 GPA",
        start="2025",
        end=None,
        location="Remote",
        relevant_coursework=["Distributed Systems"],
    )

    assert created.name == "Example College"
    assert session.dirty is True
    loaded = load_evidence_yaml(path, "education")
    assert loaded.model_dump() == _valid_education_payload()


def test_education_session_apply_writes_schema_valid_yaml_and_clears_dirty_flag(tmp_path):
    path = _write_yaml(tmp_path, _valid_education_payload(), filename="education.yaml")
    session = EducationEvidenceSession.load(path)

    session.update_education(
        1,
        name="Example University",
        degree="Bachelor of Science in Computer Science",
        grade="3.9 GPA",
        start="2020",
        end="2024",
        location="Example City, ST",
        relevant_coursework=["Data Structures"],
    )
    session.apply()

    reloaded = load_evidence_yaml(path, "education")
    assert reloaded.education[0].grade == "3.9 GPA"
    assert session.dirty is False


def test_education_session_rejects_invalid_edit_without_mutating_staged_state(tmp_path):
    path = _write_yaml(tmp_path, _valid_education_payload(), filename="education.yaml")
    session = EducationEvidenceSession.load(path)
    before = session.staged.model_dump()

    with pytest.raises(ValueError):
        session.update_education(
            1,
            name="Example University",
            degree="Bachelor of Science in Computer Science",
            grade="3.8 GPA",
            start="2020",
            end="2024",
            location="Example City, ST",
            relevant_coursework="Algorithms",  # type: ignore[arg-type]
        )

    assert session.staged.model_dump() == before


def test_experience_session_create_stages_changes_without_writing_file(tmp_path):
    path = _write_yaml(tmp_path, _valid_experience_payload(), filename="experience.yaml")
    session = ExperienceEvidenceSession.load(path)

    created = session.create_experience(
        name="Example Company",
        role="Platform Engineer",
        summary="Built platform tools.",
        highlights=["Shipped internal tools."],
        active=True,
        technology=["FastAPI"],
        programming=["Python"],
        concepts=["APIs"],
        location="Remote",
        start="2025",
        end=None,
        links=None,
    )

    assert created.id == "example-company"
    assert created.role == "Platform Engineer"
    assert session.dirty is True
    loaded = load_evidence_yaml(path, "experience")
    assert loaded.model_dump() == _valid_experience_payload()


def test_experience_session_update_keeps_original_id_on_rename(tmp_path):
    path = _write_yaml(tmp_path, _valid_experience_payload(), filename="experience.yaml")
    session = ExperienceEvidenceSession.load(path)

    updated = session.update_experience(
        1,
        name="Renamed Company",
        role="Senior Backend Engineer",
        summary="Updated summary",
        highlights=["Designed schema-validated APIs."],
        active=True,
        technology=["FastAPI"],
        programming=["Python"],
        concepts=["API"],
        location="Example City, ST",
        start="2024",
        end=None,
        links=None,
    )

    assert updated.id == "backend-engineer"
    assert updated.name == "Renamed Company"
    assert updated.role == "Senior Backend Engineer"


def test_experience_session_apply_writes_schema_valid_yaml_and_clears_dirty_flag(tmp_path):
    path = _write_yaml(tmp_path, _valid_experience_payload(), filename="experience.yaml")
    session = ExperienceEvidenceSession.load(path)

    session.delete_experience(1)
    session.apply()

    reloaded = load_evidence_yaml(path, "experience")
    assert reloaded.experience == []
    assert session.dirty is False


def test_user_info_session_update_stages_changes_without_writing_file(tmp_path):
    path = _write_yaml(tmp_path, _valid_user_payload(), filename="user.yaml")
    session = UserInfoEvidenceSession.load(path)

    updated = session.update_user_info(
        name="Updated Candidate",
        email="candidate@example.com",
        phone="+1 555-0100",
        linkedin="https://www.linkedin.com/in/example-candidate",
        github="https://github.com/example-candidate",
        website=None,
    )

    assert updated.name == "Updated Candidate"
    assert updated.website is None
    assert session.dirty is True
    loaded = load_evidence_yaml(path, "user")
    assert loaded.model_dump() == _valid_user_payload()


def test_user_info_session_apply_writes_schema_valid_yaml_and_clears_dirty_flag(tmp_path):
    path = _write_yaml(tmp_path, _valid_user_payload(), filename="user.yaml")
    session = UserInfoEvidenceSession.load(path)

    session.update_user_info(
        name="Updated Candidate",
        email="updated@example.com",
        phone="+1 555-0199",
        linkedin=None,
        github=None,
        website=None,
    )
    session.apply()

    reloaded = load_evidence_yaml(path, "user")
    assert reloaded.email == "updated@example.com"
    assert reloaded.linkedin is None
    assert session.dirty is False


def test_user_info_session_rejects_invalid_edit_without_mutating_staged_state(tmp_path):
    path = _write_yaml(tmp_path, _valid_user_payload(), filename="user.yaml")
    session = UserInfoEvidenceSession.load(path)
    before = session.staged.model_dump()

    with pytest.raises(ValueError):
        session.update_user_info(
            name=" ",
            email="candidate@example.com",
            phone="+1 555-0100",
            linkedin=None,
            github=None,
            website=None,
        )

    assert session.staged.model_dump() == before


def test_cli_list_shows_numbered_projects(tmp_path):
    path = _write_yaml(tmp_path, _valid_projects_payload())

    output = _run_cli(path, ["list", "quit"])

    assert "1. ResumeCR7 [active]" in output


def test_projects_cli_action_menu_lists_projects_at_startup(tmp_path):
    path = _write_yaml(tmp_path, _valid_projects_payload())
    action_picker = FakeChoicePicker([None])

    output = _run_projects_cli_with_action_picker(path, ["quit"], action_picker)

    assert "1. ResumeCR7 [active]" in output
    assert action_picker.calls == [
        (
            "Choose project action",
            [
                ("list", "list"),
                ("show", "show"),
                ("edit", "edit"),
                ("create", "create"),
                ("delete", "delete"),
                ("apply", "apply"),
                ("reload", "reload"),
                ("quit", "quit"),
            ],
        )
    ]


def test_projects_cli_action_menu_list_matches_list_command(tmp_path):
    path = _write_yaml(tmp_path, _valid_projects_payload())
    action_picker = FakeChoicePicker(["list", "quit"])

    output = _run_projects_cli_with_action_picker(path, [], action_picker)

    assert output.count("1. ResumeCR7 [active]") >= 2
    assert output.endswith("Goodbye.\n")


def test_projects_cli_action_menu_show_matches_show_command(tmp_path):
    path = _write_yaml(tmp_path, _valid_projects_payload())
    action_picker = FakeChoicePicker(["show", "quit"])
    project_picker = FakePicker([1])

    output = _run_projects_cli_with_action_picker(
        path,
        [],
        action_picker,
        picker=project_picker,
    )

    assert project_picker.calls == [("Choose a project to show", ["1. ResumeCR7 [active]"])]
    assert "Summary: Grounded resume tooling for deterministic resume generation." in output


def test_projects_cli_action_menu_edit_matches_edit_command(tmp_path):
    path = _write_yaml(tmp_path, _valid_projects_payload())
    action_picker = FakeChoicePicker(["edit", None])
    project_picker = FakePicker([1])

    output = _run_projects_cli_with_action_picker(
        path,
        [
            "",
            "Updated from action menu",
            "y",
            "",
            "",
            "",
            "",
            "y",
            "quit",
            "y",
        ],
        action_picker,
        picker=project_picker,
    )

    loaded = load_evidence_yaml(path, "projects")
    assert project_picker.calls == [("Choose a project to edit", ["1. ResumeCR7 [active]"])]
    assert loaded.model_dump() == _valid_projects_payload()
    assert "Staged updates for 'ResumeCR7'. Run 'apply' to save." in output


def test_projects_cli_action_menu_apply_saves_after_menu_edit(tmp_path):
    path = _write_yaml(tmp_path, _valid_projects_payload())
    action_picker = FakeChoicePicker(["edit", "apply", "quit"])
    project_picker = FakePicker([1])

    output = _run_projects_cli_with_action_picker(
        path,
        [
            "",
            "Updated and saved from action menu",
            "y",
            "",
            "",
            "",
            "",
            "y",
            "y",
        ],
        action_picker,
        picker=project_picker,
    )

    loaded = load_evidence_yaml(path, "projects")
    assert loaded.projects[0].summary == "Updated and saved from action menu"
    assert "Staged updates for 'ResumeCR7'. Run 'apply' to save." in output
    assert f"Saved staged changes to {path}" in output


def test_projects_cli_action_menu_create_matches_create_command(tmp_path):
    path = _write_yaml(tmp_path, _valid_projects_payload())
    action_picker = FakeChoicePicker(["create", None])

    output = _run_projects_cli_with_action_picker(
        path,
        [
            "Portfolio Tracker",
            "Tracks resume-ready work samples.",
            "Built CRUD workflows for resume evidence.",
            "",
            "",
            "FastAPI",
            "Python",
            "CLI design",
            "",
            "quit",
            "y",
        ],
        action_picker,
    )

    loaded = load_evidence_yaml(path, "projects")
    assert [project.name for project in loaded.projects] == ["ResumeCR7"]
    assert "Staged new project 'Portfolio Tracker'. Run 'apply' to save." in output


def test_projects_cli_action_menu_delete_matches_delete_command(tmp_path):
    path = _write_yaml(tmp_path, _valid_projects_payload())
    action_picker = FakeChoicePicker(["delete", None])
    project_picker = FakePicker([1])

    output = _run_projects_cli_with_action_picker(
        path,
        ["y", "quit", "y"],
        action_picker,
        picker=project_picker,
    )

    loaded = load_evidence_yaml(path, "projects")
    assert project_picker.calls == [("Choose a project to delete", ["1. ResumeCR7 [active]"])]
    assert loaded.model_dump() == _valid_projects_payload()
    assert "Staged deletion for 'ResumeCR7'. Run 'apply' to save." in output


def test_projects_cli_action_menu_quit_uses_existing_dirty_confirmation(tmp_path):
    path = _write_yaml(tmp_path, _valid_projects_payload())
    action_picker = FakeChoicePicker(["create", "quit", None])

    output = _run_projects_cli_with_action_picker(
        path,
        [
            "Portfolio Tracker",
            "Tracks resume-ready work samples.",
            "Built CRUD workflows for resume evidence.",
            "",
            "",
            "",
            "",
            "",
            "",
            "n",
            "quit",
            "y",
        ],
        action_picker,
    )

    loaded = load_evidence_yaml(path, "projects")
    assert [project.name for project in loaded.projects] == ["ResumeCR7"]
    assert "Quit canceled." in output
    assert output.endswith("Goodbye.\n")


def test_projects_cli_action_menu_reload_matches_reload_command(tmp_path):
    path = _write_yaml(tmp_path, _valid_projects_payload())
    action_picker = FakeChoicePicker(["create", "reload", "quit"])

    output = _run_projects_cli_with_action_picker(
        path,
        [
            "Portfolio Tracker",
            "Tracks resume-ready work samples.",
            "Built CRUD workflows for resume evidence.",
            "",
            "",
            "",
            "",
            "",
            "",
            "y",
        ],
        action_picker,
    )

    loaded = load_evidence_yaml(path, "projects")
    assert [project.name for project in loaded.projects] == ["ResumeCR7"]
    assert "Reloaded projects evidence from disk." in output


def test_projects_cli_action_menu_cancellation_returns_to_typed_prompt(tmp_path):
    path = _write_yaml(tmp_path, _valid_projects_payload())
    action_picker = FakeChoicePicker([None, None])

    output = _run_projects_cli_with_action_picker(path, ["list", "quit"], action_picker)

    loaded = load_evidence_yaml(path, "projects")
    assert loaded.model_dump() == _valid_projects_payload()
    assert output.count("1. ResumeCR7 [active]") >= 2
    assert output.endswith("Goodbye.\n")


def test_projects_cli_without_action_picker_still_accepts_typed_commands(tmp_path):
    path = _write_yaml(tmp_path, _valid_projects_payload())

    output = _run_cli(path, ["list", "quit"])

    assert "1. ResumeCR7 [active]" in output
    assert output.endswith("Goodbye.\n")


def test_cli_show_without_index_uses_project_picker(tmp_path):
    path = _write_yaml(tmp_path, _valid_projects_payload())
    picker = FakePicker([1])

    output = _run_projects_cli_with_picker(path, ["show", "quit"], picker)

    assert picker.calls == [
        ("Choose a project to show", ["1. ResumeCR7 [active]"]),
    ]
    assert "Summary: Grounded resume tooling for deterministic resume generation." in output


def test_cli_edit_without_index_uses_project_picker(tmp_path):
    path = _write_yaml(tmp_path, _valid_projects_payload())
    picker = FakePicker([1])

    _run_projects_cli_with_picker(
        path,
        [
            "edit",
            "",
            "Updated from picker",
            "y",
            "",
            "",
            "",
            "",
            "y",
            "apply",
            "y",
            "quit",
        ],
        picker,
    )

    loaded = load_evidence_yaml(path, "projects")
    assert picker.calls[0] == ("Choose a project to edit", ["1. ResumeCR7 [active]"])
    assert loaded.projects[0].summary == "Updated from picker"


def test_cli_delete_without_index_uses_project_picker(tmp_path):
    path = _write_yaml(tmp_path, _valid_projects_payload())
    picker = FakePicker([1])

    _run_projects_cli_with_picker(
        path,
        ["delete", "y", "apply", "y", "quit"],
        picker,
    )

    loaded = load_evidence_yaml(path, "projects")
    assert picker.calls == [
        ("Choose a project to delete", ["1. ResumeCR7 [active]"]),
    ]
    assert loaded.projects == []


def test_cli_project_picker_cancellation_leaves_staged_data_unchanged(tmp_path):
    path = _write_yaml(tmp_path, _valid_projects_payload())
    picker = FakePicker([None])

    output = _run_projects_cli_with_picker(path, ["edit", "quit"], picker)

    loaded = load_evidence_yaml(path, "projects")
    assert loaded.model_dump() == _valid_projects_payload()
    assert "No project selected. Use 'edit <index>' to choose directly." in output


def test_cli_project_picker_unavailable_falls_back_to_index_guidance(tmp_path):
    path = _write_yaml(tmp_path, _valid_projects_payload())

    output = _run_cli(path, ["delete", "quit"])

    loaded = load_evidence_yaml(path, "projects")
    assert loaded.model_dump() == _valid_projects_payload()
    assert "No project selected. Use 'delete <index>' to choose directly." in output


def test_cli_create_stages_changes_without_persisting_before_apply(tmp_path):
    path = _write_yaml(tmp_path, _valid_projects_payload())

    output = _run_cli(
        path,
        [
            "create",
            "Portfolio Tracker",
            "Tracks resume-ready work samples.",
            "Built CRUD workflows for resume evidence.",
            "",
            "",
            "FastAPI",
            "",
            "",
            "",
            "",
            "quit",
            "y",
        ],
    )

    loaded = load_evidence_yaml(path, "projects")
    assert [project.name for project in loaded.projects] == ["ResumeCR7"]
    assert "Run 'apply' to save." in output


def test_cli_edit_updates_project_after_apply_and_keeps_id_hidden(tmp_path):
    path = _write_yaml(tmp_path, _valid_projects_payload())

    output = _run_cli(
        path,
        [
            "edit 1",
            "",
            "Updated summary",
            "y",
            "",
            "FastAPI, Distributed Computing",
            "",
            "",
            "y",
            "apply",
            "y",
            "show 1",
            "quit",
        ],
    )

    loaded = load_evidence_yaml(path, "projects")
    assert loaded.projects[0].summary == "Updated summary"
    assert loaded.projects[0].highlights == _valid_projects_payload()["projects"][0]["highlights"]
    assert loaded.projects[0].skills.technology == ["FastAPI", "Distributed Computing"]
    assert loaded.projects[0].id == "project-123"
    assert "project-123" not in output


def test_cli_edit_updates_highlight_by_temporary_index(tmp_path):
    path = _write_yaml(tmp_path, _valid_projects_payload())

    _run_cli(
        path,
        [
            "edit 1",
            "",
            "",
            "n",
            "edit 2",
            "Defined a file-based evidence pipeline, with indexed editing.",
            "done",
            "",
            "",
            "",
            "",
            "y",
            "apply",
            "y",
            "quit",
        ],
    )

    loaded = load_evidence_yaml(path, "projects")
    assert loaded.projects[0].highlights == [
        "Built a deterministic baseline skill selector.",
        "Defined a file-based evidence pipeline, with indexed editing.",
    ]


def test_cli_edit_highlight_without_index_uses_picker(tmp_path):
    path = _write_yaml(tmp_path, _valid_projects_payload())
    picker = FakePicker([2])

    _run_projects_cli_with_picker(
        path,
        [
            "edit 1",
            "",
            "",
            "n",
            "edit",
            "Defined a file-based evidence pipeline, with picker editing.",
            "done",
            "",
            "",
            "",
            "",
            "y",
            "apply",
            "y",
            "quit",
        ],
        picker,
    )

    loaded = load_evidence_yaml(path, "projects")
    assert picker.calls == [
        (
            "Choose a highlight to edit",
            [
                "1. Built a deterministic baseline skill selector.",
                "2. Defined a file-based evidence pipeline for resume generation.",
            ],
        )
    ]
    assert loaded.projects[0].highlights == [
        "Built a deterministic baseline skill selector.",
        "Defined a file-based evidence pipeline, with picker editing.",
    ]


def test_cli_edit_can_add_and_delete_highlights_by_temporary_index(tmp_path):
    path = _write_yaml(tmp_path, _valid_projects_payload())

    _run_cli(
        path,
        [
            "edit 1",
            "",
            "",
            "n",
            "add",
            "Added a nested editor, preserving commas in highlight text.",
            "delete 1",
            "done",
            "",
            "",
            "",
            "",
            "y",
            "apply",
            "y",
            "quit",
        ],
    )

    loaded = load_evidence_yaml(path, "projects")
    assert loaded.projects[0].highlights == [
        "Defined a file-based evidence pipeline for resume generation.",
        "Added a nested editor, preserving commas in highlight text.",
    ]


def test_cli_delete_highlight_without_index_uses_picker(tmp_path):
    path = _write_yaml(tmp_path, _valid_projects_payload())
    picker = FakePicker([1])

    _run_projects_cli_with_picker(
        path,
        [
            "edit 1",
            "",
            "",
            "n",
            "delete",
            "done",
            "",
            "",
            "",
            "",
            "y",
            "apply",
            "y",
            "quit",
        ],
        picker,
    )

    loaded = load_evidence_yaml(path, "projects")
    assert picker.calls[0][0] == "Choose a highlight to delete"
    assert loaded.projects[0].highlights == [
        "Defined a file-based evidence pipeline for resume generation.",
    ]


def test_cli_edit_rejects_deleting_final_highlight(tmp_path):
    payload = _valid_projects_payload()
    payload["projects"][0]["highlights"] = ["Only highlight."]
    path = _write_yaml(tmp_path, payload)

    output = _run_cli(
        path,
        [
            "edit 1",
            "",
            "",
            "n",
            "delete 1",
            "done",
            "",
            "",
            "",
            "",
            "y",
            "quit",
        ],
    )

    loaded = load_evidence_yaml(path, "projects")
    assert loaded.projects[0].highlights == ["Only highlight."]
    assert "Error: At least one highlight is required." in output


def test_cli_edit_highlight_invalid_commands_do_not_mutate_staged_data(tmp_path):
    path = _write_yaml(tmp_path, _valid_projects_payload())

    output = _run_cli(
        path,
        [
            "edit 1",
            "",
            "",
            "n",
            "wat",
            "edit 99",
            "delete nope",
            "done",
            "",
            "",
            "",
            "",
            "y",
            "quit",
        ],
    )

    loaded = load_evidence_yaml(path, "projects")
    assert loaded.projects[0].highlights == _valid_projects_payload()["projects"][0]["highlights"]
    assert "Error: Unknown highlights command 'wat'" in output
    assert "Error: Highlight index 99 is out of range" in output
    assert "Error: Highlight index must be an integer for 'delete'" in output


def test_cli_apply_requires_confirmation_before_writing(tmp_path):
    path = _write_yaml(tmp_path, _valid_projects_payload())

    output = _run_cli(
        path,
        [
            "create",
            "Portfolio Tracker",
            "Tracks resume-ready work samples.",
            "Built CRUD workflows for resume evidence.",
            "",
            "",
            "",
            "",
            "",
            "",
            "apply",
            "n",
            "quit",
            "y",
        ],
    )

    loaded = load_evidence_yaml(path, "projects")
    assert [project.name for project in loaded.projects] == ["ResumeCR7"]
    assert "Apply canceled." in output


def test_cli_reload_discards_dirty_changes_only_after_confirmation(tmp_path):
    path = _write_yaml(tmp_path, _valid_projects_payload())

    output = _run_cli(
        path,
        [
            "create",
            "Portfolio Tracker",
            "Tracks resume-ready work samples.",
            "Built CRUD workflows for resume evidence.",
            "",
            "",
            "",
            "",
            "",
            "",
            "reload",
            "y",
            "list",
            "quit",
        ],
    )

    loaded = load_evidence_yaml(path, "projects")
    assert [project.name for project in loaded.projects] == ["ResumeCR7"]
    assert "Portfolio Tracker" not in output.split("Reloaded projects evidence from disk.")[-1]


def test_cli_quit_warns_about_unapplied_changes(tmp_path):
    path = _write_yaml(tmp_path, _valid_projects_payload())

    output = _run_cli(
        path,
        [
            "create",
            "Portfolio Tracker",
            "Tracks resume-ready work samples.",
            "Built CRUD workflows for resume evidence.",
            "",
            "",
            "",
            "",
            "",
            "",
            "quit",
            "n",
            "quit",
            "y",
        ],
    )

    assert "Quit canceled." in output


def test_skills_cli_list_shows_category_buckets(tmp_path):
    path = _write_yaml(tmp_path, _valid_skills_payload(), filename="skills.yaml")

    output = _run_skills_cli(path, ["list", "quit"])

    assert "Technology: FastAPI" in output
    assert "Programming: Python" in output
    assert "Concepts: Schema validation" in output


def test_skills_cli_edit_keeps_existing_skills_on_blank_input(tmp_path):
    path = _write_yaml(tmp_path, _valid_skills_payload(), filename="skills.yaml")

    _run_skills_cli(path, ["edit", "", "", "", "list", "quit"])

    loaded = load_evidence_yaml(path, "skills")
    assert loaded.skills.technology == ["FastAPI"]
    assert loaded.skills.programming == ["Python"]
    assert loaded.skills.concepts == ["Schema validation"]


def test_skills_cli_edit_updates_after_apply(tmp_path):
    path = _write_yaml(tmp_path, _valid_skills_payload(), filename="skills.yaml")

    output = _run_skills_cli(
        path,
        [
            "edit",
            "FastAPI, Docker",
            "Python, SQL",
            "",
            "apply",
            "y",
            "list",
            "quit",
        ],
    )

    loaded = load_evidence_yaml(path, "skills")
    assert loaded.skills.technology == ["FastAPI", "Docker"]
    assert loaded.skills.programming == ["Python", "SQL"]
    assert "Technology: FastAPI, Docker" in output


def test_skills_cli_apply_requires_confirmation_before_writing(tmp_path):
    path = _write_yaml(tmp_path, _valid_skills_payload(), filename="skills.yaml")

    output = _run_skills_cli(
        path,
        [
            "edit",
            "",
            "Python, SQL",
            "",
            "apply",
            "n",
            "quit",
            "y",
        ],
    )

    loaded = load_evidence_yaml(path, "skills")
    assert loaded.skills.programming == ["Python"]
    assert "Apply canceled." in output


def test_skills_cli_reload_discards_dirty_changes_only_after_confirmation(tmp_path):
    path = _write_yaml(tmp_path, _valid_skills_payload(), filename="skills.yaml")

    output = _run_skills_cli(
        path,
        [
            "edit",
            "Docker",
            "",
            "",
            "reload",
            "y",
            "list",
            "quit",
        ],
    )

    loaded = load_evidence_yaml(path, "skills")
    assert loaded.skills.technology == ["FastAPI"]
    assert "Reloaded skills evidence from disk." in output
    assert "Technology: FastAPI" in output.split("Reloaded skills evidence from disk.")[-1]


def test_skills_cli_quit_warns_about_unapplied_changes(tmp_path):
    path = _write_yaml(tmp_path, _valid_skills_payload(), filename="skills.yaml")

    output = _run_skills_cli(
        path,
        [
            "edit",
            "Docker",
            "",
            "",
            "quit",
            "n",
            "quit",
            "y",
        ],
    )

    assert "Quit canceled." in output


def test_cli_help_includes_all_resume_evidence_schemas():
    parser = cli_main.__globals__["build_arg_parser"]()

    help_text = parser.format_help()

    assert "education" in help_text
    assert "experience" in help_text
    assert "projects" in help_text
    assert "skills" in help_text
    assert "user" in help_text


def test_education_cli_list_and_show(tmp_path):
    path = _write_yaml(tmp_path, _valid_education_payload(), filename="education.yaml")

    output = _run_schema_cli("education", path, ["list", "show 1", "quit"])

    assert "1. Example University - Bachelor of Science in Computer Science" in output
    assert "Relevant coursework: Data Structures, Algorithms, Software Engineering" in output


def test_education_cli_create_edit_delete_and_apply(tmp_path):
    path = _write_yaml(tmp_path, _valid_education_payload(), filename="education.yaml")

    output = _run_schema_cli(
        "education",
        path,
        [
            "create",
            "Example College",
            "Master of Science in Software Engineering",
            "4.0 GPA",
            "2025",
            "",
            "Remote",
            "Distributed Systems",
            "",
            "edit 1",
            "",
            "",
            "3.9 GPA",
            "",
            "y",
            "",
            "y",
            "delete 2",
            "y",
            "apply",
            "y",
            "quit",
        ],
    )

    loaded = load_evidence_yaml(path, "education")
    assert loaded.education[0].grade == "3.9 GPA"
    assert len(loaded.education) == 1
    assert "Staged new education entry 'Example College'. Run 'apply' to save." in output
    assert "Staged deletion for 'Example College'. Run 'apply' to save." in output


def test_education_cli_reload_discards_dirty_changes_only_after_confirmation(tmp_path):
    path = _write_yaml(tmp_path, _valid_education_payload(), filename="education.yaml")

    output = _run_schema_cli(
        "education",
        path,
        [
            "delete 1",
            "y",
            "reload",
            "y",
            "list",
            "quit",
        ],
    )

    loaded = load_evidence_yaml(path, "education")
    assert len(loaded.education) == 1
    assert "Reloaded education evidence from disk." in output
    assert "1. Example University" in output.split("Reloaded education evidence from disk.")[-1]


def test_education_cli_quit_warns_about_unapplied_changes(tmp_path):
    path = _write_yaml(tmp_path, _valid_education_payload(), filename="education.yaml")

    output = _run_schema_cli(
        "education",
        path,
        [
            "delete 1",
            "y",
            "quit",
            "n",
            "quit",
            "y",
        ],
    )

    assert "Quit canceled." in output


def test_experience_cli_list_and_show(tmp_path):
    path = _write_yaml(tmp_path, _valid_experience_payload(), filename="experience.yaml")

    output = _run_schema_cli("experience", path, ["list", "show 1", "quit"])

    assert "1. Example Company [active]" in output
    assert "Role: Backend Engineer" in output
    assert "Location: Example City, ST" in output
    assert "Technology: FastAPI, PostgreSQL" in output


def test_experience_cli_action_menu_show_uses_entry_picker(tmp_path):
    path = _write_yaml(tmp_path, _valid_experience_payload(), filename="experience.yaml")
    action_picker = FakeChoicePicker(["show", "quit"])
    picker = FakePicker([1])

    output = _run_experience_cli_with_action_picker(path, [], action_picker, picker=picker)

    assert action_picker.calls[0][0] == "Choose experience action"
    assert picker.calls == [
        ("Choose an experience entry to show", ["1. Example Company [active]"]),
    ]
    assert "Role: Backend Engineer" in output


def test_experience_cli_action_menu_cancellation_returns_to_typed_prompt(tmp_path):
    path = _write_yaml(tmp_path, _valid_experience_payload(), filename="experience.yaml")
    action_picker = FakeChoicePicker([None, None])

    output = _run_experience_cli_with_action_picker(path, ["list", "quit"], action_picker)

    loaded = load_evidence_yaml(path, "experience")
    assert loaded.model_dump() == _valid_experience_payload()
    assert output.count("1. Example Company [active]") >= 2
    assert output.endswith("Goodbye.\n")


def test_experience_cli_show_without_index_uses_picker(tmp_path):
    path = _write_yaml(tmp_path, _valid_experience_payload(), filename="experience.yaml")
    picker = FakePicker([1])

    output = _run_experience_cli_with_picker(path, ["show", "quit"], picker)

    assert picker.calls == [
        ("Choose an experience entry to show", ["1. Example Company [active]"]),
    ]
    assert "Summary: Built reliable backend services for internal platforms." in output


def test_experience_cli_edit_without_index_uses_picker(tmp_path):
    path = _write_yaml(tmp_path, _valid_experience_payload(), filename="experience.yaml")
    picker = FakePicker([1])

    _run_experience_cli_with_picker(
        path,
        [
            "edit",
            "",
            "",
            "Updated from picker.",
            "y",
            "",
            "",
            "",
            "",
            "",
            "",
            "y",
            "y",
            "apply",
            "y",
            "quit",
        ],
        picker,
    )

    loaded = load_evidence_yaml(path, "experience")
    assert picker.calls[0] == (
        "Choose an experience entry to edit",
        ["1. Example Company [active]"],
    )
    assert loaded.experience[0].summary == "Updated from picker."


def test_experience_cli_delete_without_index_uses_picker(tmp_path):
    path = _write_yaml(tmp_path, _valid_experience_payload(), filename="experience.yaml")
    picker = FakePicker([1])

    _run_experience_cli_with_picker(
        path,
        ["delete", "y", "apply", "y", "quit"],
        picker,
    )

    loaded = load_evidence_yaml(path, "experience")
    assert picker.calls == [
        ("Choose an experience entry to delete", ["1. Example Company [active]"]),
    ]
    assert loaded.experience == []


def test_experience_cli_edit_updates_highlight_by_temporary_index(tmp_path):
    path = _write_yaml(tmp_path, _valid_experience_payload(), filename="experience.yaml")

    _run_schema_cli(
        "experience",
        path,
        [
            "edit 1",
            "",
            "",
            "",
            "n",
            "edit 2",
            "Improved test coverage, with indexed editing.",
            "done",
            "",
            "",
            "",
            "",
            "",
            "",
            "y",
            "y",
            "apply",
            "y",
            "quit",
        ],
    )

    loaded = load_evidence_yaml(path, "experience")
    assert loaded.experience[0].highlights == [
        "Designed schema-validated APIs.",
        "Improved test coverage, with indexed editing.",
    ]


def test_experience_cli_edit_highlight_without_index_uses_picker(tmp_path):
    path = _write_yaml(tmp_path, _valid_experience_payload(), filename="experience.yaml")
    picker = FakePicker([2])

    _run_experience_cli_with_picker(
        path,
        [
            "edit 1",
            "",
            "",
            "",
            "n",
            "edit",
            "Improved test coverage, with picker editing.",
            "done",
            "",
            "",
            "",
            "",
            "",
            "",
            "y",
            "y",
            "apply",
            "y",
            "quit",
        ],
        picker,
    )

    loaded = load_evidence_yaml(path, "experience")
    assert picker.calls == [
        (
            "Choose a highlight to edit",
            [
                "1. Designed schema-validated APIs.",
                "2. Improved test coverage for core services.",
            ],
        )
    ]
    assert loaded.experience[0].highlights == [
        "Designed schema-validated APIs.",
        "Improved test coverage, with picker editing.",
    ]


def test_experience_cli_edit_can_add_and_delete_highlights_by_temporary_index(tmp_path):
    path = _write_yaml(tmp_path, _valid_experience_payload(), filename="experience.yaml")

    _run_schema_cli(
        "experience",
        path,
        [
            "edit 1",
            "",
            "",
            "",
            "n",
            "add",
            "Added a nested editor, preserving commas in experience highlights.",
            "delete 1",
            "done",
            "",
            "",
            "",
            "",
            "",
            "",
            "y",
            "y",
            "apply",
            "y",
            "quit",
        ],
    )

    loaded = load_evidence_yaml(path, "experience")
    assert loaded.experience[0].highlights == [
        "Improved test coverage for core services.",
        "Added a nested editor, preserving commas in experience highlights.",
    ]


def test_experience_cli_delete_highlight_without_index_uses_picker(tmp_path):
    path = _write_yaml(tmp_path, _valid_experience_payload(), filename="experience.yaml")
    picker = FakePicker([1])

    _run_experience_cli_with_picker(
        path,
        [
            "edit 1",
            "",
            "",
            "",
            "n",
            "delete",
            "done",
            "",
            "",
            "",
            "",
            "",
            "",
            "y",
            "y",
            "apply",
            "y",
            "quit",
        ],
        picker,
    )

    loaded = load_evidence_yaml(path, "experience")
    assert picker.calls[0][0] == "Choose a highlight to delete"
    assert loaded.experience[0].highlights == [
        "Improved test coverage for core services.",
    ]


def test_experience_cli_edit_rejects_deleting_final_highlight(tmp_path):
    payload = _valid_experience_payload()
    payload["experience"][0]["highlights"] = ["Only experience highlight."]
    path = _write_yaml(tmp_path, payload, filename="experience.yaml")

    output = _run_schema_cli(
        "experience",
        path,
        [
            "edit 1",
            "",
            "",
            "",
            "n",
            "delete 1",
            "done",
            "",
            "",
            "",
            "",
            "",
            "",
            "y",
            "y",
            "quit",
        ],
    )

    loaded = load_evidence_yaml(path, "experience")
    assert loaded.experience[0].highlights == ["Only experience highlight."]
    assert "Error: At least one highlight is required." in output


def test_experience_cli_edit_highlight_invalid_commands_do_not_mutate_staged_data(tmp_path):
    path = _write_yaml(tmp_path, _valid_experience_payload(), filename="experience.yaml")

    output = _run_schema_cli(
        "experience",
        path,
        [
            "edit 1",
            "",
            "",
            "",
            "n",
            "wat",
            "edit 99",
            "delete nope",
            "done",
            "",
            "",
            "",
            "",
            "",
            "",
            "y",
            "y",
            "quit",
        ],
    )

    loaded = load_evidence_yaml(path, "experience")
    assert loaded.experience[0].highlights == _valid_experience_payload()["experience"][0][
        "highlights"
    ]
    assert "Error: Unknown highlights command 'wat'" in output
    assert "Error: Highlight index 99 is out of range" in output
    assert "Error: Highlight index must be an integer for 'delete'" in output


def test_experience_cli_create_edit_delete_and_apply(tmp_path):
    path = _write_yaml(tmp_path, _valid_experience_payload(), filename="experience.yaml")

    output = _run_schema_cli(
        "experience",
        path,
        [
            "create",
            "Second Company",
            "Platform Engineer",
            "Built platform tools.",
            "Shipped internal tools.",
            "",
            "",
            "FastAPI",
            "Python",
            "APIs",
            "Remote",
            "2025",
            "",
            "",
            "edit 1",
            "",
            "Senior Backend Engineer",
            "Updated backend summary.",
            "y",
            "",
            "",
            "",
            "",
            "",
            "",
            "y",
            "y",
            "delete 2",
            "y",
            "apply",
            "y",
            "quit",
        ],
    )

    loaded = load_evidence_yaml(path, "experience")
    assert loaded.experience[0].summary == "Updated backend summary."
    assert loaded.experience[0].role == "Senior Backend Engineer"
    assert loaded.experience[0].id == "backend-engineer"
    assert len(loaded.experience) == 1
    assert "Staged new experience entry 'Second Company'. Run 'apply' to save." in output
    assert "Staged deletion for 'Second Company'. Run 'apply' to save." in output


def test_experience_cli_apply_requires_confirmation_before_writing(tmp_path):
    path = _write_yaml(tmp_path, _valid_experience_payload(), filename="experience.yaml")

    output = _run_schema_cli(
        "experience",
        path,
        [
            "delete 1",
            "y",
            "apply",
            "n",
            "quit",
            "y",
        ],
    )

    loaded = load_evidence_yaml(path, "experience")
    assert len(loaded.experience) == 1
    assert "Apply canceled." in output


def test_user_cli_show_and_edit_after_apply(tmp_path):
    path = _write_yaml(tmp_path, _valid_user_payload(), filename="user.yaml")

    output = _run_schema_cli(
        "user",
        path,
        [
            "show",
            "edit",
            "Updated Candidate",
            "updated@example.com",
            "",
            "y",
            "n",
            "",
            "y",
            "apply",
            "y",
            "show",
            "quit",
        ],
    )

    loaded = load_evidence_yaml(path, "user")
    assert loaded.name == "Updated Candidate"
    assert loaded.email == "updated@example.com"
    assert loaded.github is None
    assert "Name: Updated Candidate" in output
    assert "GitHub: none" in output


def test_user_cli_apply_requires_confirmation_before_writing(tmp_path):
    path = _write_yaml(tmp_path, _valid_user_payload(), filename="user.yaml")

    output = _run_schema_cli(
        "user",
        path,
        [
            "edit",
            "Updated Candidate",
            "",
            "",
            "y",
            "y",
            "y",
            "apply",
            "n",
            "quit",
            "y",
        ],
    )

    loaded = load_evidence_yaml(path, "user")
    assert loaded.name == "Example Candidate"
    assert "Apply canceled." in output


def test_user_cli_reload_discards_dirty_changes_only_after_confirmation(tmp_path):
    path = _write_yaml(tmp_path, _valid_user_payload(), filename="user.yaml")

    output = _run_schema_cli(
        "user",
        path,
        [
            "edit",
            "Updated Candidate",
            "",
            "",
            "y",
            "y",
            "y",
            "reload",
            "y",
            "show",
            "quit",
        ],
    )

    loaded = load_evidence_yaml(path, "user")
    assert loaded.name == "Example Candidate"
    assert "Reloaded user evidence from disk." in output
    assert "Name: Example Candidate" in output.split("Reloaded user evidence from disk.")[-1]


def test_user_cli_quit_warns_about_unapplied_changes(tmp_path):
    path = _write_yaml(tmp_path, _valid_user_payload(), filename="user.yaml")

    output = _run_schema_cli(
        "user",
        path,
        [
            "edit",
            "Updated Candidate",
            "",
            "",
            "y",
            "y",
            "y",
            "quit",
            "n",
            "quit",
            "y",
        ],
    )

    assert "Quit canceled." in output
