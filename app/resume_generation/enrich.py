from __future__ import annotations

import argparse
import os
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml

from app.link_scanning.models import LinkScanRequest, LinkScanResponse
from app.link_scanning.service import scan_link_evidence_service
from app.resume_evidence.loader import default_evidence_paths, load_evidence_yaml
from app.resume_evidence.models import (
    ExperienceFile,
    ExperienceRecord,
    ProjectRecord,
    ProjectsFile,
)
from app.resume_generation.config import (
    load_generation_config,
    resolve_generation_config_path,
)
from app.resume_generation.models import ResumeGenerationConfig

EvidenceSchema = Literal["projects", "experience", "all"]
EvidenceType = Literal["project", "experience"]
EvidenceRecord = ProjectRecord | ExperienceRecord
LinkScanService = Callable[[LinkScanRequest], LinkScanResponse]


@dataclass(frozen=True)
class LinkEvidenceEnrichmentRecordResult:
    evidence_type: EvidenceType
    evidence_id: str
    name: str
    scanned: bool
    added_highlights: tuple[str, ...]
    skipped_reason: str | None = None
    details: dict[str, Any] | None = None


@dataclass(frozen=True)
class LinkEvidenceEnrichmentResult:
    dry_run: bool
    records: tuple[LinkEvidenceEnrichmentRecordResult, ...]
    updated_paths: tuple[str, ...]

    @property
    def total_added_highlights(self) -> int:
        return sum(len(record.added_highlights) for record in self.records)

    @property
    def scanned_count(self) -> int:
        return sum(1 for record in self.records if record.scanned)


def _write_yaml_atomic(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_file_path: str | None = None

    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            yaml.safe_dump(data, handle, sort_keys=False)
            temp_file_path = handle.name

        os.replace(temp_file_path, path)
    finally:
        if temp_file_path is not None and os.path.exists(temp_file_path):
            os.unlink(temp_file_path)


def _resolve_evidence_paths(
    evidence_paths: Mapping[str, Path | str] | None,
) -> dict[str, Path]:
    resolved = default_evidence_paths()
    if evidence_paths is not None:
        resolved.update({schema_name: Path(path) for schema_name, path in evidence_paths.items()})
    return resolved


def _selected_schemas(evidence_type: EvidenceSchema) -> tuple[Literal["projects", "experience"], ...]:
    if evidence_type == "all":
        return ("projects", "experience")
    return (evidence_type,)


def _append_unique_highlights(
    existing: Sequence[str],
    additions: Sequence[str],
) -> tuple[str, ...]:
    seen = {item.strip().casefold() for item in existing}
    appended: list[str] = []
    for addition in additions:
        normalized = addition.strip()
        key = normalized.casefold()
        if not normalized or key in seen:
            continue
        seen.add(key)
        appended.append(normalized)
    return tuple(appended)


def _request_for_record(
    *,
    evidence_type: EvidenceType,
    record: EvidenceRecord,
    config: ResumeGenerationConfig,
    dev_mode: bool | None,
    llm_model: str | None,
    llm_max_output_tokens: int | None,
    highlight_count: int | None,
    max_tokens_per_highlight: int | None,
) -> LinkScanRequest:
    link_config = config.link_scanning
    return LinkScanRequest(
        evidence_type=evidence_type,
        evidence=record,
        dev_mode=dev_mode if dev_mode is not None else link_config.dev_mode,
        llm_model=llm_model if llm_model is not None else link_config.llm_model,
        llm_max_output_tokens=(
            llm_max_output_tokens
            if llm_max_output_tokens is not None
            else link_config.llm_max_output_tokens
        ),
        requested_highlight_count=(
            highlight_count if highlight_count is not None else link_config.highlight_count
        ),
        max_tokens_per_highlight=(
            max_tokens_per_highlight
            if max_tokens_per_highlight is not None
            else link_config.max_tokens_per_highlight
        ),
    )


def _enrich_records_data(
    *,
    schema_name: Literal["projects", "experience"],
    data: dict[str, Any],
    config: ResumeGenerationConfig,
    evidence_id: str | None,
    dry_run: bool,
    dev_mode: bool | None,
    llm_model: str | None,
    llm_max_output_tokens: int | None,
    highlight_count: int | None,
    max_tokens_per_highlight: int | None,
    scan_service: LinkScanService,
) -> tuple[dict[str, Any], tuple[LinkEvidenceEnrichmentRecordResult, ...], bool, bool]:
    evidence_type: EvidenceType = "project" if schema_name == "projects" else "experience"
    list_key = "projects" if schema_name == "projects" else "experience"
    file_model = (
        ProjectsFile.model_validate(data)
        if schema_name == "projects"
        else ExperienceFile.model_validate(data)
    )
    records: Sequence[EvidenceRecord] = (
        file_model.projects if isinstance(file_model, ProjectsFile) else file_model.experience
    )

    results: list[LinkEvidenceEnrichmentRecordResult] = []
    changed = False
    matched_target = evidence_id is None
    updated_data = file_model.model_dump(mode="python")

    for index, record in enumerate(records):
        if evidence_id is not None and record.id != evidence_id:
            continue

        matched_target = True
        if not record.links:
            results.append(
                LinkEvidenceEnrichmentRecordResult(
                    evidence_type=evidence_type,
                    evidence_id=record.id,
                    name=record.name,
                    scanned=False,
                    added_highlights=(),
                    skipped_reason="no_links",
                )
            )
            continue

        response = scan_service(
            _request_for_record(
                evidence_type=evidence_type,
                record=record,
                config=config,
                dev_mode=dev_mode,
                llm_model=llm_model,
                llm_max_output_tokens=llm_max_output_tokens,
                highlight_count=highlight_count,
                max_tokens_per_highlight=max_tokens_per_highlight,
            )
        )
        additions = _append_unique_highlights(
            record.highlights,
            [highlight.text for highlight in response.added_highlights],
        )
        if additions:
            changed = True
            updated_data[list_key][index]["highlights"] = [
                *record.highlights,
                *additions,
            ]

        results.append(
            LinkEvidenceEnrichmentRecordResult(
                evidence_type=evidence_type,
                evidence_id=record.id,
                name=record.name,
                scanned=True,
                added_highlights=additions,
                skipped_reason=None if additions else "no_new_highlights",
                details=response.details,
            )
        )

    if changed and not dry_run:
        if schema_name == "projects":
            ProjectsFile.model_validate(updated_data)
        else:
            ExperienceFile.model_validate(updated_data)

    return updated_data, tuple(results), changed, matched_target


def run_link_evidence_enrichment(
    *,
    evidence_type: EvidenceSchema = "all",
    evidence_id: str | None = None,
    evidence_paths: Mapping[str, Path | str] | None = None,
    config_path: Path | str | None = None,
    config: ResumeGenerationConfig | None = None,
    dry_run: bool = False,
    dev_mode: bool | None = None,
    llm_model: str | None = None,
    llm_max_output_tokens: int | None = None,
    highlight_count: int | None = None,
    max_tokens_per_highlight: int | None = None,
    scan_service: LinkScanService = scan_link_evidence_service,
) -> LinkEvidenceEnrichmentResult:
    if evidence_id is not None:
        normalized_evidence_id = evidence_id.strip()
        if not normalized_evidence_id:
            raise ValueError("evidence_id must not be empty")
        if evidence_type == "all":
            raise ValueError("evidence_id requires evidence_type to be projects or experience")
        evidence_id = normalized_evidence_id

    effective_config = config if config is not None else load_generation_config(config_path)
    resolved_paths = _resolve_evidence_paths(evidence_paths)
    all_results: list[LinkEvidenceEnrichmentRecordResult] = []
    updated_paths: list[str] = []
    found_target = evidence_id is None

    for schema_name in _selected_schemas(evidence_type):
        path = resolved_paths[schema_name]
        loaded = load_evidence_yaml(path, schema_name)
        if not isinstance(loaded, (ProjectsFile, ExperienceFile)):
            raise TypeError(f"Expected {schema_name} evidence file")

        data, schema_results, changed, matched_target = _enrich_records_data(
            schema_name=schema_name,
            data=loaded.model_dump(mode="python"),
            config=effective_config,
            evidence_id=evidence_id,
            dry_run=dry_run,
            dev_mode=dev_mode,
            llm_model=llm_model,
            llm_max_output_tokens=llm_max_output_tokens,
            highlight_count=highlight_count,
            max_tokens_per_highlight=max_tokens_per_highlight,
            scan_service=scan_service,
        )
        found_target = found_target or matched_target
        all_results.extend(schema_results)
        if changed and not dry_run:
            _write_yaml_atomic(path, data)
            updated_paths.append(str(path))

    if not found_target:
        raise ValueError(f"No {evidence_type} evidence record found with id: {evidence_id}")

    return LinkEvidenceEnrichmentResult(
        dry_run=dry_run,
        records=tuple(all_results),
        updated_paths=tuple(updated_paths),
    )


def _build_config_path_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--config-path", default=str(resolve_generation_config_path()))
    return parser


def _build_arg_parser(config: ResumeGenerationConfig | None = None) -> argparse.ArgumentParser:
    link_config = config.link_scanning if config is not None else None
    evidence_paths = default_evidence_paths()
    parser = argparse.ArgumentParser(
        description="Enrich project and experience evidence by scanning configured links."
    )
    parser.add_argument(
        "--evidence-type",
        choices=("projects", "experience", "all"),
        default="all",
    )
    parser.add_argument("--config-path", default=str(resolve_generation_config_path()))
    parser.add_argument("--projects-path", default=str(evidence_paths["projects"]))
    parser.add_argument("--experience-path", default=str(evidence_paths["experience"]))
    parser.add_argument(
        "--dev-mode",
        action=argparse.BooleanOptionalAction,
        default=None if link_config is None else link_config.dev_mode,
    )
    parser.add_argument(
        "--highlight-count",
        type=int,
        default=None if link_config is None else link_config.highlight_count,
    )
    parser.add_argument(
        "--llm-model",
        default=None if link_config is None else link_config.llm_model,
    )
    parser.add_argument(
        "--llm-max-output-tokens",
        type=int,
        default=None if link_config is None else link_config.llm_max_output_tokens,
    )
    parser.add_argument(
        "--max-tokens-per-highlight",
        type=int,
        default=None if link_config is None else link_config.max_tokens_per_highlight,
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    config_path_args, _ = _build_config_path_parser().parse_known_args(argv)
    config = load_generation_config(config_path_args.config_path)
    args = _build_arg_parser(config).parse_args(argv)
    evidence_paths: dict[str, Path | str] = {}
    if args.projects_path:
        evidence_paths["projects"] = args.projects_path
    if args.experience_path:
        evidence_paths["experience"] = args.experience_path

    result = run_link_evidence_enrichment(
        evidence_type=args.evidence_type,
        evidence_paths=evidence_paths or None,
        config_path=args.config_path,
        config=config,
        dry_run=args.dry_run,
        dev_mode=args.dev_mode,
        llm_model=args.llm_model,
        llm_max_output_tokens=args.llm_max_output_tokens,
        highlight_count=args.highlight_count,
        max_tokens_per_highlight=args.max_tokens_per_highlight,
    )
    print(
        "Scanned "
        f"{result.scanned_count} records; added "
        f"{result.total_added_highlights} highlights."
    )
    for record in result.records:
        if record.added_highlights:
            print(
                f"{record.evidence_type}:{record.evidence_id} "
                f"+{len(record.added_highlights)}"
            )
    if result.updated_paths:
        print("Updated: " + ", ".join(result.updated_paths))
    if result.dry_run:
        print("Dry run: no files written.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
