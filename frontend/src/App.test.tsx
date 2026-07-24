import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import App from "./App";
import { ApiError } from "./api";
import type { EvidenceApi } from "./api";
import { cloneEvidence } from "./draft";
import { sampleEvidence } from "./testFixtures";

describe("App", () => {
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

  it("generates tex with a job target override", async () => {
    const evidence = sampleEvidence();
    const client = createMockClient(evidence);

    render(<App client={client} />);

    fireEvent.click(await screen.findByRole("button", { name: "Generate" }));
    fireEvent.change(screen.getByLabelText("Job Title"), {
      target: { value: "Frontend Engineer" },
    });
    fireEvent.change(screen.getByLabelText("Job Description"), {
      target: { value: "Build React interfaces." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Generate .tex" }));

    await waitFor(() => {
      expect(client.generateResumeTex).toHaveBeenCalledWith({
        job_target: {
          schema_version: 1,
          title: "Frontend Engineer",
          description: "Build React interfaces.",
        },
      });
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
});

function createMockClient(
  initial = sampleEvidence(),
  reloaded = initial,
): EvidenceApi & Record<string, ReturnType<typeof vi.fn>> {
  return {
    getHealth: vi.fn().mockResolvedValue({ status: "ok" }),
    getResumeEvidence: vi
      .fn()
      .mockResolvedValueOnce(cloneEvidence(initial))
      .mockResolvedValue(cloneEvidence(reloaded)),
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
      tex_path: "user/resume_generation/resume.tex",
      tex_content: "tex",
    }),
    generateResumePdf: vi.fn().mockResolvedValue(
      new Blob(["%PDF-1.4\n"], { type: "application/pdf" }),
    ),
    enrichResumeLinkEvidence: vi.fn().mockResolvedValue({
      dry_run: false,
      scanned_count: 1,
      total_added_highlights: 1,
      updated_paths: ["user/resume_evidence/projects.yaml"],
      records: [],
    }),
  };
}
