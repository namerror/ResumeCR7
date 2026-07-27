import type { JobTargetResponse, ResumeEvidenceRegistry, ResumeGenerationConfig } from "./types";

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

export function sampleGenerationConfig(): ResumeGenerationConfig {
  return {
    schema_version: 1,
    config_path: "user/resume_generation/config.yaml",
    skill_selection: {
      top_n: 20,
    },
    project_selection: {
      top_n: null,
    },
    link_scanning: {
      highlight_count: 6,
      max_tokens_per_highlight: 500,
    },
    bullet_count_range: null,
    openai_api_key_configured: false,
    openai_api_key_saved: false,
    openai_api_key_source: "none",
    display_defaults: {
      skill_selection_top_n: "20 (default)",
      project_selection_top_n: "unlimited (default)",
      link_scanning_highlight_count: "6 (default)",
      link_scanning_max_tokens_per_highlight: "500 (default)",
      bullet_count_range: "3 to 3 (default)",
    },
    default_values: {
      skill_selection_top_n: 20,
      project_selection_top_n: null,
      link_scanning_highlight_count: 6,
      link_scanning_max_tokens_per_highlight: 500,
      bullet_count_range: {
        min: 3,
        max: 3,
      },
    },
  };
}

export function sampleJobTarget(): JobTargetResponse {
  return {
    schema_version: 1,
    title: "Backend Engineer",
    description: "Build Python APIs.",
    job_target_path: "user/resume_generation/job_target.yaml",
  };
}
