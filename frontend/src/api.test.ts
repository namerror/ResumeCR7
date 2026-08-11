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
        run_id: "run-1",
        resume_result: {},
        resume_result_path: "user/resume_generation/resume_result.json",
        manifest_path: "user/resume_generation/resume_run_manifest.json",
        tex_path: "user/resume_generation/output/resume.tex",
        artifact_tex_path: "user/resume_generation/artifacts/resume.tex",
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

  it("reads generation status", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue({
        schema_version: 1,
        run_id: "run-1",
        operation: "tex",
        status: "running",
        started_at: "2026-08-11T12:00:00Z",
        completed_at: null,
        current_stage_id: "job_focus_generation",
        error: null,
        stages: [],
        job_focus: null,
      }),
    });
    const api = createEvidenceApi({
      baseUrl: "/api",
      fetchImpl: fetchMock as unknown as typeof fetch,
    });

    const status = await api.getResumeGenerationStatus();

    expect(status.status).toBe("running");
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/resume-generation/status",
      expect.objectContaining({}),
    );
  });

  it("returns pdf blobs from the pdf endpoint", async () => {
    const blob = new Blob(["%PDF-1.4\n"], { type: "application/pdf" });
    const headers = new Headers({
      "X-ResumeCR7-Tex-Path": "user/resume_generation/output/resume.tex",
      "X-ResumeCR7-Pdf-Path": "user/resume_generation/output/resume.pdf",
      "X-ResumeCR7-Artifact-Tex-Path": "user/resume_generation/artifacts/resume.tex",
      "X-ResumeCR7-Artifact-Pdf-Path": "user/resume_generation/artifacts/resume.pdf",
    });
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      headers,
      blob: vi.fn().mockResolvedValue(blob),
    });
    const api = createEvidenceApi({
      baseUrl: "/api",
      fetchImpl: fetchMock as unknown as typeof fetch,
    });

    const result = await api.generateResumePdf();

    expect(result).toEqual({
      blob,
      texPath: "user/resume_generation/output/resume.tex",
      pdfPath: "user/resume_generation/output/resume.pdf",
      artifactTexPath: "user/resume_generation/artifacts/resume.tex",
      artifactPdfPath: "user/resume_generation/artifacts/resume.pdf",
    });
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
      llm_provider: "openai" as const,
      bullet_point_generation_strategy: "section_batch" as const,
      skill_selection: { top_n: 20 },
      project_selection: { top_n: null },
      experience_selection: { top_n: null },
      link_scanning: { highlight_count: 6, max_tokens_per_highlight: 500 },
      bullet_count_range: null,
      openai_api_key_configured: false,
      openai_api_key_saved: false,
      openai_api_key_source: "none" as const,
      qwen_api_key_configured: false,
      qwen_api_key_saved: false,
      qwen_api_key_source: "none" as const,
      qwen_base_url: "https://dashscope-us.aliyuncs.com/compatible-mode/v1",
      github_token_configured: false,
      github_token_saved: false,
      github_token_source: "none" as const,
      display_defaults: {
        skill_selection_top_n: "20 (default)",
        project_selection_top_n: "unlimited (default)",
        experience_selection_top_n: "unlimited (default)",
        link_scanning_highlight_count: "6 (default)",
        link_scanning_max_tokens_per_highlight: "500 (default)",
        bullet_count_range: "3 to 3 (default)",
      },
      default_values: {
        skill_selection_top_n: 20,
        project_selection_top_n: null,
        experience_selection_top_n: null,
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
      llm_provider: "qwen",
      skill_selection: { top_n: 12 },
      openai: { api_key: "sk-test" },
      qwen: {
        api_key: "qwen-test",
        base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1",
      },
      github: { token: "github_pat_test" },
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
          llm_provider: "qwen",
          skill_selection: { top_n: 12 },
          openai: { api_key: "sk-test" },
          qwen: {
            api_key: "qwen-test",
            base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1",
          },
          github: { token: "github_pat_test" },
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
