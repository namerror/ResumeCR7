import type {
  EducationFile,
  EducationRecord,
  EducationRecordInput,
  ExperienceFile,
  ExperienceRecord,
  ExperienceRecordInput,
  JobTarget,
  JobTargetResponse,
  ProjectRecord,
  ProjectRecordInput,
  ProjectsFile,
  ResumeLinkEnrichmentRequest,
  ResumeLinkEnrichmentResponse,
  ResumeEvidenceRegistry,
  ResumeGenerationConfig,
  ResumeGenerationConfigPatch,
  ResumeTexGenerationRequest,
  ResumeTexGenerationResponse,
  SkillsFile,
  SkillsInput,
  UserInfoFile,
  UserInfoInput,
} from "./types";

export interface BackendHealth {
  status: string;
  version?: string;
  service?: string;
}

export interface EvidenceApi {
  getHealth(): Promise<BackendHealth>;
  getResumeEvidence(): Promise<ResumeEvidenceRegistry>;
  getProjects(): Promise<ProjectsFile>;
  createProject(payload: ProjectRecordInput): Promise<ProjectRecord>;
  updateProject(id: string, payload: ProjectRecordInput): Promise<ProjectRecord>;
  deleteProject(id: string): Promise<ProjectRecord>;
  getExperience(): Promise<ExperienceFile>;
  createExperience(payload: ExperienceRecordInput): Promise<ExperienceRecord>;
  updateExperience(id: string, payload: ExperienceRecordInput): Promise<ExperienceRecord>;
  deleteExperience(id: string): Promise<ExperienceRecord>;
  getEducation(): Promise<EducationFile>;
  createEducation(payload: EducationRecordInput): Promise<EducationRecord>;
  updateEducation(id: string, payload: EducationRecordInput): Promise<EducationRecord>;
  deleteEducation(id: string): Promise<EducationRecord>;
  updateSkills(payload: SkillsInput): Promise<SkillsFile>;
  updateUser(payload: UserInfoInput): Promise<UserInfoFile>;
  generateResumeTex(payload?: ResumeTexGenerationRequest): Promise<ResumeTexGenerationResponse>;
  generateResumePdf(): Promise<Blob>;
  enrichResumeLinkEvidence(
    payload: ResumeLinkEnrichmentRequest,
  ): Promise<ResumeLinkEnrichmentResponse>;
  getGenerationConfig(): Promise<ResumeGenerationConfig>;
  updateGenerationConfig(
    payload: ResumeGenerationConfigPatch,
  ): Promise<ResumeGenerationConfig>;
  getJobTarget(): Promise<JobTargetResponse>;
  updateJobTarget(payload: JobTarget): Promise<JobTargetResponse>;
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly detail: string,
  ) {
    super(detail);
    this.name = "ApiError";
  }
}

interface ApiOptions {
  baseUrl?: string;
  fetchImpl?: typeof fetch;
}

const defaultBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim() || "/api";

export function createEvidenceApi(options: ApiOptions = {}): EvidenceApi {
  const baseUrl = stripTrailingSlash(options.baseUrl ?? defaultBaseUrl);
  const fetchImpl = options.fetchImpl ?? fetch;

  async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const headers = new Headers(init.headers);
    if (init.body && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }

    const response = await fetchImpl(`${baseUrl}${path}`, {
      ...init,
      headers,
    });

    if (!response.ok) {
      throw new ApiError(response.status, await readErrorDetail(response));
    }

    return (await response.json()) as T;
  }

  async function requestBlob(path: string, init: RequestInit = {}): Promise<Blob> {
    const headers = new Headers(init.headers);
    if (init.body && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }

    const response = await fetchImpl(`${baseUrl}${path}`, {
      ...init,
      headers,
    });

    if (!response.ok) {
      throw new ApiError(response.status, await readErrorDetail(response));
    }

    return response.blob();
  }

  return {
    getHealth: () => request<BackendHealth>("/health"),
    getResumeEvidence: () => request<ResumeEvidenceRegistry>("/resume-evidence"),
    getProjects: () => request<ProjectsFile>("/resume-evidence/projects"),
    createProject: (payload) =>
      request<ProjectRecord>("/resume-evidence/projects", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    updateProject: (id, payload) =>
      request<ProjectRecord>(`/resume-evidence/projects/${encodeURIComponent(id)}`, {
        method: "PUT",
        body: JSON.stringify(payload),
      }),
    deleteProject: (id) =>
      request<ProjectRecord>(`/resume-evidence/projects/${encodeURIComponent(id)}`, {
        method: "DELETE",
      }),
    getExperience: () => request<ExperienceFile>("/resume-evidence/experience"),
    createExperience: (payload) =>
      request<ExperienceRecord>("/resume-evidence/experience", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    updateExperience: (id, payload) =>
      request<ExperienceRecord>(`/resume-evidence/experience/${encodeURIComponent(id)}`, {
        method: "PUT",
        body: JSON.stringify(payload),
      }),
    deleteExperience: (id) =>
      request<ExperienceRecord>(`/resume-evidence/experience/${encodeURIComponent(id)}`, {
        method: "DELETE",
      }),
    getEducation: () => request<EducationFile>("/resume-evidence/education"),
    createEducation: (payload) =>
      request<EducationRecord>("/resume-evidence/education", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    updateEducation: (id, payload) =>
      request<EducationRecord>(`/resume-evidence/education/${encodeURIComponent(id)}`, {
        method: "PUT",
        body: JSON.stringify(payload),
      }),
    deleteEducation: (id) =>
      request<EducationRecord>(`/resume-evidence/education/${encodeURIComponent(id)}`, {
        method: "DELETE",
      }),
    updateSkills: (payload) =>
      request<SkillsFile>("/resume-evidence/skills", {
        method: "PUT",
        body: JSON.stringify(payload),
      }),
    updateUser: (payload) =>
      request<UserInfoFile>("/resume-evidence/user", {
        method: "PUT",
        body: JSON.stringify(payload),
      }),
    generateResumeTex: (payload = {}) =>
      request<ResumeTexGenerationResponse>("/resume-generation/tex", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    generateResumePdf: () =>
      requestBlob("/resume-generation/pdf", {
        method: "POST",
        body: JSON.stringify({}),
      }),
    enrichResumeLinkEvidence: (payload) =>
      request<ResumeLinkEnrichmentResponse>("/resume-generation/enrich-link-evidence", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    getGenerationConfig: () => request<ResumeGenerationConfig>("/resume-generation/config"),
    updateGenerationConfig: (payload) =>
      request<ResumeGenerationConfig>("/resume-generation/config", {
        method: "PATCH",
        body: JSON.stringify(payload),
      }),
    getJobTarget: () => request<JobTargetResponse>("/resume-generation/job-target"),
    updateJobTarget: (payload) =>
      request<JobTargetResponse>("/resume-generation/job-target", {
        method: "PUT",
        body: JSON.stringify(payload),
      }),
  };
}

async function readErrorDetail(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as { detail?: unknown };
    if (typeof payload.detail === "string") {
      return payload.detail;
    }
    if (payload.detail) {
      return JSON.stringify(payload.detail);
    }
  } catch {
    // Fall through to status text.
  }
  return response.statusText || `Request failed with ${response.status}`;
}

function stripTrailingSlash(value: string): string {
  return value.replace(/\/+$/, "");
}

export const evidenceApi = createEvidenceApi();
