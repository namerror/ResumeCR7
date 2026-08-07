import type { JobTarget, ResumeEvidenceRegistry, ResumeGenerationConfig } from "./types";

export function validateDraftEvidence(draft: ResumeEvidenceRegistry): string[] {
  const errors: string[] = [];

  requireText(errors, "User name", draft.user.name);
  requireText(errors, "User email", draft.user.email);
  requireText(errors, "User phone", draft.user.phone);
  validateOptionalLinks(errors, "User links", [
    draft.user.linkedin,
    draft.user.github,
    draft.user.website,
  ]);
  validateList(errors, "Skills technology", draft.skills.skills.technology);
  validateList(errors, "Skills programming", draft.skills.skills.programming);
  validateList(errors, "Skills concepts", draft.skills.skills.concepts);

  for (const project of draft.projects.projects) {
    const label = project.name.trim() || "Untitled project";
    requireText(errors, `${label} name`, project.name);
    requireText(errors, `${label} summary`, project.summary);
    validateList(errors, `${label} highlights`, project.highlights, 1);
    validateList(errors, `${label} technology skills`, project.skills.technology);
    validateList(errors, `${label} programming skills`, project.skills.programming);
    validateList(errors, `${label} concept skills`, project.skills.concepts);
    validateList(errors, `${label} links`, project.links ?? []);
  }

  for (const experience of draft.experience.experience) {
    const label = experience.name.trim() || "Untitled experience";
    requireText(errors, `${label} organization`, experience.name);
    requireText(errors, `${label} role`, experience.role);
    requireText(errors, `${label} summary`, experience.summary);
    requireText(errors, `${label} location`, experience.location);
    requireText(errors, `${label} start`, experience.start);
    validateList(errors, `${label} highlights`, experience.highlights, 1);
    validateList(errors, `${label} technology skills`, experience.skills.technology);
    validateList(errors, `${label} programming skills`, experience.skills.programming);
    validateList(errors, `${label} concept skills`, experience.skills.concepts);
    validateList(errors, `${label} links`, experience.links ?? []);
  }

  for (const education of draft.education.education) {
    const label = education.name.trim() || "Untitled education";
    requireText(errors, `${label} institution`, education.name);
    requireText(errors, `${label} degree`, education.degree);
    requireText(errors, `${label} grade`, education.grade);
    requireText(errors, `${label} location`, education.location);
    requireText(errors, `${label} start`, education.start);
    validateList(errors, `${label} coursework`, education.relevant_coursework);
  }

  return errors;
}

export function validateGenerationConfig(draft: ResumeGenerationConfig): string[] {
  const errors: string[] = [];

  validateNullableNonNegativeInteger(
    errors,
    "# of skills to display in the skills section per category",
    draft.skill_selection.top_n,
  );
  validateNullableNonNegativeInteger(
    errors,
    "# of projects to select for the resume",
    draft.project_selection.top_n,
  );
  validateNullableNonNegativeInteger(
    errors,
    "# of experience entries to include in the resume",
    draft.experience_selection.top_n,
  );
  validateNullablePositiveInteger(
    errors,
    "Link scanning highlights",
    draft.link_scanning.highlight_count,
  );
  validateNullablePositiveInteger(
    errors,
    "Link scanning max tokens per highlight",
    draft.link_scanning.max_tokens_per_highlight,
  );
  requireText(errors, "Resume output directory", draft.resume_output.output_dir);

  if (draft.bullet_count_range !== null) {
    const { min, max } = draft.bullet_count_range;
    validatePositiveInteger(errors, "Bullet count lower bound", min);
    validatePositiveInteger(errors, "Bullet count upper bound", max);
    if (Number.isInteger(min) && Number.isInteger(max) && min > max) {
      errors.push("Bullet count lower bound must be less than or equal to upper bound.");
    }
    if (Number.isInteger(max) && max > 10) {
      errors.push("Bullet count upper bound must be 10 or less.");
    }
  }

  return errors;
}

export function validateJobTarget(draft: JobTarget): string[] {
  const errors: string[] = [];
  requireText(errors, "Job title", draft.title);
  return errors;
}

function requireText(errors: string[], label: string, value: string): void {
  if (!value.trim()) {
    errors.push(`${label} is required.`);
  }
}

function validateNullableNonNegativeInteger(
  errors: string[],
  label: string,
  value: number | null,
): void {
  if (value === null) {
    return;
  }
  if (!Number.isInteger(value) || value < 0) {
    errors.push(`${label} must be a whole number greater than or equal to 0.`);
  }
}

function validateNullablePositiveInteger(
  errors: string[],
  label: string,
  value: number | null,
): void {
  if (value === null) {
    return;
  }
  validatePositiveInteger(errors, label, value);
}

function validatePositiveInteger(errors: string[], label: string, value: number): void {
  if (!Number.isInteger(value) || value < 1) {
    errors.push(`${label} must be a whole number greater than 0.`);
  }
}

function validateList(
  errors: string[],
  label: string,
  values: string[],
  minLength = 0,
): void {
  if (values.length < minLength) {
    errors.push(`${label} needs at least ${minLength} entry.`);
  }
  if (values.some((value) => !value.trim())) {
    errors.push(`${label} has a blank entry.`);
  }
}

function validateOptionalLinks(errors: string[], label: string, values: Array<string | null>): void {
  if (values.some((value) => value !== null && !value.trim())) {
    errors.push(`${label} have a blank entry.`);
  }
}
