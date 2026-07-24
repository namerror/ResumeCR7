import type { ResumeEvidenceRegistry } from "./types";

export function sampleEvidence(): ResumeEvidenceRegistry {
  return {
    education: {
      schema_version: 1,
      education: [
        {
          id: "example-university",
          name: "Example University",
          degree: "Bachelor of Science in Computer Science",
          grade: "3.8 GPA",
          start: "2020",
          end: "2024",
          location: "Example City, ST",
          relevant_coursework: ["Data Structures", "Algorithms"],
        },
      ],
    },
    experience: {
      schema_version: 1,
      experience: [
        {
          id: "backend-engineer",
          name: "Example Company",
          role: "Backend Engineer",
          summary: "Built backend services.",
          highlights: ["Designed schema-validated APIs."],
          active: true,
          skills: {
            technology: ["FastAPI"],
            programming: ["Python"],
            concepts: ["API"],
          },
          location: "Example City, ST",
          start: "2024",
          end: null,
          links: ["https://example.com/company"],
        },
      ],
    },
    projects: {
      schema_version: 1,
      projects: [
        {
          id: "resumecr7",
          name: "ResumeCR7",
          summary: "Grounded resume tooling.",
          highlights: ["Built deterministic evidence workflows."],
          active: true,
          skills: {
            technology: ["FastAPI"],
            programming: ["Python"],
            concepts: ["Schema validation"],
          },
          links: ["https://github.com/example/resumecr7"],
        },
      ],
    },
    skills: {
      schema_version: 1,
      skills: {
        technology: ["FastAPI"],
        programming: ["Python"],
        concepts: ["Schema validation"],
      },
    },
    user: {
      schema_version: 1,
      name: "Example Candidate",
      email: "candidate@example.com",
      phone: "+1 555-0100",
      linkedin: "https://www.linkedin.com/in/example-candidate",
      github: "https://github.com/example-candidate",
      website: null,
    },
  };
}
