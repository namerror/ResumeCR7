import type {
  EducationRecord,
  ExperienceRecord,
  ProjectRecord,
  ProjectSkills,
  ResumeEvidenceRegistry,
} from "./types";
import { sortProjectSkills } from "./skills";

export const tempIdPrefix = "tmp-";

export function cloneEvidence<T>(value: T): T {
  if (typeof structuredClone === "function") {
    return structuredClone(value);
  }
  return JSON.parse(JSON.stringify(value)) as T;
}

export function createTempId(scope: string): string {
  const randomValue =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  return `${tempIdPrefix}${scope}-${randomValue}`;
}

export function isTempId(id: string): boolean {
  return id.startsWith(tempIdPrefix);
}

export function createEmptySkills(): ProjectSkills {
  return {
    technology: [],
    programming: [],
    concepts: [],
  };
}

export function createBlankProject(): ProjectRecord {
  return {
    id: createTempId("project"),
    name: "",
    summary: "",
    highlights: [""],
    active: true,
    skills: createEmptySkills(),
    links: null,
  };
}

export function createBlankExperience(): ExperienceRecord {
  return {
    id: createTempId("experience"),
    name: "",
    role: "",
    summary: "",
    highlights: [""],
    active: true,
    skills: createEmptySkills(),
    location: "",
    start: "",
    end: null,
    links: null,
  };
}

export function createBlankEducation(): EducationRecord {
  return {
    id: createTempId("education"),
    name: "",
    degree: "",
    grade: "",
    start: "",
    end: null,
    location: "",
    relevant_coursework: [],
  };
}

export function hasDraftChanges(
  baseline: ResumeEvidenceRegistry | null,
  draft: ResumeEvidenceRegistry | null,
): boolean {
  if (!baseline || !draft) {
    return false;
  }
  return !deepEqual(toComparableEvidence(baseline), toComparableEvidence(draft));
}

export function deepEqual(left: unknown, right: unknown): boolean {
  return JSON.stringify(left) === JSON.stringify(right);
}

function toComparableEvidence(evidence: ResumeEvidenceRegistry): ResumeEvidenceRegistry {
  const comparable = cloneEvidence(evidence);
  comparable.skills.skills = sortProjectSkills(comparable.skills.skills);
  return comparable;
}
