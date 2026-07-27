import { describe, expect, it, vi } from "vitest";

import { ApiError, createEvidenceApi } from "./api";

describe("evidence api client", () => {
  it("updates project records through the ID route with an ID-free payload", async () => {
    const payload = {
      name: "ResumeCR7",
      summary: "Updated summary.",
      highlights: ["Built APIs."],
      active: true,
      skills: {
        technology: ["FastAPI"],
        programming: ["Python"],
        concepts: ["API"],
      },
      links: null,
    };
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue({ id: "resumecr7", ...payload }),
    });
    const api = createEvidenceApi({
      baseUrl: "http://127.0.0.1:8000",
      fetchImpl: fetchMock as unknown as typeof fetch,
    });

    await api.updateProject("resumecr7", payload);

    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/resume-evidence/projects/resumecr7",
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify(payload),
      }),
    );
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).not.toHaveProperty("id");
  });

  it("surfaces FastAPI error details", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 400,
      statusText: "Bad Request",
      json: vi.fn().mockResolvedValue({ detail: "invalid evidence" }),
    });
    const api = createEvidenceApi({
      baseUrl: "/api",
      fetchImpl: fetchMock as unknown as typeof fetch,
    });

    await expect(api.getResumeEvidence()).rejects.toEqual(new ApiError(400, "invalid evidence"));
  });

  it("posts job target overrides when generating tex", async () => {
    const payload = {
      job_target: {
        schema_version: 1 as const,
        title: "Frontend Engineer",
        description: "Build React interfaces.",
      },
    };
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue({
        resume_result: {},
        resume_result_path: "user/resume_generation/resume_result.json",
        manifest_path: "user/resume_generation/resume_run_manifest.json",
        tex_path: "user/resume_generation/resume.tex",
        tex_content: "tex",
      }),
    });
    const api = createEvidenceApi({
      baseUrl: "/api",
      fetchImpl: fetchMock as unknown as typeof fetch,
    });

    await api.generateResumeTex(payload);

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/resume-generation/tex",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify(payload),
      }),
    );
  });

  it("returns pdf blobs from the pdf endpoint", async () => {
    const blob = new Blob(["%PDF-1.4\n"], { type: "application/pdf" });
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      blob: vi.fn().mockResolvedValue(blob),
    });
    const api = createEvidenceApi({
      baseUrl: "/api",
      fetchImpl: fetchMock as unknown as typeof fetch,
    });

    const result = await api.generateResumePdf();

    expect(result).toBe(blob);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/resume-generation/pdf",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({}),
      }),
    );
  });

  it("posts targeted resume link enrichment requests", async () => {
    const payload = {
      evidence_type: "projects" as const,
      evidence_id: "resumecr7",
      dry_run: false,
    };
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue({
        dry_run: false,
        scanned_count: 1,
        total_added_highlights: 1,
        updated_paths: ["user/resume_evidence/projects.yaml"],
        records: [],
      }),
    });
    const api = createEvidenceApi({
      baseUrl: "/api",
      fetchImpl: fetchMock as unknown as typeof fetch,
    });

    await api.enrichResumeLinkEvidence(payload);

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/resume-generation/enrich-link-evidence",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify(payload),
      }),
    );
  });

  it("reads and patches generation config", async () => {
    const configPayload = {
      schema_version: 1 as const,
      config_path: "user/resume_generation/config.yaml",
      skill_selection: { top_n: 20 },
      project_selection: { top_n: null },
      link_scanning: { highlight_count: 6, max_tokens_per_highlight: 500 },
      bullet_count_range: null,
      openai_api_key_configured: false,
      openai_api_key_saved: false,
      openai_api_key_source: "none" as const,
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
        bullet_count_range: { min: 3, max: 3 },
      },
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: vi.fn().mockResolvedValue(configPayload),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: vi.fn().mockResolvedValue({
          ...configPayload,
          skill_selection: { top_n: 12 },
        }),
      });
    const api = createEvidenceApi({
      baseUrl: "/api",
      fetchImpl: fetchMock as unknown as typeof fetch,
    });

    await api.getGenerationConfig();
    await api.updateGenerationConfig({
      skill_selection: { top_n: 12 },
      openai: { api_key: "sk-test" },
    });

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/api/resume-generation/config",
      expect.objectContaining({ headers: expect.any(Headers) }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/api/resume-generation/config",
      expect.objectContaining({
        method: "PATCH",
        body: JSON.stringify({
          skill_selection: { top_n: 12 },
          openai: { api_key: "sk-test" },
        }),
      }),
    );
  });

  it("reads and updates the saved job target", async () => {
    const jobTargetPayload = {
      schema_version: 1 as const,
      title: "Backend Engineer",
      description: "Build Python APIs.",
      job_target_path: "user/resume_generation/job_target.yaml",
    };
    const updatePayload = {
      schema_version: 1 as const,
      title: "Frontend Engineer",
      description: "Build React interfaces.",
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: vi.fn().mockResolvedValue(jobTargetPayload),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: vi.fn().mockResolvedValue({
          ...updatePayload,
          job_target_path: jobTargetPayload.job_target_path,
        }),
      });
    const api = createEvidenceApi({
      baseUrl: "/api",
      fetchImpl: fetchMock as unknown as typeof fetch,
    });

    await api.getJobTarget();
    await api.updateJobTarget(updatePayload);

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/api/resume-generation/job-target",
      expect.objectContaining({ headers: expect.any(Headers) }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/api/resume-generation/job-target",
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify(updatePayload),
      }),
    );
  });
});
