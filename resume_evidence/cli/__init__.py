from __future__ import annotations

import argparse
from pathlib import Path
from typing import Callable, TextIO

from app.config import settings
from app.runtime_data import bootstrap_runtime_data
from resume_evidence.cli.education import EducationEvidenceCLI
from resume_evidence.cli.experience import ExperienceEvidenceCLI
from resume_evidence.cli.projects import ProjectsEvidenceCLI
from resume_evidence.cli.skills import SkillsEvidenceCLI
from resume_evidence.cli.user import UserInfoEvidenceCLI
from resume_evidence.session import (
    EducationEvidenceSession,
    ExperienceEvidenceSession,
    ProjectsEvidenceSession,
    SkillsEvidenceSession,
    UserInfoEvidenceSession,
)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Interactive CLI for resume evidence.")
    parser.add_argument(
        "--path",
        type=Path,
        default=None,
        help="Optional path to an evidence YAML file. Defaults to the selected user/resume_evidence file.",
    )
    parser.add_argument(
        "--schema",
        choices=("education", "experience", "projects", "skills", "user"),
        default="projects",
        help="Evidence schema to manage. Defaults to projects.",
    )
    return parser


def main(
    argv: list[str] | None = None,
    *,
    input_func: Callable[[str], str] = input,
    output: TextIO | None = None,
) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    if args.path is None:
        bootstrap_runtime_data(
            data_dir=settings.RESUMECR7_DATA_DIR,
            evidence_root=settings.RESUME_EVIDENCE_ROOT,
            generation_root=settings.RESUME_GENERATION_ROOT,
            artifacts_root=settings.resume_generation_artifacts_root,
            log_dir=settings.RESUMECR7_LOG_DIR,
        )

    if args.schema == "education":
        session = EducationEvidenceSession.load(args.path)
        cli = EducationEvidenceCLI(session, input_func=input_func, output=output)
    elif args.schema == "experience":
        session = ExperienceEvidenceSession.load(args.path)
        cli = ExperienceEvidenceCLI(session, input_func=input_func, output=output)
    elif args.schema == "skills":
        session = SkillsEvidenceSession.load(args.path)
        cli = SkillsEvidenceCLI(session, input_func=input_func, output=output)
    elif args.schema == "user":
        session = UserInfoEvidenceSession.load(args.path)
        cli = UserInfoEvidenceCLI(session, input_func=input_func, output=output)
    else:
        session = ProjectsEvidenceSession.load(args.path)
        cli = ProjectsEvidenceCLI(session, input_func=input_func, output=output)

    return cli.run()


__all__ = ["build_arg_parser", "main"]
