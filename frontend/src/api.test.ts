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
});
