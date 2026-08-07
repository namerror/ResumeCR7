"""Resume-generation orchestration boundary.

This package is reserved for code that loads resume evidence, calls the
selection services, and prepares structured resume fill data.
"""

import importlib

from app.resume_generation.config import (
    DEFAULT_GENERATION_CONFIG_PATH,
    DEFAULT_JOB_TARGET_PATH,
    default_generation_config_payload,
    ensure_generation_config_defaults,
    load_generation_config,
    load_generation_config_payload,
    load_job_target,
    merge_generation_config_defaults,
    resolve_generation_config_path,
    resolve_job_target_path,
    write_generation_config_payload,
)
from app.resume_generation.assembly import assemble_intermediate_resume_result
from app.resume_generation.models import (
    BulletCountRangeConfig,
    BulletPointGenerationConfig,
    ExperienceBulletPointResult,
    ExperienceSelectionConfig,
    GenerationAppConfig,
    IntermediateResumeResult,
    JobFocusGenerationConfig,
    JobFocusResult,
    JobTarget,
    LinkScanningConfig,
    OpenAIConfig,
    ProjectBulletPointResult,
    ProjectLinkScanResult,
    ProjectSelectionConfig,
    ProjectSelectionResult,
    ResumeGenerationConcurrencyConfig,
    ResumeGenerationCacheConfig,
    ResumeEducationItem,
    ResumeExperienceItem,
    ResumeGenerationConfig,
    ResumeOutputConfig,
    ResumeProjectItem,
    ResumeSelectionContext,
    ResumeSkillsSection,
    ResumeTopSection,
    SkillSelectionConfig,
    SkillSelectionResult,
)
from app.resume_generation.bullet_points import (
    generate_experience_bullet_points_async,
    generate_experience_bullet_points,
    generate_project_bullet_points_async,
    generate_project_bullet_points,
)
from app.resume_generation.job_focus import derive_job_focus
from app.resume_generation.cache import ResumeGenerationStageCache, ResumeGenerationStageCacheResult
from app.resume_generation.latex import (
    DEFAULT_RESUME_TEX_ARTIFACT_PATH,
    copy_resume_latex_to_user_output,
    latex_escape,
    render_resume_latex,
    resolve_resume_latex_output_path,
    resolve_resume_user_latex_output_path,
    resolve_resume_user_output_dir,
    write_resume_latex_artifact,
)
from app.resume_generation.pdf import (
    DEFAULT_LATEX_LOCAL_COMMAND,
    DEFAULT_RESUME_PDF_ARTIFACT_PATH,
    DEFAULT_RESUME_TEX_INPUT_PATH,
    LatexPdfPrerequisiteError,
    LatexPdfRenderError,
    copy_resume_pdf_to_user_output,
    render_latex_pdf,
    resolve_resume_pdf_output_path,
    resolve_resume_user_pdf_output_path,
)
from app.resume_generation.selection import (
    ResumeGenerationError,
    build_skill_selection_payload,
    generate_selection_context,
)

_LAZY_EXPORT_MODULES = {
    "LinkEvidenceEnrichmentRecordResult": ".enrich",
    "LinkEvidenceEnrichmentResult": ".enrich",
    "run_link_evidence_enrichment": ".enrich",
    "DEFAULT_RESUME_RESULT_ARTIFACT_PATH": ".main",
    "DEFAULT_RESUME_RUN_MANIFEST_ARTIFACT_PATH": ".main",
    "build_resume_run_manifest": ".main",
    "resolve_resume_result_artifact_path": ".main",
    "resolve_resume_run_manifest_artifact_path": ".main",
    "run_resume_generation_pipeline_async": ".main",
    "run_resume_generation_pipeline": ".main",
    "write_resume_pdf_from_config": ".main",
    "write_resume_result_artifact": ".main",
    "write_resume_run_manifest_artifact": ".main",
}


def __getattr__(name: str):
    if module_name := _LAZY_EXPORT_MODULES.get(name):
        module = importlib.import_module(module_name, __name__)
        value = getattr(module, name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "DEFAULT_GENERATION_CONFIG_PATH",
    "DEFAULT_LATEX_LOCAL_COMMAND",
    "DEFAULT_JOB_TARGET_PATH",
    "DEFAULT_RESUME_PDF_ARTIFACT_PATH",
    "DEFAULT_RESUME_RESULT_ARTIFACT_PATH",
    "DEFAULT_RESUME_RUN_MANIFEST_ARTIFACT_PATH",
    "DEFAULT_RESUME_TEX_ARTIFACT_PATH",
    "DEFAULT_RESUME_TEX_INPUT_PATH",
    "BulletCountRangeConfig",
    "BulletPointGenerationConfig",
    "ExperienceBulletPointResult",
    "ExperienceSelectionConfig",
    "GenerationAppConfig",
    "IntermediateResumeResult",
    "JobFocusGenerationConfig",
    "JobFocusResult",
    "JobTarget",
    "LinkEvidenceEnrichmentRecordResult",
    "LinkEvidenceEnrichmentResult",
    "LinkScanningConfig",
    "LatexPdfPrerequisiteError",
    "LatexPdfRenderError",
    "OpenAIConfig",
    "ProjectBulletPointResult",
    "ProjectLinkScanResult",
    "ProjectSelectionConfig",
    "ProjectSelectionResult",
    "ResumeGenerationCacheConfig",
    "ResumeGenerationStageCache",
    "ResumeGenerationStageCacheResult",
    "ResumeEducationItem",
    "ResumeExperienceItem",
    "ResumeGenerationConfig",
    "ResumeGenerationConcurrencyConfig",
    "ResumeGenerationError",
    "ResumeOutputConfig",
    "ResumeProjectItem",
    "ResumeSelectionContext",
    "ResumeSkillsSection",
    "ResumeTopSection",
    "SkillSelectionConfig",
    "SkillSelectionResult",
    "assemble_intermediate_resume_result",
    "build_resume_run_manifest",
    "build_skill_selection_payload",
    "copy_resume_latex_to_user_output",
    "copy_resume_pdf_to_user_output",
    "default_generation_config_payload",
    "derive_job_focus",
    "ensure_generation_config_defaults",
    "generate_experience_bullet_points",
    "generate_experience_bullet_points_async",
    "generate_project_bullet_points",
    "generate_project_bullet_points_async",
    "generate_selection_context",
    "latex_escape",
    "load_generation_config",
    "load_generation_config_payload",
    "load_job_target",
    "merge_generation_config_defaults",
    "render_resume_latex",
    "render_latex_pdf",
    "resolve_generation_config_path",
    "resolve_job_target_path",
    "resolve_resume_result_artifact_path",
    "resolve_resume_run_manifest_artifact_path",
    "resolve_resume_pdf_output_path",
    "resolve_resume_latex_output_path",
    "resolve_resume_user_latex_output_path",
    "resolve_resume_user_output_dir",
    "resolve_resume_user_pdf_output_path",
    "run_link_evidence_enrichment",
    "run_resume_generation_pipeline",
    "run_resume_generation_pipeline_async",
    "write_resume_result_artifact",
    "write_resume_latex_artifact",
    "write_resume_pdf_from_config",
    "write_resume_run_manifest_artifact",
    "write_generation_config_payload",
]
