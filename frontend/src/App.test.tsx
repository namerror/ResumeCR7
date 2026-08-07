import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import App from "./App";
import { ApiError } from "./api";
import type { EvidenceApi } from "./api";
import { cloneEvidence } from "./draft";
import { sampleEvidence, sampleGenerationConfig, sampleJobTarget } from "./testFixtures";

describe("App", () => {
  it("groups evidence tabs before generation and config tabs", async () => {
    const evidence = sampleEvidence();
    const client = createMockClient(evidence);

    render(<App client={client} />);

    const nav = await screen.findByRole("navigation", { name: "Evidence sections" });
    const labels = Array.from(nav.querySelectorAll(".nav-button span:nth-child(2)")).map(
      (element) => element.textContent,
    );

    expect(labels).toEqual([
      "User",
      "Skills",
      "Experience",
      "Projects",
      "Education",
      "Generate",
      "Config",
    ]);
  });

  it("orders main skills alphabetically in each category", async () => {
    const evidence = sampleEvidence();
    evidence.skills.skills.technology = ["Vite", "Docker", "API Gateway"];
    evidence.skills.skills.programming = ["TypeScript", "Python", "Go"];
    evidence.skills.skills.concepts = ["Schema validation", "Caching", "API design"];
    const client = createMockClient(evidence);

    render(<App client={client} />);

    fireEvent.click(await screen.findByRole("button", { name: "Skills" }));

    expect(skillInputValue("Technology 1")).toBe("API Gateway");
    expect(skillInputValue("Technology 2")).toBe("Docker");
    expect(skillInputValue("Technology 3")).toBe("Vite");
    expect(skillInputValue("Programming 1")).toBe("Go");
    expect(skillInputValue("Programming 2")).toBe("Python");
    expect(skillInputValue("Programming 3")).toBe("TypeScript");
    expect(skillInputValue("Concepts 1")).toBe("API design");
    expect(skillInputValue("Concepts 2")).toBe("Caching");
    expect(skillInputValue("Concepts 3")).toBe("Schema validation");
  });

  it("adds new main skill inputs at the top of the category", async () => {
    const evidence = sampleEvidence();
    evidence.skills.skills.technology = ["Vite", "Docker"];
    const client = createMockClient(evidence);

    render(<App client={client} />);

    fireEvent.click(await screen.findByRole("button", { name: "Skills" }));
    fireEvent.click(screen.getByRole("button", { name: "Add Technology" }));

    expect(skillInputValue("Technology 1")).toBe("");
    expect(skillInputValue("Technology 2")).toBe("Docker");
    expect(skillInputValue("Technology 3")).toBe("Vite");
    expect(document.activeElement).toBe(screen.getByLabelText("Technology 1"));
  });

  it("places a new main skill alphabetically after focus leaves the category", async () => {
    const evidence = sampleEvidence();
    evidence.skills.skills.technology = ["Docker", "Vite"];
    const client = createMockClient(evidence);

    render(<App client={client} />);

    fireEvent.click(await screen.findByRole("button", { name: "Skills" }));
    fireEvent.click(screen.getByRole("button", { name: "Add Technology" }));
    const newSkill = screen.getByLabelText("Technology 1");
    fireEvent.change(newSkill, { target: { value: "Terraform" } });
    fireEvent.blur(newSkill);

    expect(skillInputValue("Technology 1")).toBe("Docker");
    expect(skillInputValue("Technology 2")).toBe("Terraform");
    expect(skillInputValue("Technology 3")).toBe("Vite");
  });

  it("applies main skill edits with alphabetized category payloads", async () => {
    const evidence = sampleEvidence();
    evidence.skills.skills.technology = ["Vite", "Docker"];
    const reloaded = cloneEvidence(evidence);
    reloaded.skills.skills.technology = ["Ansible", "Docker", "Vite"];
    const client = createMockClient(evidence, reloaded);

    render(<App client={client} />);

    fireEvent.click(await screen.findByRole("button", { name: "Skills" }));
    fireEvent.click(screen.getByRole("button", { name: "Add Technology" }));
    const newSkill = screen.getByLabelText("Technology 1");
    fireEvent.change(newSkill, { target: { value: "Ansible" } });
    fireEvent.click(screen.getByRole("button", { name: /apply/i }));

    await waitFor(() => {
      expect(client.updateSkills).toHaveBeenCalledWith({
        skills: {
          technology: ["Ansible", "Docker", "Vite"],
          programming: ["Python"],
          concepts: ["Schema validation"],
        },
      });
    });
  });

  it("blocks repeated main skill names across categories ignoring case", async () => {
    const evidence = sampleEvidence();
    evidence.skills.skills.technology = ["NodeJS"];
    evidence.skills.skills.programming = [];
    const client = createMockClient(evidence);

    render(<App client={client} />);

    fireEvent.click(await screen.findByRole("button", { name: "Skills" }));
    fireEvent.click(screen.getByRole("button", { name: "Add Programming" }));
    const newSkill = screen.getByLabelText("Programming 1");
    fireEvent.change(newSkill, { target: { value: "nodejs" } });
    fireEvent.blur(newSkill);

    expect(await screen.findByText("Skills has duplicate skill name: NodeJS.")).toBeTruthy();
    expect((screen.getByRole("button", { name: /apply/i }) as HTMLButtonElement).disabled).toBe(
      true,
    );

    fireEvent.click(screen.getByRole("button", { name: /apply/i }));
    expect(client.updateSkills).not.toHaveBeenCalled();
  });

  it("stages user edits and applies them through the user endpoint", async () => {
    const evidence = sampleEvidence();
    const reloaded = cloneEvidence(evidence);
    reloaded.user.email = "updated@example.com";
    const client = createMockClient(evidence, reloaded);

    render(<App client={client} />);

    const emailInput = (await screen.findByLabelText("Email")) as HTMLInputElement;
    fireEvent.change(emailInput, { target: { value: "updated@example.com" } });

    const applyButton = screen.getByRole("button", { name: /apply/i }) as HTMLButtonElement;
    expect(applyButton.disabled).toBe(false);
    fireEvent.click(applyButton);

    await waitFor(() => {
      expect(client.updateUser).toHaveBeenCalledWith({
        name: "Example Candidate",
        email: "updated@example.com",
        phone: "+1 555-0100",
        linkedin: "https://www.linkedin.com/in/example-candidate",
        github: "https://github.com/example-candidate",
        website: null,
      });
    });
    expect(client.getResumeEvidence).toHaveBeenCalledTimes(2);
  });

  it("keeps new projects local until Apply is clicked", async () => {
    const evidence = sampleEvidence();
    const reloaded = cloneEvidence(evidence);
    reloaded.projects.projects.push({
      id: "portfolio-api",
      name: "Portfolio API",
      summary: "FastAPI portfolio service.",
      highlights: ["Built staged CRUD workflows."],
      active: true,
      skills: {
        technology: [],
        programming: [],
        concepts: [],
      },
      links: null,
    });
    const client = createMockClient(evidence, reloaded);

    render(<App client={client} />);

    fireEvent.click(await screen.findByRole("button", { name: "Projects" }));
    fireEvent.click(screen.getByRole("button", { name: "Add Project" }));
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Portfolio API" } });
    fireEvent.change(screen.getByLabelText("Summary"), {
      target: { value: "FastAPI portfolio service." },
    });
    fireEvent.change(screen.getByLabelText("Highlights 1"), {
      target: { value: "Built staged CRUD workflows." },
    });

    expect(client.createProject).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: /apply/i }));

    await waitFor(() => {
      expect(client.createProject).toHaveBeenCalledWith({
        name: "Portfolio API",
        summary: "FastAPI portfolio service.",
        highlights: ["Built staged CRUD workflows."],
        active: true,
        skills: {
          technology: [],
          programming: [],
          concepts: [],
        },
        links: null,
      });
    });
  });

  it("keeps project deletes local until Apply is clicked", async () => {
    const evidence = sampleEvidence();
    const reloaded = cloneEvidence(evidence);
    reloaded.projects.projects = [];
    const client = createMockClient(evidence, reloaded);

    render(<App client={client} />);

    fireEvent.click(await screen.findByRole("button", { name: "Projects" }));
    fireEvent.click(screen.getByLabelText("Delete ResumeCR7"));

    expect(client.deleteProject).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: /apply/i }));

    await waitFor(() => {
      expect(client.deleteProject).toHaveBeenCalledWith("resumecr7");
    });
  });

  it("blocks resume generation while evidence edits are staged", async () => {
    const evidence = sampleEvidence();
    const client = createMockClient(evidence);

    render(<App client={client} />);

    const emailInput = (await screen.findByLabelText("Email")) as HTMLInputElement;
    fireEvent.change(emailInput, { target: { value: "updated@example.com" } });
    fireEvent.click(screen.getByRole("button", { name: "Generate" }));

    const generateTexButton = screen.getByRole("button", {
      name: "Generate .tex",
    }) as HTMLButtonElement;
    expect(generateTexButton.disabled).toBe(true);
    expect(client.generateResumeTex).not.toHaveBeenCalled();
  });

  it("loads the saved job target into the generate panel", async () => {
    const evidence = sampleEvidence();
    const jobTarget = sampleJobTarget();
    const client = createMockClient(
      evidence,
      evidence,
      sampleGenerationConfig(),
      sampleGenerationConfig(),
      jobTarget,
    );

    render(<App client={client} />);

    fireEvent.click(await screen.findByRole("button", { name: "Generate" }));

    expect((screen.getByLabelText("Job Title") as HTMLInputElement).value).toBe(
      "Backend Engineer",
    );
    expect((screen.getByLabelText("Job Description") as HTMLTextAreaElement).value).toBe(
      "Build Python APIs.",
    );
  });

  it("applies job target edits through the job target endpoint", async () => {
    const evidence = sampleEvidence();
    const jobTarget = sampleJobTarget();
    const reloadedJobTarget = {
      ...jobTarget,
      title: "Frontend Engineer",
      description: "Build React interfaces.",
    };
    const client = createMockClient(
      evidence,
      evidence,
      sampleGenerationConfig(),
      sampleGenerationConfig(),
      jobTarget,
      reloadedJobTarget,
    );

    render(<App client={client} />);

    fireEvent.click(await screen.findByRole("button", { name: "Generate" }));
    fireEvent.change(screen.getByLabelText("Job Title"), {
      target: { value: " Frontend Engineer " },
    });
    fireEvent.change(screen.getByLabelText("Job Description"), {
      target: { value: " Build React interfaces. " },
    });
    fireEvent.click(screen.getByRole("button", { name: /apply/i }));

    await waitFor(() => {
      expect(client.updateJobTarget).toHaveBeenCalledWith({
        schema_version: 1,
        title: "Frontend Engineer",
        description: "Build React interfaces.",
      });
    });
  });

  it("generates tex with the saved job target", async () => {
    const evidence = sampleEvidence();
    const client = createMockClient(evidence);

    render(<App client={client} />);

    fireEvent.click(await screen.findByRole("button", { name: "Generate" }));
    fireEvent.click(screen.getByRole("button", { name: "Generate .tex" }));

    await waitFor(() => {
      expect(client.generateResumeTex).toHaveBeenCalledWith({});
    });
  });

  it("shows a short pdf prerequisite message when no tex exists", async () => {
    const evidence = sampleEvidence();
    const client = createMockClient(evidence);
    (client.generateResumePdf as ReturnType<typeof vi.fn>).mockRejectedValue(
      new ApiError(404, "missing tex"),
    );

    render(<App client={client} />);

    fireEvent.click(await screen.findByRole("button", { name: "Generate" }));
    fireEvent.click(screen.getByRole("button", { name: "Generate PDF" }));

    expect(await screen.findByText("Generate the .tex file first.")).toBeTruthy();
  });

  it("shows a short pdf dependency message when latex prerequisites are missing", async () => {
    const evidence = sampleEvidence();
    const client = createMockClient(evidence);
    (client.generateResumePdf as ReturnType<typeof vi.fn>).mockRejectedValue(
      new ApiError(
        502,
        "PDF rendering prerequisites are missing. Install latexmk and TeX Live packages.",
      ),
    );

    render(<App client={client} />);

    fireEvent.click(await screen.findByRole("button", { name: "Generate" }));
    fireEvent.click(screen.getByRole("button", { name: "Generate PDF" }));

    expect(
      await screen.findByText(
        "PDF rendering dependencies are missing. On Ubuntu/Debian, run resumecr7-install-pdf-dependencies.sh, then try Generate PDF again.",
      ),
    ).toBeTruthy();
  });

  it("enriches the selected project through targeted link scanning", async () => {
    const evidence = sampleEvidence();
    const reloaded = cloneEvidence(evidence);
    reloaded.projects.projects[0].highlights.push("Scanned project detail.");
    const client = createMockClient(evidence, reloaded);

    render(<App client={client} />);

    fireEvent.click(await screen.findByRole("button", { name: "Projects" }));
    fireEvent.click(screen.getByRole("button", { name: "Enrich with link scanning" }));

    await waitFor(() => {
      expect(client.enrichResumeLinkEvidence).toHaveBeenCalledWith({
        evidence_type: "projects",
        evidence_id: "resumecr7",
        dry_run: false,
      });
    });
    expect(client.getResumeEvidence).toHaveBeenCalledTimes(2);
  });

  it("enriches the selected experience through targeted link scanning", async () => {
    const evidence = sampleEvidence();
    const reloaded = cloneEvidence(evidence);
    reloaded.experience.experience[0].highlights.push("Scanned experience detail.");
    const client = createMockClient(evidence, reloaded);

    render(<App client={client} />);

    fireEvent.click(await screen.findByRole("button", { name: "Experience" }));
    fireEvent.click(screen.getByRole("button", { name: "Enrich with link scanning" }));

    await waitFor(() => {
      expect(client.enrichResumeLinkEvidence).toHaveBeenCalledWith({
        evidence_type: "experience",
        evidence_id: "backend-engineer",
        dry_run: false,
      });
    });
    expect(client.getResumeEvidence).toHaveBeenCalledTimes(2);
  });

  it("shows config defaults for null values", async () => {
    const evidence = sampleEvidence();
    const config = sampleGenerationConfig();
    const client = createMockClient(evidence, evidence, config);

    render(<App client={client} />);

    fireEvent.click(await screen.findByRole("button", { name: "Config" }));

    expect(screen.getAllByText("unlimited (default)").length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText("3 to 3 (default)").length).toBeGreaterThan(0);
    expect((screen.getByLabelText("OpenAI API Key") as HTMLInputElement).type).toBe("password");
    expect((screen.getByLabelText("OpenAI API Key") as HTMLInputElement).value).toBe("");
    expect((screen.getByLabelText("GitHub Token") as HTMLInputElement).type).toBe("password");
    expect((screen.getByLabelText("GitHub Token") as HTMLInputElement).value).toBe("");
  });

  it("applies exposed config edits and changed OpenAI keys", async () => {
    const evidence = sampleEvidence();
    const config = sampleGenerationConfig();
    const reloadedConfig = cloneEvidence(config);
    reloadedConfig.skill_selection.top_n = 12;
    reloadedConfig.project_selection.top_n = 3;
    reloadedConfig.experience_selection.top_n = 2;
    reloadedConfig.resume_output.output_dir = "user/resume_generation/final";
    reloadedConfig.openai_api_key_configured = true;
    reloadedConfig.openai_api_key_saved = true;
    reloadedConfig.openai_api_key_source = "config";
    reloadedConfig.github_token_configured = true;
    reloadedConfig.github_token_saved = true;
    reloadedConfig.github_token_source = "config";
    const client = createMockClient(evidence, evidence, config, reloadedConfig);

    render(<App client={client} />);

    fireEvent.click(await screen.findByRole("button", { name: "Config" }));
    fireEvent.change(
      screen.getByLabelText("# of skills to display in the skills section per category"),
      { target: { value: "12" } },
    );
    fireEvent.change(screen.getByLabelText("# of projects to select for the resume"), {
      target: { value: "3" },
    });
    fireEvent.change(screen.getByLabelText("# of experience entries to include in the resume"), {
      target: { value: "2" },
    });
    fireEvent.change(screen.getByLabelText("Resume output directory"), {
      target: { value: "user/resume_generation/final" },
    });
    fireEvent.change(screen.getByLabelText("OpenAI API Key"), {
      target: { value: "sk-test" },
    });
    fireEvent.change(screen.getByLabelText("GitHub Token"), {
      target: { value: "github_pat_test" },
    });
    fireEvent.click(screen.getByRole("button", { name: /apply/i }));

    await waitFor(() => {
      expect(client.updateGenerationConfig).toHaveBeenCalledWith({
        skill_selection: { top_n: 12 },
        project_selection: { top_n: 3 },
        experience_selection: { top_n: 2 },
        resume_output: { output_dir: "user/resume_generation/final" },
        openai: { api_key: "sk-test" },
        github: { token: "github_pat_test" },
      });
    });
  });

  it("blocks invalid bullet count ranges before applying config", async () => {
    const evidence = sampleEvidence();
    const config = sampleGenerationConfig();
    const client = createMockClient(evidence, evidence, config);

    render(<App client={client} />);

    fireEvent.click(await screen.findByRole("button", { name: "Config" }));
    fireEvent.change(await screen.findByLabelText("Bullet count lower bound"), {
      target: { value: "5" },
    });
    fireEvent.change(screen.getByLabelText("Bullet count upper bound"), {
      target: { value: "2" },
    });

    expect(
      await screen.findByText(
        "Bullet count lower bound must be less than or equal to upper bound.",
      ),
    ).toBeTruthy();
    expect((screen.getByRole("button", { name: /apply/i }) as HTMLButtonElement).disabled).toBe(
      true,
    );
    expect(client.updateGenerationConfig).not.toHaveBeenCalled();
  });
});

function skillInputValue(label: string): string {
  return (screen.getByLabelText(label) as HTMLInputElement).value;
}

function createMockClient(
  initial = sampleEvidence(),
  reloaded = initial,
  initialConfig = sampleGenerationConfig(),
  reloadedConfig = initialConfig,
  initialJobTarget = sampleJobTarget(),
  reloadedJobTarget = initialJobTarget,
): EvidenceApi & Record<string, ReturnType<typeof vi.fn>> {
  return {
    getHealth: vi.fn().mockResolvedValue({ status: "ok" }),
    getResumeEvidence: vi
      .fn()
      .mockResolvedValueOnce(cloneEvidence(initial))
      .mockResolvedValue(cloneEvidence(reloaded)),
    getGenerationConfig: vi
      .fn()
      .mockResolvedValueOnce(cloneEvidence(initialConfig))
      .mockResolvedValue(cloneEvidence(reloadedConfig)),
    getJobTarget: vi
      .fn()
      .mockResolvedValueOnce(cloneEvidence(initialJobTarget))
      .mockResolvedValue(cloneEvidence(reloadedJobTarget)),
    getProjects: vi.fn(),
    createProject: vi.fn().mockResolvedValue(reloaded.projects.projects.at(-1)),
    updateProject: vi.fn(),
    deleteProject: vi.fn().mockResolvedValue(initial.projects.projects[0]),
    getExperience: vi.fn(),
    createExperience: vi.fn(),
    updateExperience: vi.fn(),
    deleteExperience: vi.fn(),
    getEducation: vi.fn(),
    createEducation: vi.fn(),
    updateEducation: vi.fn(),
    deleteEducation: vi.fn(),
    updateSkills: vi.fn(),
    updateUser: vi.fn().mockResolvedValue(reloaded.user),
    generateResumeTex: vi.fn().mockResolvedValue({
      resume_result: {},
      resume_result_path: "user/resume_generation/resume_result.json",
      manifest_path: "user/resume_generation/resume_run_manifest.json",
      tex_path: "user/resume_generation/output/resume.tex",
      artifact_tex_path: "user/resume_generation/artifacts/resume.tex",
      tex_content: "tex",
    }),
    generateResumePdf: vi.fn().mockResolvedValue({
      blob: new Blob(["%PDF-1.4\n"], { type: "application/pdf" }),
      texPath: "user/resume_generation/output/resume.tex",
      pdfPath: "user/resume_generation/output/resume.pdf",
      artifactTexPath: "user/resume_generation/artifacts/resume.tex",
      artifactPdfPath: "user/resume_generation/artifacts/resume.pdf",
    }),
    enrichResumeLinkEvidence: vi.fn().mockResolvedValue({
      dry_run: false,
      scanned_count: 1,
      total_added_highlights: 1,
      updated_paths: ["user/resume_evidence/projects.yaml"],
      records: [],
    }),
    updateGenerationConfig: vi.fn().mockResolvedValue(cloneEvidence(reloadedConfig)),
    updateJobTarget: vi.fn().mockResolvedValue(cloneEvidence(reloadedJobTarget)),
  };
}
