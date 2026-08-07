import type { EvidenceApi } from "./api";
import { deepEqual } from "./draft";
import { sortProjectSkills } from "./skills";
import type {
  EducationRecord,
  EducationRecordInput,
  ExperienceRecord,
  ExperienceRecordInput,
  ProjectRecord,
  ProjectRecordInput,
  ResumeEvidenceRegistry,
  SkillsInput,
  UserInfoInput,
} from "./types";

export type ApplyOperation =
  | { action: "update"; resource: "user"; payload: UserInfoInput }
  | { action: "update"; resource: "skills"; payload: SkillsInput }
  | { action: "create"; resource: "projects"; payload: ProjectRecordInput }
  | { action: "update"; resource: "projects"; id: string; payload: ProjectRecordInput }
  | { action: "delete"; resource: "projects"; id: string }
  | { action: "create"; resource: "experience"; payload: ExperienceRecordInput }
  | { action: "update"; resource: "experience"; id: string; payload: ExperienceRecordInput }
  | { action: "delete"; resource: "experience"; id: string }
  | { action: "create"; resource: "education"; payload: EducationRecordInput }
  | { action: "update"; resource: "education"; id: string; payload: EducationRecordInput }
  | { action: "delete"; resource: "education"; id: string };

export function buildApplyOperations(
  baseline: ResumeEvidenceRegistry,
  draft: ResumeEvidenceRegistry,
): ApplyOperation[] {
  const operations: ApplyOperation[] = [];
  const baselineUser = toUserInput(baseline.user);
  const draftUser = toUserInput(draft.user);
  const baselineSkills = toSkillsInput(baseline.skills);
  const draftSkills = toSkillsInput(draft.skills);

  if (!deepEqual(baselineUser, draftUser)) {
    operations.push({ action: "update", resource: "user", payload: draftUser });
  }

  if (!deepEqual(baselineSkills, draftSkills)) {
    operations.push({ action: "update", resource: "skills", payload: draftSkills });
  }

  operations.push(...buildProjectOperations(baseline.projects.projects, draft.projects.projects));
  operations.push(...buildExperienceOperations(baseline.experience.experience, draft.experience.experience));
  operations.push(...buildEducationOperations(baseline.education.education, draft.education.education));

  return operations;
}

export async function applyEvidenceChanges(
  api: EvidenceApi,
  baseline: ResumeEvidenceRegistry,
  draft: ResumeEvidenceRegistry,
  onOperation?: (operation: ApplyOperation) => void,
): Promise<number> {
  const operations = buildApplyOperations(baseline, draft);

  for (const operation of operations) {
    onOperation?.(operation);
    await executeOperation(api, operation);
  }

  return operations.length;
}

export function describeOperation(operation: ApplyOperation): string {
  if (operation.action === "update" && operation.resource === "user") {
    return "Update user";
  }
  if (operation.action === "update" && operation.resource === "skills") {
    return "Update skills";
  }

  const resourceLabel =
    operation.resource === "projects"
      ? "project"
      : operation.resource === "experience"
        ? "experience"
        : "education";

  if (operation.action === "create") {
    return `Create ${resourceLabel}`;
  }
  if (operation.action === "delete") {
    return `Delete ${resourceLabel} ${operation.id}`;
  }
  return `Update ${resourceLabel} ${operation.id}`;
}

export function toProjectInput(record: ProjectRecord): ProjectRecordInput {
  return {
    name: record.name,
    summary: record.summary,
    highlights: [...record.highlights],
    active: record.active,
    skills: cloneSkills(record.skills),
    links: normalizeOptionalList(record.links),
  };
}

export function toExperienceInput(record: ExperienceRecord): ExperienceRecordInput {
  return {
    name: record.name,
    role: record.role,
    summary: record.summary,
    highlights: [...record.highlights],
    active: record.active,
    skills: cloneSkills(record.skills),
    location: record.location,
    start: record.start,
    end: normalizeOptionalText(record.end),
    links: normalizeOptionalList(record.links),
  };
}

export function toEducationInput(record: EducationRecord): EducationRecordInput {
  return {
    name: record.name,
    degree: record.degree,
    grade: record.grade,
    start: record.start,
    end: normalizeOptionalText(record.end),
    location: record.location,
    relevant_coursework: [...record.relevant_coursework],
  };
}

export function toUserInput(record: ResumeEvidenceRegistry["user"]): UserInfoInput {
  return {
    name: record.name,
    email: record.email,
    phone: record.phone,
    linkedin: normalizeOptionalText(record.linkedin),
    github: normalizeOptionalText(record.github),
    website: normalizeOptionalText(record.website),
  };
}

export function toSkillsInput(record: ResumeEvidenceRegistry["skills"]): SkillsInput {
  return {
    skills: sortProjectSkills(record.skills),
  };
}

function buildProjectOperations(
  baselineRecords: ProjectRecord[],
  draftRecords: ProjectRecord[],
): ApplyOperation[] {
  const operations: ApplyOperation[] = [];
  const draftById = new Map(draftRecords.map((record) => [record.id, record]));
  const baselineById = new Map(baselineRecords.map((record) => [record.id, record]));

  for (const record of baselineRecords) {
    if (!draftById.has(record.id)) {
      operations.push({ action: "delete", resource: "projects", id: record.id });
    }
  }

  for (const record of draftRecords) {
    const baselineRecord = baselineById.get(record.id);
    if (!baselineRecord) {
      operations.push({ action: "create", resource: "projects", payload: toProjectInput(record) });
      continue;
    }

    const baselineInput = toProjectInput(baselineRecord);
    const draftInput = toProjectInput(record);
    if (!deepEqual(baselineInput, draftInput)) {
      operations.push({
        action: "update",
        resource: "projects",
        id: record.id,
        payload: draftInput,
      });
    }
  }

  return operations;
}

function buildExperienceOperations(
  baselineRecords: ExperienceRecord[],
  draftRecords: ExperienceRecord[],
): ApplyOperation[] {
  const operations: ApplyOperation[] = [];
  const draftById = new Map(draftRecords.map((record) => [record.id, record]));
  const baselineById = new Map(baselineRecords.map((record) => [record.id, record]));

  for (const record of baselineRecords) {
    if (!draftById.has(record.id)) {
      operations.push({ action: "delete", resource: "experience", id: record.id });
    }
  }

  for (const record of draftRecords) {
    const baselineRecord = baselineById.get(record.id);
    if (!baselineRecord) {
      operations.push({
        action: "create",
        resource: "experience",
        payload: toExperienceInput(record),
      });
      continue;
    }

    const baselineInput = toExperienceInput(baselineRecord);
    const draftInput = toExperienceInput(record);
    if (!deepEqual(baselineInput, draftInput)) {
      operations.push({
        action: "update",
        resource: "experience",
        id: record.id,
        payload: draftInput,
      });
    }
  }

  return operations;
}

function buildEducationOperations(
  baselineRecords: EducationRecord[],
  draftRecords: EducationRecord[],
): ApplyOperation[] {
  const operations: ApplyOperation[] = [];
  const draftById = new Map(draftRecords.map((record) => [record.id, record]));
  const baselineById = new Map(baselineRecords.map((record) => [record.id, record]));

  for (const record of baselineRecords) {
    if (!draftById.has(record.id)) {
      operations.push({ action: "delete", resource: "education", id: record.id });
    }
  }

  for (const record of draftRecords) {
    const baselineRecord = baselineById.get(record.id);
    if (!baselineRecord) {
      operations.push({
        action: "create",
        resource: "education",
        payload: toEducationInput(record),
      });
      continue;
    }

    const baselineInput = toEducationInput(baselineRecord);
    const draftInput = toEducationInput(record);
    if (!deepEqual(baselineInput, draftInput)) {
      operations.push({
        action: "update",
        resource: "education",
        id: record.id,
        payload: draftInput,
      });
    }
  }

  return operations;
}

async function executeOperation(api: EvidenceApi, operation: ApplyOperation): Promise<unknown> {
  if (operation.resource === "user") {
    return api.updateUser(operation.payload);
  }
  if (operation.resource === "skills") {
    return api.updateSkills(operation.payload);
  }
  if (operation.resource === "projects") {
    if (operation.action === "create") {
      return api.createProject(operation.payload);
    }
    if (operation.action === "update") {
      return api.updateProject(operation.id, operation.payload);
    }
    return api.deleteProject(operation.id);
  }
  if (operation.resource === "experience") {
    if (operation.action === "create") {
      return api.createExperience(operation.payload);
    }
    if (operation.action === "update") {
      return api.updateExperience(operation.id, operation.payload);
    }
    return api.deleteExperience(operation.id);
  }
  if (operation.action === "create") {
    return api.createEducation(operation.payload);
  }
  if (operation.action === "update") {
    return api.updateEducation(operation.id, operation.payload);
  }
  return api.deleteEducation(operation.id);
}

function normalizeOptionalText(value: string | null): string | null {
  if (value === null) {
    return null;
  }
  return value.length > 0 ? value : null;
}

function normalizeOptionalList(value: string[] | null): string[] | null {
  if (!value || value.length === 0) {
    return null;
  }
  return [...value];
}

function cloneSkills(skills: ProjectRecord["skills"]): ProjectRecord["skills"] {
  return {
    technology: [...skills.technology],
    programming: [...skills.programming],
    concepts: [...skills.concepts],
  };
}
