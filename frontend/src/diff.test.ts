import { describe, expect, it } from "vitest";

import { buildApplyOperations, toProjectInput } from "./diff";
import { cloneEvidence, createBlankProject } from "./draft";
import { sampleEvidence } from "./testFixtures";

describe("resume evidence apply diff", () => {
  it("creates singleton and collection operations without sending record ids", () => {
    const baseline = sampleEvidence();
    const draft = cloneEvidence(baseline);
    const newProject = {
      ...createBlankProject(),
      name: "Portfolio API",
      summary: "FastAPI portfolio service.",
      highlights: ["Built staged CRUD workflows."],
      skills: {
        technology: ["FastAPI"],
        programming: ["TypeScript"],
        concepts: ["REST API"],
      },
      links: null,
    };

    draft.user.email = "updated@example.com";
    draft.projects.projects[0].summary = "Updated grounded resume tooling.";
    draft.projects.projects.push(newProject);
    draft.experience.experience = [];

    const operations = buildApplyOperations(baseline, draft);

    expect(operations).toEqual([
      {
        action: "update",
        resource: "user",
        payload: {
          name: "Example Candidate",
          email: "updated@example.com",
          phone: "+1 555-0100",
          linkedin: "https://www.linkedin.com/in/example-candidate",
          github: "https://github.com/example-candidate",
          website: null,
        },
      },
      {
        action: "update",
        resource: "projects",
        id: "resumecr7",
        payload: {
          name: "ResumeCR7",
          summary: "Updated grounded resume tooling.",
          highlights: ["Built deterministic evidence workflows."],
          active: true,
          skills: {
            technology: ["FastAPI"],
            programming: ["Python"],
            concepts: ["Schema validation"],
          },
          links: ["https://github.com/example/resumecr7"],
        },
      },
      {
        action: "create",
        resource: "projects",
        payload: {
          name: "Portfolio API",
          summary: "FastAPI portfolio service.",
          highlights: ["Built staged CRUD workflows."],
          active: true,
          skills: {
            technology: ["FastAPI"],
            programming: ["TypeScript"],
            concepts: ["REST API"],
          },
          links: null,
        },
      },
      {
        action: "delete",
        resource: "experience",
        id: "backend-engineer",
      },
    ]);
    expect(JSON.stringify(operations)).not.toContain(newProject.id);
  });

  it("strips ids from project update payloads", () => {
    const project = sampleEvidence().projects.projects[0];

    expect(toProjectInput(project)).not.toHaveProperty("id");
  });
});
