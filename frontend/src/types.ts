export const skillCategories = ["technology", "programming", "concepts"] as const;

export type SkillCategory = (typeof skillCategories)[number];

export interface ProjectSkills {
  technology: string[];
  programming: string[];
  concepts: string[];
}

export interface ProjectRecordInput {
  name: string;
  summary: string;
  highlights: string[];
  active: boolean;
  skills: ProjectSkills;
  links: string[] | null;
}

export interface ProjectRecord extends ProjectRecordInput {
  id: string;
}

export interface ProjectsFile {
  schema_version: 1;
  projects: ProjectRecord[];
}

export interface ExperienceRecordInput {
  name: string;
  role: string;
  summary: string;
  highlights: string[];
  active: boolean;
  skills: ProjectSkills;
  location: string;
  start: string;
  end: string | null;
  links: string[] | null;
}

export interface ExperienceRecord extends ExperienceRecordInput {
  id: string;
}

export interface ExperienceFile {
  schema_version: 1;
  experience: ExperienceRecord[];
}

export interface EducationRecordInput {
  name: string;
  degree: string;
  grade: string;
  start: string;
  end: string | null;
  location: string;
  relevant_coursework: string[];
}

export interface EducationRecord extends EducationRecordInput {
  id: string;
}

export interface EducationFile {
  schema_version: 1;
  education: EducationRecord[];
}

export interface SkillsFile {
  schema_version: 1;
  skills: ProjectSkills;
}

export interface SkillsInput {
  skills: ProjectSkills;
}

export interface UserInfoInput {
  name: string;
  email: string;
  phone: string;
  linkedin: string | null;
  github: string | null;
  website: string | null;
}

export interface UserInfoFile extends UserInfoInput {
  schema_version: 1;
}

export interface ResumeEvidenceRegistry {
  education: EducationFile;
  experience: ExperienceFile;
  projects: ProjectsFile;
  skills: SkillsFile;
  user: UserInfoFile;
}

export type CollectionRecord = ProjectRecord | ExperienceRecord | EducationRecord;

export interface JobTarget {
  schema_version: 1;
  title: string;
  description: string | null;
}

export interface JobTargetResponse extends JobTarget {
  job_target_path: string;
}

export interface ResumeTexGenerationRequest {
  job_target?: JobTarget | null;
}

export interface ResumeTexGenerationResponse {
  run_id: string;
  resume_result: unknown;
  resume_result_path: string;
  manifest_path: string;
  tex_path: string;
  artifact_tex_path: string;
  tex_content: string;
}

export type ResumeLinkEnrichmentEvidenceType = "projects" | "experience" | "all";

export interface ResumeLinkEnrichmentRequest {
  evidence_type: ResumeLinkEnrichmentEvidenceType;
  evidence_id?: string | null;
  dry_run?: boolean;
  dev_mode?: boolean | null;
  llm_model?: string | null;
  llm_max_output_tokens?: number | null;
  highlight_count?: number | null;
  max_tokens_per_highlight?: number | null;
}

export interface ResumeLinkEnrichmentRecordResponse {
  evidence_type: "project" | "experience";
  evidence_id: string;
  name: string;
  scanned: boolean;
  added_highlights: string[];
  skipped_reason: string | null;
  details: Record<string, unknown> | null;
}

export interface ResumeLinkEnrichmentResponse {
  dry_run: boolean;
  scanned_count: number;
  total_added_highlights: number;
  updated_paths: string[];
  records: ResumeLinkEnrichmentRecordResponse[];
}

export interface ConfigTopNValues {
  top_n: number | null;
}

export interface ConfigLinkScanningValues {
  highlight_count: number | null;
  max_tokens_per_highlight: number | null;
}

export interface BulletCountRangeConfig {
  min: number;
  max: number;
}

export type OpenAIApiKeySource = "environment" | "config" | "none";
export type LLMProvider = "openai" | "qwen";
export type GitHubTokenSource = "environment" | "config" | "none";
export type BulletPointGenerationStrategy = "section_batch" | "per_record";

export interface ConfigDisplayDefaults {
  skill_selection_top_n: string;
  project_selection_top_n: string;
  experience_selection_top_n: string;
  link_scanning_highlight_count: string;
  link_scanning_max_tokens_per_highlight: string;
  bullet_count_range: string;
}

export interface ConfigDefaultValues {
  skill_selection_top_n: number;
  project_selection_top_n: number | null;
  experience_selection_top_n: number | null;
  link_scanning_highlight_count: number;
  link_scanning_max_tokens_per_highlight: number;
  bullet_count_range: BulletCountRangeConfig;
}

export interface ConfigResumeOutputValues {
  output_dir: string;
  tex_path: string;
  pdf_path: string;
  artifact_tex_path: string;
  artifact_pdf_path: string;
}

export interface ResumeGenerationConfig {
  schema_version: 1;
  config_path: string;
  llm_provider: LLMProvider;
  bullet_point_generation_strategy: BulletPointGenerationStrategy;
  skill_selection: ConfigTopNValues;
  project_selection: ConfigTopNValues;
  experience_selection: ConfigTopNValues;
  link_scanning: ConfigLinkScanningValues;
  resume_output: ConfigResumeOutputValues;
  bullet_count_range: BulletCountRangeConfig | null;
  openai_api_key_configured: boolean;
  openai_api_key_saved: boolean;
  openai_api_key_source: OpenAIApiKeySource;
  qwen_api_key_configured: boolean;
  qwen_api_key_saved: boolean;
  qwen_api_key_source: OpenAIApiKeySource;
  qwen_base_url: string;
  github_token_configured: boolean;
  github_token_saved: boolean;
  github_token_source: GitHubTokenSource;
  display_defaults: ConfigDisplayDefaults;
  default_values: ConfigDefaultValues;
}

export interface ResumeGenerationConfigPatch {
  llm_provider?: LLMProvider;
  bullet_point_generation_strategy?: BulletPointGenerationStrategy;
  skill_selection?: Partial<ConfigTopNValues>;
  project_selection?: Partial<ConfigTopNValues>;
  experience_selection?: Partial<ConfigTopNValues>;
  link_scanning?: Partial<ConfigLinkScanningValues>;
  resume_output?: {
    output_dir?: string | null;
  };
  bullet_count_range?: BulletCountRangeConfig | null;
  openai?: {
    api_key?: string | null;
    clear_api_key?: boolean;
  };
  qwen?: {
    api_key?: string | null;
    clear_api_key?: boolean;
    base_url?: string | null;
  };
  github?: {
    token?: string | null;
    clear_token?: boolean;
  };
}

export interface ResumePdfGenerationResponse {
  blob: Blob;
  texPath: string | null;
  pdfPath: string | null;
  artifactTexPath: string | null;
  artifactPdfPath: string | null;
}

export type ResumeGenerationRunStatus = "idle" | "running" | "succeeded" | "failed";
export type ResumeGenerationStageStatus = "pending" | "running" | "succeeded" | "failed";

export interface JobFocus {
  summary: string;
  required_skills: string[];
  preferred_skills: string[];
  responsibilities: string[];
  domain_emphasis: string[];
  resume_relevant_constraints: string[];
  excluded_context: string[];
}

export interface ResumeGenerationStatusStage {
  id: string;
  label: string;
  status: ResumeGenerationStageStatus;
  started_at: string | null;
  completed_at: string | null;
  message: string | null;
}

export interface ResumeGenerationStatus {
  schema_version: 1;
  run_id: string | null;
  operation: "tex" | null;
  status: ResumeGenerationRunStatus;
  started_at: string | null;
  completed_at: string | null;
  current_stage_id: string | null;
  error: string | null;
  stages: ResumeGenerationStatusStage[];
  job_focus: JobFocus | null;
}
