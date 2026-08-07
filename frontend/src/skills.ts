import type { ProjectSkills } from "./types";
import { skillCategories } from "./types";

export function normalizeSkillName(value: string): string {
  return value.trim().toLowerCase();
}

export function compareSkillNames(left: string, right: string): number {
  const leftKey = normalizeSkillName(left);
  const rightKey = normalizeSkillName(right);

  if (leftKey < rightKey) {
    return -1;
  }
  if (leftKey > rightKey) {
    return 1;
  }
  return left.trim() < right.trim() ? -1 : left.trim() > right.trim() ? 1 : 0;
}

export function sortSkillList(values: string[]): string[] {
  return [...values].sort(compareSkillNames);
}

export function sortProjectSkills(skills: ProjectSkills): ProjectSkills {
  return {
    technology: sortSkillList(skills.technology),
    programming: sortSkillList(skills.programming),
    concepts: sortSkillList(skills.concepts),
  };
}

export function findDuplicateSkillNames(skills: ProjectSkills): string[] {
  const seen = new Map<string, string>();
  const duplicates = new Map<string, string>();

  for (const category of skillCategories) {
    for (const skill of skills[category]) {
      const trimmed = skill.trim();
      if (!trimmed) {
        continue;
      }

      const key = normalizeSkillName(trimmed);
      const firstSkill = seen.get(key);
      if (firstSkill) {
        duplicates.set(key, firstSkill);
      } else {
        seen.set(key, trimmed);
      }
    }
  }

  return sortSkillList(Array.from(duplicates.values()));
}
