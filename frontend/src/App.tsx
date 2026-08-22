import {
  Activity,
  AlertCircle,
  BriefcaseBusiness,
  CheckCircle2,
  Download,
  FileText,
  FolderKanban,
  GraduationCap,
  Loader2,
  Plus,
  RefreshCw,
  RotateCcw,
  Save,
  ScanLine,
  Search,
  Settings2,
  Trash2,
  UserRound,
  Wrench,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { FocusEvent, ReactNode } from "react";

import type { EvidenceApi } from "./api";
import { ApiError, evidenceApi } from "./api";
import {
  applyEvidenceChanges,
  describeOperation,
} from "./diff";
import {
  cloneEvidence,
  createBlankEducation,
  createBlankExperience,
  createBlankProject,
  deepEqual,
  hasDraftChanges,
  isTempId,
} from "./draft";
import { sortSkillList } from "./skills";
import type {
  CollectionRecord,
  BulletPointGenerationStrategy,
  BulletCountRangeConfig,
  EducationRecord,
  ExperienceRecord,
  JobTarget,
  LLMProvider,
  MetricOpportunityNote,
  ProjectRecord,
  ProjectSkills,
  ResumeEvidenceRegistry,
  ResumeGenerationConfig,
  ResumeGenerationConfigPatch,
  ResumeGenerationStatus,
  ResumeGenerationStatusStage,
  SkillCategory,
} from "./types";
import { skillCategories } from "./types";
import { validateDraftEvidence, validateGenerationConfig, validateJobTarget } from "./validation";

type SectionKey =
  | "user"
  | "skills"
  | "generate"
  | "status"
  | "config"
  | "experience"
  | "projects"
  | "education";
type BackendStatus = "checking" | "online" | "offline";
type EnrichmentEvidenceType = "projects" | "experience";

interface EnrichmentTarget {
  evidenceType: EnrichmentEvidenceType;
  id: string;
}

interface AppProps {
  client?: EvidenceApi;
}

interface SelectedIds {
  projects?: string;
  experience?: string;
  education?: string;
}

const sectionDefinitions: Array<{
  key: SectionKey;
  label: string;
  icon: LucideIcon;
}> = [
  { key: "user", label: "User", icon: UserRound },
  { key: "skills", label: "Skills", icon: Wrench },
  { key: "experience", label: "Experience", icon: BriefcaseBusiness },
  { key: "projects", label: "Projects", icon: FolderKanban },
  { key: "education", label: "Education", icon: GraduationCap },
  { key: "generate", label: "Generate", icon: FileText },
  { key: "status", label: "Status", icon: Activity },
  { key: "config", label: "Config", icon: Settings2 },
];

const categoryLabels: Record<SkillCategory, string> = {
  technology: "Technology",
  programming: "Programming",
  concepts: "Concepts",
};
const PDF_PREREQUISITE_ERROR_PREFIX = "PDF rendering prerequisites are missing.";
const PDF_PREREQUISITE_MESSAGE =
  "PDF rendering dependencies are missing. On Ubuntu/Debian, run resumecr7-install-pdf-dependencies.sh, then try Generate PDF again.";

export default function App({ client = evidenceApi }: AppProps) {
  const [baseline, setBaseline] = useState<ResumeEvidenceRegistry | null>(null);
  const [draft, setDraft] = useState<ResumeEvidenceRegistry | null>(null);
  const [configBaseline, setConfigBaseline] = useState<ResumeGenerationConfig | null>(null);
  const [configDraft, setConfigDraft] = useState<ResumeGenerationConfig | null>(null);
  const [jobTargetBaseline, setJobTargetBaseline] = useState<JobTarget | null>(null);
  const [jobTargetDraft, setJobTargetDraft] = useState<JobTarget | null>(null);
  const [openAiKeyDraft, setOpenAiKeyDraft] = useState("");
  const [clearOpenAiKey, setClearOpenAiKey] = useState(false);
  const [qwenKeyDraft, setQwenKeyDraft] = useState("");
  const [clearQwenKey, setClearQwenKey] = useState(false);
  const [githubTokenDraft, setGithubTokenDraft] = useState("");
  const [clearGithubToken, setClearGithubToken] = useState(false);
  const [activeSection, setActiveSection] = useState<SectionKey>("user");
  const [selectedIds, setSelectedIds] = useState<SelectedIds>({});
  const [backendStatus, setBackendStatus] = useState<BackendStatus>("checking");
  const [isLoading, setIsLoading] = useState(true);
  const [isApplying, setIsApplying] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [applyError, setApplyError] = useState<string | null>(null);
  const [currentOperation, setCurrentOperation] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [isGeneratingTex, setIsGeneratingTex] = useState(false);
  const [isGeneratingPdf, setIsGeneratingPdf] = useState(false);
  const [generationStatus, setGenerationStatus] = useState<ResumeGenerationStatus | null>(null);
  const [generationStatusError, setGenerationStatusError] = useState<string | null>(null);
  const [enrichingTarget, setEnrichingTarget] = useState<EnrichmentTarget | null>(null);

  const resetEvidence = useCallback((evidence: ResumeEvidenceRegistry) => {
    const nextBaseline = cloneEvidence(evidence);
    setBaseline(nextBaseline);
    setDraft(cloneEvidence(evidence));
    setSelectedIds({
      projects: evidence.projects.projects[0]?.id,
      experience: evidence.experience.experience[0]?.id,
      education: evidence.education.education[0]?.id,
    });
    setApplyError(null);
    setCurrentOperation(null);
  }, []);

  const resetConfig = useCallback((config: ResumeGenerationConfig) => {
    const nextBaseline = cloneEvidence(config);
    setConfigBaseline(nextBaseline);
    setConfigDraft(cloneEvidence(config));
    setOpenAiKeyDraft("");
    setClearOpenAiKey(false);
    setQwenKeyDraft("");
    setClearQwenKey(false);
    setGithubTokenDraft("");
    setClearGithubToken(false);
  }, []);

  const resetJobTarget = useCallback((jobTarget: JobTarget) => {
    const nextBaseline = cloneEvidence(jobTarget);
    setJobTargetBaseline(nextBaseline);
    setJobTargetDraft(cloneEvidence(jobTarget));
  }, []);

  const loadEvidence = useCallback(async () => {
    setIsLoading(true);
    setLoadError(null);
    setMessage(null);
    setBackendStatus("checking");

    try {
      const healthPromise = client
        .getHealth()
        .then(() => "online" as const)
        .catch(() => "offline" as const);
      const [evidence, config, jobTarget] = await Promise.all([
        client.getResumeEvidence(),
        client.getGenerationConfig(),
        client.getJobTarget(),
      ]);
      resetEvidence(evidence);
      resetConfig(config);
      resetJobTarget(jobTarget);
      setBackendStatus(await healthPromise);
    } catch (error) {
      setBackendStatus("offline");
      setLoadError(formatError(error));
    } finally {
      setIsLoading(false);
    }
  }, [client, resetConfig, resetEvidence, resetJobTarget]);

  const loadGenerationStatus = useCallback(async () => {
    try {
      const status = await client.getResumeGenerationStatus();
      setGenerationStatus(status);
      setGenerationStatusError(null);
    } catch (error) {
      setGenerationStatusError(formatError(error));
    }
  }, [client]);

  useEffect(() => {
    void loadEvidence();
  }, [loadEvidence]);

  useEffect(() => {
    void loadGenerationStatus();
  }, [loadGenerationStatus]);

  useEffect(() => {
    if (activeSection === "status") {
      void loadGenerationStatus();
    }

    if (!isGeneratingTex && generationStatus?.status !== "running") {
      return undefined;
    }

    const pollId = window.setInterval(() => {
      void loadGenerationStatus();
    }, 1000);
    return () => window.clearInterval(pollId);
  }, [activeSection, generationStatus?.status, isGeneratingTex, loadGenerationStatus]);

  const evidenceDirty = useMemo(() => hasDraftChanges(baseline, draft), [baseline, draft]);
  const configValuesDirty = useMemo(
    () => configExposedValuesChanged(configBaseline, configDraft),
    [configBaseline, configDraft],
  );
  const configSecretDirty =
    openAiKeyDraft.trim().length > 0 ||
    clearOpenAiKey ||
    qwenKeyDraft.trim().length > 0 ||
    clearQwenKey ||
    githubTokenDraft.trim().length > 0 ||
    clearGithubToken;
  const configDirty = configValuesDirty || configSecretDirty;
  const jobTargetDirty = useMemo(
    () =>
      Boolean(
        jobTargetBaseline &&
          jobTargetDraft &&
          !deepEqual(jobTargetBaseline, jobTargetDraft),
      ),
    [jobTargetBaseline, jobTargetDraft],
  );
  const dirty = evidenceDirty || configDirty || jobTargetDirty;
  const validationErrors = useMemo(() => {
    const errors = draft ? validateDraftEvidence(draft) : [];
    if (configDraft) {
      errors.push(...validateGenerationConfig(configDraft));
    }
    if (jobTargetDraft) {
      errors.push(...validateJobTarget(jobTargetDraft));
    }
    return errors;
  }, [configDraft, draft, jobTargetDraft]);
  const actionInFlight = isGeneratingTex || isGeneratingPdf || enrichingTarget !== null;
  const savedActionDisabled =
    dirty || isLoading || isApplying || actionInFlight || validationErrors.length > 0;
  const applyDisabled = !dirty || isApplying || actionInFlight || validationErrors.length > 0;

  const mutateDraft = useCallback((mutator: (next: ResumeEvidenceRegistry) => void) => {
    setDraft((current) => {
      if (!current) {
        return current;
      }
      const next = cloneEvidence(current);
      mutator(next);
      return next;
    });
    setApplyError(null);
    setMessage(null);
  }, []);

  const mutateConfig = useCallback((mutator: (next: ResumeGenerationConfig) => void) => {
    setConfigDraft((current) => {
      if (!current) {
        return current;
      }
      const next = cloneEvidence(current);
      mutator(next);
      return next;
    });
    setApplyError(null);
    setMessage(null);
  }, []);

  const mutateJobTarget = useCallback((mutator: (next: JobTarget) => void) => {
    setJobTargetDraft((current) => {
      if (!current) {
        return current;
      }
      const next = cloneEvidence(current);
      mutator(next);
      return next;
    });
    setApplyError(null);
    setMessage(null);
  }, []);

  async function handleApply() {
    if (
      !baseline ||
      !draft ||
      !configBaseline ||
      !configDraft ||
      !jobTargetBaseline ||
      !jobTargetDraft ||
      applyDisabled
    ) {
      return;
    }

    setIsApplying(true);
    setApplyError(null);
    setMessage(null);

    let operationLabel: string | null = null;
    try {
      let operationCount = 0;
      if (evidenceDirty) {
        operationCount += await applyEvidenceChanges(client, baseline, draft, (operation) => {
          operationLabel = describeOperation(operation);
          setCurrentOperation(operationLabel);
        });
      }
      if (configDirty) {
        operationLabel = "Updating config";
        setCurrentOperation(operationLabel);
        await client.updateGenerationConfig(
          buildGenerationConfigPatch({
            baseline: configBaseline,
            draft: configDraft,
            openAiKeyDraft,
            clearOpenAiKey,
            qwenKeyDraft,
            clearQwenKey,
            githubTokenDraft,
            clearGithubToken,
          }),
        );
        operationCount += 1;
      }
      if (jobTargetDirty) {
        operationLabel = "Updating job target";
        setCurrentOperation(operationLabel);
        await client.updateJobTarget(normalizeJobTargetForSave(jobTargetDraft));
        operationCount += 1;
      }
      const [freshEvidence, freshConfig, freshJobTarget] = await Promise.all([
        client.getResumeEvidence(),
        client.getGenerationConfig(),
        client.getJobTarget(),
      ]);
      resetEvidence(freshEvidence);
      resetConfig(freshConfig);
      resetJobTarget(freshJobTarget);
      setMessage(`${operationCount} operation${operationCount === 1 ? "" : "s"} applied.`);
    } catch (error) {
      const prefix = operationLabel ? `${operationLabel}: ` : "";
      setApplyError(`${prefix}${formatError(error)}`);
    } finally {
      setCurrentOperation(null);
      setIsApplying(false);
    }
  }

  function handleDiscard() {
    if (!baseline || !configBaseline || !jobTargetBaseline) {
      return;
    }
    setDraft(cloneEvidence(baseline));
    resetConfig(configBaseline);
    resetJobTarget(jobTargetBaseline);
    setSelectedIds({
      projects: baseline.projects.projects[0]?.id,
      experience: baseline.experience.experience[0]?.id,
      education: baseline.education.education[0]?.id,
    });
    setApplyError(null);
    setMessage("Draft discarded.");
  }

  function addProject() {
    const project = createBlankProject();
    mutateDraft((next) => {
      next.projects.projects.push(project);
    });
    setSelectedIds((current) => ({ ...current, projects: project.id }));
    setActiveSection("projects");
  }

  function updateProject(id: string, patch: Partial<ProjectRecord>) {
    mutateDraft((next) => {
      next.projects.projects = next.projects.projects.map((project) =>
        project.id === id ? { ...project, ...patch } : project,
      );
    });
  }

  function deleteProject(id: string) {
    let nextSelected: string | undefined;
    mutateDraft((next) => {
      next.projects.projects = next.projects.projects.filter((project) => project.id !== id);
      nextSelected = next.projects.projects[0]?.id;
    });
    setSelectedIds((current) => ({
      ...current,
      projects: current.projects === id ? nextSelected : current.projects,
    }));
  }

  function addExperience() {
    const experience = createBlankExperience();
    mutateDraft((next) => {
      next.experience.experience.push(experience);
    });
    setSelectedIds((current) => ({ ...current, experience: experience.id }));
    setActiveSection("experience");
  }

  function updateExperience(id: string, patch: Partial<ExperienceRecord>) {
    mutateDraft((next) => {
      next.experience.experience = next.experience.experience.map((experience) =>
        experience.id === id ? { ...experience, ...patch } : experience,
      );
    });
  }

  function deleteExperience(id: string) {
    let nextSelected: string | undefined;
    mutateDraft((next) => {
      next.experience.experience = next.experience.experience.filter(
        (experience) => experience.id !== id,
      );
      nextSelected = next.experience.experience[0]?.id;
    });
    setSelectedIds((current) => ({
      ...current,
      experience: current.experience === id ? nextSelected : current.experience,
    }));
  }

  function addEducation() {
    const education = createBlankEducation();
    mutateDraft((next) => {
      next.education.education.push(education);
    });
    setSelectedIds((current) => ({ ...current, education: education.id }));
    setActiveSection("education");
  }

  function updateEducation(id: string, patch: Partial<EducationRecord>) {
    mutateDraft((next) => {
      next.education.education = next.education.education.map((education) =>
        education.id === id ? { ...education, ...patch } : education,
      );
    });
  }

  function deleteEducation(id: string) {
    let nextSelected: string | undefined;
    mutateDraft((next) => {
      next.education.education = next.education.education.filter(
        (education) => education.id !== id,
      );
      nextSelected = next.education.education[0]?.id;
    });
    setSelectedIds((current) => ({
      ...current,
      education: current.education === id ? nextSelected : current.education,
    }));
  }

  function ensureSavedActionReady(): boolean {
    if (dirty) {
      setApplyError("Apply or discard staged edits before running this action.");
      setMessage(null);
      return false;
    }
    if (validationErrors.length > 0) {
      setApplyError(validationErrors[0]);
      setMessage(null);
      return false;
    }
    return true;
  }

  async function handleGenerateTex() {
    if (!ensureSavedActionReady()) {
      return;
    }

    setActiveSection("status");
    setIsGeneratingTex(true);
    setApplyError(null);
    setGenerationStatusError(null);
    setMessage(null);
    setCurrentOperation("Generating .tex resume");

    try {
      const result = await client.generateResumeTex({});
      setMessage(`Generated .tex at ${result.tex_path}.`);
      await loadGenerationStatus();
    } catch (error) {
      setApplyError(formatError(error));
      await loadGenerationStatus();
    } finally {
      setCurrentOperation(null);
      setIsGeneratingTex(false);
    }
  }

  async function handleGeneratePdf() {
    if (!ensureSavedActionReady()) {
      return;
    }

    setIsGeneratingPdf(true);
    setApplyError(null);
    setMessage(null);
    setCurrentOperation("Generating PDF");

    try {
      const result = await client.generateResumePdf();
      setMessage(
        result.pdfPath
          ? `Generated PDF at ${result.pdfPath}. Source .tex: ${result.texPath ?? "unknown"}.`
          : "Generated PDF.",
      );
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) {
        setApplyError("Generate the .tex file first.");
      } else if (isPdfPrerequisiteError(error)) {
        setApplyError(PDF_PREREQUISITE_MESSAGE);
      } else {
        setApplyError(formatError(error));
      }
    } finally {
      setCurrentOperation(null);
      setIsGeneratingPdf(false);
    }
  }

  async function handleEnrichRecord(evidenceType: EnrichmentEvidenceType, id: string) {
    if (!ensureSavedActionReady()) {
      return;
    }

    setEnrichingTarget({ evidenceType, id });
    setApplyError(null);
    setMessage(null);
    setCurrentOperation("Enriching link evidence");

    try {
      const result = await client.enrichResumeLinkEvidence({
        evidence_type: evidenceType,
        evidence_id: id,
        dry_run: false,
      });
      const freshEvidence = await client.getResumeEvidence();
      resetEvidence(freshEvidence);
      setActiveSection(evidenceType);
      setSelectedIds((current) => ({ ...current, [evidenceType]: id }));
      setMessage(
        `Link scanning added ${result.total_added_highlights} highlight${
          result.total_added_highlights === 1 ? "" : "s"
        }.`,
      );
    } catch (error) {
      setApplyError(formatError(error));
    } finally {
      setCurrentOperation(null);
      setEnrichingTarget(null);
    }
  }

  function enrichmentDisabledReason(record: ProjectRecord | ExperienceRecord): string | null {
    if (dirty) {
      return "Apply or discard staged edits first";
    }
    if (validationErrors.length > 0) {
      return validationErrors[0];
    }
    if (isTempId(record.id)) {
      return "Apply new record first";
    }
    if (!record.links || record.links.length === 0) {
      return "Add a link before scanning";
    }
    if (isLoading || isApplying || actionInFlight) {
      return "Another operation is running";
    }
    return null;
  }

  const validationMessage = dirty && validationErrors.length > 0 ? validationErrors[0] : null;

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand-block">
          <span className="brand-mark">RC7</span>
          <div>
            <h1>Resume Evidence</h1>
            <span className="subtle-text">ResumeCR7 Workbench</span>
          </div>
        </div>

        <div className="topbar-actions">
          <BackendStatusPill status={backendStatus} />
          {dirty ? <span className="dirty-pill">Unsaved</span> : <span className="clean-pill">Saved</span>}
          <button
            className="button secondary"
            type="button"
            onClick={() => void loadEvidence()}
            disabled={isLoading || isApplying || actionInFlight}
            title="Reload evidence"
          >
            <RefreshCw aria-hidden="true" size={17} />
            Reload
          </button>
          <button
            className="button secondary"
            type="button"
            onClick={handleDiscard}
            disabled={!dirty || isApplying || actionInFlight}
            title="Discard draft changes"
          >
            <RotateCcw aria-hidden="true" size={17} />
            Discard
          </button>
          <button
            className="button primary"
            type="button"
            onClick={() => void handleApply()}
            disabled={applyDisabled}
            title="Apply staged changes"
          >
            {isApplying ? (
              <Loader2 className="spin" aria-hidden="true" size={17} />
            ) : (
              <Save aria-hidden="true" size={17} />
            )}
            Apply
          </button>
        </div>
      </header>

      <div className="workspace">
        <nav className="section-nav" aria-label="Evidence sections">
          {sectionDefinitions.map((section) => (
            <NavButton
              key={section.key}
              active={activeSection === section.key}
              count={draft ? sectionCount(section.key, draft) : undefined}
              icon={section.icon}
              label={section.label}
              onClick={() => setActiveSection(section.key)}
            />
          ))}
        </nav>

        <section className="content-area">
          {isLoading ? (
            <StatePanel icon={Loader2} spin title="Loading evidence" />
          ) : loadError || !draft || !configDraft || !jobTargetDraft ? (
            <StatePanel
              icon={AlertCircle}
              tone="error"
              title="Evidence unavailable"
              detail={loadError ?? "Workspace data was not returned."}
            >
              <button className="button secondary" type="button" onClick={() => void loadEvidence()}>
                <RefreshCw aria-hidden="true" size={17} />
                Reload
              </button>
            </StatePanel>
          ) : (
            <>
              <StatusMessages
                applyError={applyError}
                currentOperation={currentOperation}
                message={message}
                validationMessage={validationMessage}
              />
              {activeSection === "user" ? (
                <UserEditor
                  user={draft.user}
                  onChange={(patch) => {
                    mutateDraft((next) => {
                      next.user = { ...next.user, ...patch };
                    });
                  }}
                />
              ) : null}
              {activeSection === "skills" ? (
                <SkillsEditor
                  skills={draft.skills.skills}
                  onChange={(skills) => {
                    mutateDraft((next) => {
                      next.skills.skills = skills;
                    });
                  }}
                />
              ) : null}
              {activeSection === "generate" ? (
                <ResumeGenerationPanel
                  actionsDisabled={savedActionDisabled}
                  jobTarget={jobTargetDraft}
                  pdfBusy={isGeneratingPdf}
                  texBusy={isGeneratingTex}
                  onGeneratePdf={() => void handleGeneratePdf()}
                  onGenerateTex={() => void handleGenerateTex()}
                  onJobDescriptionChange={(description) => {
                    mutateJobTarget((next) => {
                      next.description = optionalText(description);
                    });
                  }}
                  onJobTitleChange={(title) => {
                    mutateJobTarget((next) => {
                      next.title = title;
                    });
                  }}
                />
              ) : null}
              {activeSection === "status" ? (
                <GenerationStatusPanel
                  error={generationStatusError}
                  status={generationStatus}
                  onRefresh={() => void loadGenerationStatus()}
                />
              ) : null}
              {activeSection === "config" ? (
                <ConfigEditor
                  clearGithubToken={clearGithubToken}
                  clearOpenAiKey={clearOpenAiKey}
                  clearQwenKey={clearQwenKey}
                  config={configDraft}
                  githubTokenDraft={githubTokenDraft}
                  openAiKeyDraft={openAiKeyDraft}
                  qwenKeyDraft={qwenKeyDraft}
                  onChange={mutateConfig}
                  onClearGithubToken={(value) => {
                    setClearGithubToken(value);
                    if (value) {
                      setGithubTokenDraft("");
                    }
                    setApplyError(null);
                    setMessage(null);
                  }}
                  onClearOpenAiKey={(value) => {
                    setClearOpenAiKey(value);
                    if (value) {
                      setOpenAiKeyDraft("");
                    }
                    setApplyError(null);
                    setMessage(null);
                  }}
                  onClearQwenKey={(value) => {
                    setClearQwenKey(value);
                    if (value) {
                      setQwenKeyDraft("");
                    }
                    setApplyError(null);
                    setMessage(null);
                  }}
                  onGithubTokenChange={(value) => {
                    setGithubTokenDraft(value);
                    if (value.trim()) {
                      setClearGithubToken(false);
                    }
                    setApplyError(null);
                    setMessage(null);
                  }}
                  onOpenAiKeyChange={(value) => {
                    setOpenAiKeyDraft(value);
                    if (value.trim()) {
                      setClearOpenAiKey(false);
                    }
                    setApplyError(null);
                    setMessage(null);
                  }}
                  onQwenKeyChange={(value) => {
                    setQwenKeyDraft(value);
                    if (value.trim()) {
                      setClearQwenKey(false);
                    }
                    setApplyError(null);
                    setMessage(null);
                  }}
                />
              ) : null}
              {activeSection === "projects" ? (
                <CollectionPanel
                  addLabel="Add Project"
                  getMeta={(project) =>
                    `${project.active ? "Active" : "Inactive"} | ${countSkills(project.skills)} skills`
                  }
                  getSearchText={(project) => `${project.name} ${project.summary}`}
                  records={draft.projects.projects}
                  selectedId={selectedIds.projects}
                  title="Projects"
                  onAdd={addProject}
                  onDelete={deleteProject}
                  onSelect={(id) => setSelectedIds((current) => ({ ...current, projects: id }))}
                  renderEditor={(project) => (
                    <ProjectRecordEditor
                      key={project.id}
                      enrichDisabledReason={enrichmentDisabledReason(project)}
                      isEnriching={
                        enrichingTarget?.evidenceType === "projects" &&
                        enrichingTarget.id === project.id
                      }
                      project={project}
                      onChange={(patch) => updateProject(project.id, patch)}
                      onEnrich={() => void handleEnrichRecord("projects", project.id)}
                    />
                  )}
                />
              ) : null}
              {activeSection === "experience" ? (
                <CollectionPanel
                  addLabel="Add Experience"
                  getMeta={(experience) =>
                    `${experience.role || "Role"} | ${experience.start || "Start"}${
                      experience.end ? ` to ${experience.end}` : ""
                    }`
                  }
                  getSearchText={(experience) =>
                    `${experience.name} ${experience.role} ${experience.summary}`
                  }
                  records={draft.experience.experience}
                  selectedId={selectedIds.experience}
                  title="Experience"
                  onAdd={addExperience}
                  onDelete={deleteExperience}
                  onSelect={(id) => setSelectedIds((current) => ({ ...current, experience: id }))}
                  renderEditor={(experience) => (
                    <ExperienceRecordEditor
                      key={experience.id}
                      enrichDisabledReason={enrichmentDisabledReason(experience)}
                      experience={experience}
                      isEnriching={
                        enrichingTarget?.evidenceType === "experience" &&
                        enrichingTarget.id === experience.id
                      }
                      onChange={(patch) => updateExperience(experience.id, patch)}
                      onEnrich={() => void handleEnrichRecord("experience", experience.id)}
                    />
                  )}
                />
              ) : null}
              {activeSection === "education" ? (
                <CollectionPanel
                  addLabel="Add Education"
                  getMeta={(education) => `${education.degree || "Degree"} | ${education.location || "Location"}`}
                  getSearchText={(education) => `${education.name} ${education.degree} ${education.location}`}
                  records={draft.education.education}
                  selectedId={selectedIds.education}
                  title="Education"
                  onAdd={addEducation}
                  onDelete={deleteEducation}
                  onSelect={(id) => setSelectedIds((current) => ({ ...current, education: id }))}
                  renderEditor={(education) => (
                    <EducationRecordEditor
                      key={education.id}
                      education={education}
                      onChange={(patch) => updateEducation(education.id, patch)}
                    />
                  )}
                />
              ) : null}
            </>
          )}
        </section>
      </div>
    </main>
  );
}

function BackendStatusPill({ status }: { status: BackendStatus }) {
  const label =
    status === "checking"
      ? "Checking backend"
      : status === "online"
        ? "Backend online"
        : "Backend offline";
  return (
    <span className={`status-pill ${status}`}>
      <span className="status-dot" aria-hidden="true" />
      {label}
    </span>
  );
}

function NavButton({
  active,
  count,
  icon: Icon,
  label,
  onClick,
}: {
  active: boolean;
  count?: number;
  icon: LucideIcon;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      aria-current={active ? "page" : undefined}
      className={`nav-button ${active ? "active" : ""}`}
      type="button"
      onClick={onClick}
    >
      <Icon aria-hidden="true" size={18} />
      <span>{label}</span>
      {typeof count === "number" ? <span className="nav-count">{count}</span> : null}
    </button>
  );
}

function StatusMessages({
  applyError,
  currentOperation,
  message,
  validationMessage,
}: {
  applyError: string | null;
  currentOperation: string | null;
  message: string | null;
  validationMessage: string | null;
}) {
  if (!applyError && !currentOperation && !message && !validationMessage) {
    return null;
  }

  if (applyError) {
    return (
      <div className="notice error" role="alert">
        <AlertCircle aria-hidden="true" size={18} />
        {applyError}
      </div>
    );
  }

  if (validationMessage) {
    return (
      <div className="notice warning" role="status">
        <AlertCircle aria-hidden="true" size={18} />
        {validationMessage}
      </div>
    );
  }

  if (currentOperation) {
    return (
      <div className="notice pending" role="status">
        <Loader2 className="spin" aria-hidden="true" size={18} />
        {currentOperation}
      </div>
    );
  }

  return (
    <div className="notice success" role="status">
      <CheckCircle2 aria-hidden="true" size={18} />
      {message}
    </div>
  );
}

function UserEditor({
  user,
  onChange,
}: {
  user: ResumeEvidenceRegistry["user"];
  onChange: (patch: Partial<ResumeEvidenceRegistry["user"]>) => void;
}) {
  return (
    <div className="editor-surface">
      <SectionHeader title="User" eyebrow="Contact" />
      <div className="field-grid">
        <TextField label="Name" value={user.name} onChange={(name) => onChange({ name })} />
        <TextField label="Email" value={user.email} onChange={(email) => onChange({ email })} />
        <TextField label="Phone" value={user.phone} onChange={(phone) => onChange({ phone })} />
        <TextField
          label="LinkedIn"
          value={user.linkedin ?? ""}
          onChange={(linkedin) => onChange({ linkedin: optionalText(linkedin) })}
        />
        <TextField
          label="GitHub"
          value={user.github ?? ""}
          onChange={(github) => onChange({ github: optionalText(github) })}
        />
        <TextField
          label="Website"
          value={user.website ?? ""}
          onChange={(website) => onChange({ website: optionalText(website) })}
        />
      </div>
    </div>
  );
}

function SkillsEditor({
  skills,
  onChange,
}: {
  skills: ProjectSkills;
  onChange: (skills: ProjectSkills) => void;
}) {
  const [editingCategory, setEditingCategory] = useState<SkillCategory | null>(null);
  const [focusRequest, setFocusRequest] = useState<{
    category: SkillCategory;
    sequence: number;
  } | null>(null);

  function updateCategory(category: SkillCategory, values: string[]) {
    onChange({ ...skills, [category]: values });
  }

  function startEditingCategory(category: SkillCategory) {
    if (editingCategory !== category) {
      updateCategory(category, sortSkillList(skills[category]));
    }
    setEditingCategory(category);
  }

  function addSkill(category: SkillCategory) {
    updateCategory(category, ["", ...sortSkillList(skills[category])]);
    setEditingCategory(category);
    setFocusRequest((current) => ({
      category,
      sequence: (current?.sequence ?? 0) + 1,
    }));
  }

  function finishEditingCategory(category: SkillCategory, values: string[]) {
    updateCategory(category, sortSkillList(values));
    setEditingCategory((current) => (current === category ? null : current));
  }

  return (
    <div className="editor-surface">
      <SectionHeader title="Skills" eyebrow="Inventory" />
      <div className="bucket-grid">
        {skillCategories.map((category) => (
          <SkillInventoryCategoryEditor
            key={category}
            focusFirstSequence={
              focusRequest?.category === category ? focusRequest.sequence : undefined
            }
            label={categoryLabels[category]}
            values={
              editingCategory === category ? skills[category] : sortSkillList(skills[category])
            }
            onAdd={() => addSkill(category)}
            onBlurAway={(values) => finishEditingCategory(category, values)}
            onChange={(values) => updateCategory(category, values)}
            onFocus={() => startEditingCategory(category)}
          />
        ))}
      </div>
    </div>
  );
}

function ResumeGenerationPanel({
  actionsDisabled,
  jobTarget,
  pdfBusy,
  texBusy,
  onGeneratePdf,
  onGenerateTex,
  onJobDescriptionChange,
  onJobTitleChange,
}: {
  actionsDisabled: boolean;
  jobTarget: JobTarget;
  pdfBusy: boolean;
  texBusy: boolean;
  onGeneratePdf: () => void;
  onGenerateTex: () => void;
  onJobDescriptionChange: (value: string) => void;
  onJobTitleChange: (value: string) => void;
}) {
  return (
    <div className="editor-surface">
      <SectionHeader title="Resume" eyebrow="Generate" />
      <div className="field-grid">
        <TextField label="Job Title" value={jobTarget.title} onChange={onJobTitleChange} />
      </div>
      <TextareaField
        label="Job Description"
        value={jobTarget.description ?? ""}
        onChange={onJobDescriptionChange}
      />
      <div className="generation-actions">
        <button
          className="button primary"
          disabled={actionsDisabled}
          title="Generate .tex"
          type="button"
          onClick={onGenerateTex}
        >
          {texBusy ? (
            <Loader2 className="spin" aria-hidden="true" size={17} />
          ) : (
            <FileText aria-hidden="true" size={17} />
          )}
          Generate .tex
        </button>
        <button
          className="button secondary"
          disabled={actionsDisabled}
          title="Generate PDF"
          type="button"
          onClick={onGeneratePdf}
        >
          {pdfBusy ? (
            <Loader2 className="spin" aria-hidden="true" size={17} />
          ) : (
            <Download aria-hidden="true" size={17} />
          )}
          Generate PDF
        </button>
      </div>
    </div>
  );
}

function GenerationStatusPanel({
  error,
  status,
  onRefresh,
}: {
  error: string | null;
  status: ResumeGenerationStatus | null;
  onRefresh: () => void;
}) {
  const activeStage = status?.stages.find((stage) => stage.id === status.current_stage_id);
  return (
    <div className="editor-surface">
      <div className="status-header-row">
        <SectionHeader
          title="Generation Status"
          eyebrow={status?.status === "running" ? "Running" : "Monitor"}
        />
        <button className="button secondary icon-only" type="button" onClick={onRefresh} title="Refresh">
          <RefreshCw aria-hidden="true" size={17} />
        </button>
      </div>

      {error ? (
        <div className="notice error" role="alert">
          <AlertCircle aria-hidden="true" size={18} />
          {error}
        </div>
      ) : null}

      <div className={`generation-run-summary ${status?.status ?? "idle"}`}>
        <div>
          <span>Run</span>
          <strong>{status ? generationRunLabel(status.status) : "Loading"}</strong>
        </div>
        <div>
          <span>Current</span>
          <strong>{activeStage?.label ?? "None"}</strong>
        </div>
        <div>
          <span>Started</span>
          <strong>{formatStatusTime(status?.started_at)}</strong>
        </div>
      </div>

      <div className="generation-stage-list" aria-label="Generation stages">
        {status && status.stages.length > 0 ? (
          status.stages.map((stage) => <GenerationStageRow key={stage.id} stage={stage} />)
        ) : (
          <StatePanel icon={Activity} title="No generation run" />
        )}
      </div>

      {status?.metric_notes.length ? (
        <MetricOpportunityPanel notes={status.metric_notes} />
      ) : null}

      {status?.job_focus ? (
        <div className="job-focus-panel">
          <SectionHeader title="Job Focus" eyebrow="Found" compact />
          <p>{status.job_focus.summary}</p>
          <JobFocusList label="Required" values={status.job_focus.required_skills} />
          <JobFocusList label="Preferred" values={status.job_focus.preferred_skills} />
          <JobFocusList label="Responsibilities" values={status.job_focus.responsibilities} />
          <JobFocusList label="Emphasis" values={status.job_focus.domain_emphasis} />
          <JobFocusList
            label="Constraints"
            values={status.job_focus.resume_relevant_constraints}
          />
        </div>
      ) : null}
    </div>
  );
}

function MetricOpportunityPanel({ notes }: { notes: MetricOpportunityNote[] }) {
  return (
    <div className="metric-opportunity-panel">
      <SectionHeader title="Metric Opportunities" eyebrow="Evidence" compact />
      <div className="metric-note-list">
        {notes.map((note) => (
          <div
            className="metric-note"
            key={`${note.evidence_type}-${note.evidence_id}`}
          >
            <div>
              <strong>{note.name}</strong>
              <span>{note.evidence_type === "project" ? "Project" : "Experience"}</span>
            </div>
            <ul>
              {note.suggestions.map((suggestion) => (
                <li key={suggestion}>{suggestion}</li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </div>
  );
}

function GenerationStageRow({ stage }: { stage: ResumeGenerationStatusStage }) {
  const Icon =
    stage.status === "succeeded"
      ? CheckCircle2
      : stage.status === "failed"
        ? AlertCircle
        : stage.status === "running"
          ? Loader2
          : Activity;
  return (
    <div className={`generation-stage-row ${stage.status}`}>
      <span className="stage-icon" aria-hidden="true">
        <Icon className={stage.status === "running" ? "spin" : undefined} size={18} />
      </span>
      <div className="stage-copy">
        <strong>{stage.label}</strong>
        <span>{stage.message ?? generationStageLabel(stage.status)}</span>
      </div>
      <span className="stage-state">{generationStageLabel(stage.status)}</span>
    </div>
  );
}

function JobFocusList({ label, values }: { label: string; values: string[] }) {
  if (values.length === 0) {
    return null;
  }
  return (
    <div className="job-focus-list">
      <span>{label}</span>
      <div>
        {values.map((value) => (
          <span className="job-focus-chip" key={value}>
            {value}
          </span>
        ))}
      </div>
    </div>
  );
}

function ConfigEditor({
  clearGithubToken,
  clearOpenAiKey,
  clearQwenKey,
  config,
  githubTokenDraft,
  openAiKeyDraft,
  qwenKeyDraft,
  onChange,
  onClearGithubToken,
  onClearOpenAiKey,
  onClearQwenKey,
  onGithubTokenChange,
  onOpenAiKeyChange,
  onQwenKeyChange,
}: {
  clearGithubToken: boolean;
  clearOpenAiKey: boolean;
  clearQwenKey: boolean;
  config: ResumeGenerationConfig;
  githubTokenDraft: string;
  openAiKeyDraft: string;
  qwenKeyDraft: string;
  onChange: (mutator: (next: ResumeGenerationConfig) => void) => void;
  onClearGithubToken: (value: boolean) => void;
  onClearOpenAiKey: (value: boolean) => void;
  onClearQwenKey: (value: boolean) => void;
  onGithubTokenChange: (value: string) => void;
  onOpenAiKeyChange: (value: string) => void;
  onQwenKeyChange: (value: string) => void;
}) {
  const bulletRange = config.bullet_count_range;
  const openAiStatus = openAiKeyStatus(config, openAiKeyDraft, clearOpenAiKey);
  const qwenStatus = qwenKeyStatus(config, qwenKeyDraft, clearQwenKey);
  const githubStatus = githubTokenStatus(config, githubTokenDraft, clearGithubToken);
  return (
    <div className="editor-surface">
      <SectionHeader title="Config" eyebrow="Runtime" />
      <div className="config-layout">
        <div className="config-section">
          <h3>Selection</h3>
          <div className="field-grid">
            <NumberField
              defaultLabel={
                config.skill_selection.top_n === null
                  ? config.display_defaults.skill_selection_top_n
                  : undefined
              }
              label="# of skills to display in the skills section per category"
              min={0}
              value={config.skill_selection.top_n}
              onChange={(top_n) =>
                onChange((next) => {
                  next.skill_selection.top_n = top_n;
                })
              }
            />
            <NumberField
              defaultLabel={
                config.project_selection.top_n === null
                  ? config.display_defaults.project_selection_top_n
                  : undefined
              }
              label="# of projects to select for the resume"
              min={0}
              value={config.project_selection.top_n}
              onChange={(top_n) =>
                onChange((next) => {
                  next.project_selection.top_n = top_n;
                })
              }
            />
            <NumberField
              defaultLabel={
                config.experience_selection.top_n === null
                  ? config.display_defaults.experience_selection_top_n
                  : undefined
              }
              label="# of experience entries to include in the resume"
              min={0}
              value={config.experience_selection.top_n}
              onChange={(top_n) =>
                onChange((next) => {
                  next.experience_selection.top_n = top_n;
                })
              }
            />
          </div>
        </div>

        <div className="config-section">
          <h3>Link Scanning</h3>
          <div className="field-grid">
            <NumberField
              defaultLabel={
                config.link_scanning.highlight_count === null
                  ? config.display_defaults.link_scanning_highlight_count
                  : undefined
              }
              label="Highlights to collect per record"
              min={1}
              value={config.link_scanning.highlight_count}
              onChange={(highlight_count) =>
                onChange((next) => {
                  next.link_scanning.highlight_count = highlight_count;
                })
              }
            />
            <NumberField
              defaultLabel={
                config.link_scanning.max_tokens_per_highlight === null
                  ? config.display_defaults.link_scanning_max_tokens_per_highlight
                  : undefined
              }
              label="Max tokens per highlight"
              min={1}
              value={config.link_scanning.max_tokens_per_highlight}
              onChange={(max_tokens_per_highlight) =>
                onChange((next) => {
                  next.link_scanning.max_tokens_per_highlight = max_tokens_per_highlight;
                })
              }
            />
          </div>
        </div>

        <div className="config-section">
          <h3>Bullet Generation</h3>
          <div className="field-grid">
            <SelectField<BulletPointGenerationStrategy>
              label="Bullet generation strategy"
              value={config.bullet_point_generation_strategy}
              options={[
                { label: "Whole section", value: "section_batch" },
                { label: "Per entry", value: "per_record" },
              ]}
              onChange={(strategy) =>
                onChange((next) => {
                  next.bullet_point_generation_strategy = strategy;
                })
              }
            />
          </div>
        </div>

        <div className="config-section">
          <div className="config-section-header">
            <h3>Bullet Counts</h3>
            <button
              className="button secondary compact"
              disabled={bulletRange === null}
              title="Use default bullet count range"
              type="button"
              onClick={() =>
                onChange((next) => {
                  next.bullet_count_range = null;
                })
              }
            >
              <RotateCcw aria-hidden="true" size={16} />
              Use default
            </button>
          </div>
          <div className="field-grid">
            <NumberField
              defaultLabel={
                bulletRange === null ? config.display_defaults.bullet_count_range : undefined
              }
              label="Bullet count lower bound"
              min={1}
              value={bulletRange?.min ?? null}
              onChange={(min) =>
                updateBulletCountRange(config, onChange, "min", min)
              }
            />
            <NumberField
              defaultLabel={
                bulletRange === null ? config.display_defaults.bullet_count_range : undefined
              }
              label="Bullet count upper bound"
              min={1}
              value={bulletRange?.max ?? null}
              onChange={(max) =>
                updateBulletCountRange(config, onChange, "max", max)
              }
            />
          </div>
        </div>

        <div className="config-section">
          <h3>Resume Output</h3>
          <div className="field-grid">
            <TextField
              label="Resume output directory"
              value={config.resume_output.output_dir}
              onChange={(outputDir) =>
                onChange((next) => {
                  next.resume_output.output_dir = outputDir;
                  next.resume_output.tex_path = `${outputDir.replace(/\/+$/, "")}/resume.tex`;
                  next.resume_output.pdf_path = `${outputDir.replace(/\/+$/, "")}/resume.pdf`;
                })
              }
            />
          </div>
        </div>

        <div className="config-section">
          <div className="config-section-header">
            <h3>LLM Provider</h3>
            <span className="config-status">{config.llm_provider}</span>
          </div>
          <div className="field-grid">
            <SelectField
              label="LLM Provider"
              value={config.llm_provider}
              options={[
                { label: "OpenAI", value: "openai" },
                { label: "Qwen", value: "qwen" },
              ]}
              onChange={(llmProvider) =>
                onChange((next) => {
                  next.llm_provider = llmProvider;
                })
              }
            />
            <TextField
              label="Qwen Base URL"
              value={config.qwen_base_url}
              onChange={(baseUrl) =>
                onChange((next) => {
                  next.qwen_base_url = baseUrl;
                })
              }
            />
          </div>
        </div>

        <div className="config-section">
          <div className="config-section-header">
            <h3>OpenAI API Key</h3>
            <span className="config-status">{openAiStatus}</span>
          </div>
          <div className="secret-row">
            <PasswordField
              label="OpenAI API Key"
              placeholder={config.openai_api_key_configured ? "saved" : "not set"}
              value={openAiKeyDraft}
              onChange={onOpenAiKeyChange}
            />
            <button
              className="button secondary compact"
              disabled={!config.openai_api_key_saved}
              title={clearOpenAiKey ? "Keep saved OpenAI API key" : "Clear saved OpenAI API key"}
              type="button"
              onClick={() => onClearOpenAiKey(!clearOpenAiKey)}
            >
              {clearOpenAiKey ? (
                <RotateCcw aria-hidden="true" size={16} />
              ) : (
                <Trash2 aria-hidden="true" size={16} />
              )}
              {clearOpenAiKey ? "Keep" : "Clear"}
            </button>
          </div>
        </div>

        <div className="config-section">
          <div className="config-section-header">
            <h3>Qwen API Key</h3>
            <span className="config-status">{qwenStatus}</span>
          </div>
          <div className="secret-row">
            <PasswordField
              label="Qwen API Key"
              placeholder={config.qwen_api_key_configured ? "saved" : "not set"}
              value={qwenKeyDraft}
              onChange={onQwenKeyChange}
            />
            <button
              className="button secondary compact"
              disabled={!config.qwen_api_key_saved}
              title={clearQwenKey ? "Keep saved Qwen API key" : "Clear saved Qwen API key"}
              type="button"
              onClick={() => onClearQwenKey(!clearQwenKey)}
            >
              {clearQwenKey ? (
                <RotateCcw aria-hidden="true" size={16} />
              ) : (
                <Trash2 aria-hidden="true" size={16} />
              )}
              {clearQwenKey ? "Keep" : "Clear"}
            </button>
          </div>
        </div>

        <div className="config-section">
          <div className="config-section-header">
            <h3>GitHub</h3>
            <span className="config-status">{githubStatus}</span>
          </div>
          <div className="secret-row">
            <PasswordField
              label="GitHub Token"
              placeholder={config.github_token_configured ? "saved" : "not set"}
              value={githubTokenDraft}
              onChange={onGithubTokenChange}
            />
            <button
              className="button secondary compact"
              disabled={!config.github_token_saved}
              title={clearGithubToken ? "Keep saved GitHub token" : "Clear saved GitHub token"}
              type="button"
              onClick={() => onClearGithubToken(!clearGithubToken)}
            >
              {clearGithubToken ? (
                <RotateCcw aria-hidden="true" size={16} />
              ) : (
                <Trash2 aria-hidden="true" size={16} />
              )}
              {clearGithubToken ? "Keep" : "Clear"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function CollectionPanel<T extends CollectionRecord>({
  addLabel,
  getMeta,
  getSearchText,
  records,
  renderEditor,
  selectedId,
  title,
  onAdd,
  onDelete,
  onSelect,
}: {
  addLabel: string;
  getMeta: (record: T) => string;
  getSearchText: (record: T) => string;
  records: T[];
  renderEditor: (record: T) => ReactNode;
  selectedId?: string;
  title: string;
  onAdd: () => void;
  onDelete: (id: string) => void;
  onSelect: (id: string) => void;
}) {
  const [query, setQuery] = useState("");
  const normalizedQuery = query.trim().toLowerCase();
  const selectedRecord = records.find((record) => record.id === selectedId) ?? records[0];
  const filteredRecords = normalizedQuery
    ? records.filter((record) => getSearchText(record).toLowerCase().includes(normalizedQuery))
    : records;

  return (
    <div className="collection-layout">
      <aside className="record-list-pane">
        <div className="collection-toolbar">
          <SectionHeader title={title} eyebrow={`${records.length} entries`} compact />
          <button className="button primary compact" type="button" onClick={onAdd}>
            <Plus aria-hidden="true" size={16} />
            {addLabel}
          </button>
        </div>
        <label className="search-box">
          <Search aria-hidden="true" size={17} />
          <input
            aria-label={`Search ${title}`}
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
        <div className="record-list">
          {filteredRecords.length === 0 ? (
            <p className="empty-note">No matches.</p>
          ) : (
            filteredRecords.map((record) => (
              <div
                className={`record-row ${record.id === selectedRecord?.id ? "selected" : ""}`}
                key={record.id}
              >
                <button className="record-select" type="button" onClick={() => onSelect(record.id)}>
                  <span className="record-title">{record.name || "Untitled"}</span>
                  <span className="record-meta">{getMeta(record)}</span>
                  {isTempId(record.id) ? <span className="record-temp">New</span> : null}
                </button>
                <button
                  aria-label={`Delete ${record.name || "record"}`}
                  className="icon-button danger"
                  title={`Delete ${record.name || "record"}`}
                  type="button"
                  onClick={() => onDelete(record.id)}
                >
                  <Trash2 aria-hidden="true" size={16} />
                </button>
              </div>
            ))
          )}
        </div>
      </aside>
      <section className="record-editor">
        {selectedRecord ? renderEditor(selectedRecord) : <StatePanel icon={AlertCircle} title="No records" />}
      </section>
    </div>
  );
}

function ProjectRecordEditor({
  enrichDisabledReason,
  isEnriching,
  onEnrich,
  project,
  onChange,
}: {
  enrichDisabledReason: string | null;
  isEnriching: boolean;
  onEnrich: () => void;
  project: ProjectRecord;
  onChange: (patch: Partial<ProjectRecord>) => void;
}) {
  return (
    <div className="editor-surface">
      <SectionHeader title={project.name || "Untitled Project"} eyebrow={project.id} />
      <div className="record-action-row">
        <button
          className="button secondary"
          disabled={enrichDisabledReason !== null}
          title={enrichDisabledReason ?? "Enrich with link scanning"}
          type="button"
          onClick={onEnrich}
        >
          {isEnriching ? (
            <Loader2 className="spin" aria-hidden="true" size={17} />
          ) : (
            <ScanLine aria-hidden="true" size={17} />
          )}
          Enrich with link scanning
        </button>
      </div>
      <div className="field-grid">
        <TextField label="Name" value={project.name} onChange={(name) => onChange({ name })} />
        <ToggleField
          checked={project.active}
          label="Active"
          onChange={(active) => onChange({ active })}
        />
      </div>
      <TextareaField
        label="Summary"
        value={project.summary}
        onChange={(summary) => onChange({ summary })}
      />
      <TextListEditor
        label="Highlights"
        minItems={1}
        values={project.highlights}
        onChange={(highlights) => onChange({ highlights })}
      />
      <SkillBucketsEditor
        skills={project.skills}
        onChange={(skills) => onChange({ skills })}
      />
      <TextListEditor
        label="Links"
        values={project.links ?? []}
        onChange={(links) => onChange({ links: optionalList(links) })}
      />
    </div>
  );
}

function ExperienceRecordEditor({
  enrichDisabledReason,
  experience,
  isEnriching,
  onChange,
  onEnrich,
}: {
  enrichDisabledReason: string | null;
  experience: ExperienceRecord;
  isEnriching: boolean;
  onChange: (patch: Partial<ExperienceRecord>) => void;
  onEnrich: () => void;
}) {
  return (
    <div className="editor-surface">
      <SectionHeader title={experience.name || "Untitled Experience"} eyebrow={experience.id} />
      <div className="record-action-row">
        <button
          className="button secondary"
          disabled={enrichDisabledReason !== null}
          title={enrichDisabledReason ?? "Enrich with link scanning"}
          type="button"
          onClick={onEnrich}
        >
          {isEnriching ? (
            <Loader2 className="spin" aria-hidden="true" size={17} />
          ) : (
            <ScanLine aria-hidden="true" size={17} />
          )}
          Enrich with link scanning
        </button>
      </div>
      <div className="field-grid">
        <TextField
          label="Organization"
          value={experience.name}
          onChange={(name) => onChange({ name })}
        />
        <TextField label="Role" value={experience.role} onChange={(role) => onChange({ role })} />
        <TextField
          label="Location"
          value={experience.location}
          onChange={(location) => onChange({ location })}
        />
        <TextField label="Start" value={experience.start} onChange={(start) => onChange({ start })} />
        <TextField
          label="End"
          value={experience.end ?? ""}
          onChange={(end) => onChange({ end: optionalText(end) })}
        />
        <ToggleField
          checked={experience.active}
          label="Active"
          onChange={(active) => onChange({ active })}
        />
      </div>
      <TextareaField
        label="Summary"
        value={experience.summary}
        onChange={(summary) => onChange({ summary })}
      />
      <TextListEditor
        label="Highlights"
        minItems={1}
        values={experience.highlights}
        onChange={(highlights) => onChange({ highlights })}
      />
      <SkillBucketsEditor
        skills={experience.skills}
        onChange={(skills) => onChange({ skills })}
      />
      <TextListEditor
        label="Links"
        values={experience.links ?? []}
        onChange={(links) => onChange({ links: optionalList(links) })}
      />
    </div>
  );
}

function EducationRecordEditor({
  education,
  onChange,
}: {
  education: EducationRecord;
  onChange: (patch: Partial<EducationRecord>) => void;
}) {
  return (
    <div className="editor-surface">
      <SectionHeader title={education.name || "Untitled Education"} eyebrow={education.id} />
      <div className="field-grid">
        <TextField label="Name" value={education.name} onChange={(name) => onChange({ name })} />
        <TextField
          label="Degree"
          value={education.degree}
          onChange={(degree) => onChange({ degree })}
        />
        <TextField label="Grade" value={education.grade} onChange={(grade) => onChange({ grade })} />
        <TextField
          label="Location"
          value={education.location}
          onChange={(location) => onChange({ location })}
        />
        <TextField label="Start" value={education.start} onChange={(start) => onChange({ start })} />
        <TextField
          label="End"
          value={education.end ?? ""}
          onChange={(end) => onChange({ end: optionalText(end) })}
        />
      </div>
      <TextListEditor
        label="Relevant Coursework"
        values={education.relevant_coursework}
        onChange={(relevant_coursework) => onChange({ relevant_coursework })}
      />
    </div>
  );
}

function SkillBucketsEditor({
  skills,
  onChange,
}: {
  skills: ProjectSkills;
  onChange: (skills: ProjectSkills) => void;
}) {
  return (
    <div className="bucket-grid">
      {skillCategories.map((category) => (
        <TextListEditor
          key={category}
          label={categoryLabels[category]}
          values={skills[category]}
          onChange={(values) => onChange({ ...skills, [category]: values })}
        />
      ))}
    </div>
  );
}

function SkillInventoryCategoryEditor({
  focusFirstSequence,
  label,
  onAdd,
  onBlurAway,
  onChange,
  onFocus,
  values,
}: {
  focusFirstSequence?: number;
  label: string;
  onAdd: () => void;
  onBlurAway: (values: string[]) => void;
  onChange: (values: string[]) => void;
  onFocus: () => void;
  values: string[];
}) {
  const firstInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (focusFirstSequence !== undefined) {
      firstInputRef.current?.focus();
    }
  }, [focusFirstSequence]);

  function updateValue(index: number, value: string) {
    const next = [...values];
    next[index] = value;
    onChange(next);
  }

  function removeValue(index: number) {
    onChange(values.filter((_, currentIndex) => currentIndex !== index));
  }

  function handleBlur(event: FocusEvent<HTMLDivElement>) {
    const nextTarget = event.relatedTarget;
    if (nextTarget instanceof Node && event.currentTarget.contains(nextTarget)) {
      return;
    }
    onBlurAway(values);
  }

  return (
    <div className="list-editor" onBlur={handleBlur} onFocus={onFocus}>
      <div className="list-editor-header">
        <span>{label}</span>
        <button
          aria-label={`Add ${label}`}
          className="icon-button"
          title={`Add ${label}`}
          type="button"
          onClick={onAdd}
        >
          <Plus aria-hidden="true" size={16} />
        </button>
      </div>
      {values.length === 0 ? <p className="empty-note">None.</p> : null}
      {values.map((value, index) => (
        <div className="list-row" key={index}>
          <input
            ref={index === 0 ? firstInputRef : undefined}
            aria-label={`${label} ${index + 1}`}
            value={value}
            onChange={(event) => updateValue(index, event.target.value)}
          />
          <button
            aria-label={`Remove ${label} ${index + 1}`}
            className="icon-button danger"
            title={`Remove ${label} ${index + 1}`}
            type="button"
            onClick={() => removeValue(index)}
          >
            <Trash2 aria-hidden="true" size={16} />
          </button>
        </div>
      ))}
    </div>
  );
}

function TextField({
  label,
  onChange,
  value,
}: {
  label: string;
  onChange: (value: string) => void;
  value: string;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      <input value={value} onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}

function SelectField<T extends string>({
  label,
  onChange,
  options,
  value,
}: {
  label: string;
  onChange: (value: T) => void;
  options: Array<{ label: string; value: T }>;
  value: T;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      <select
        aria-label={label}
        value={value}
        onChange={(event) => onChange(event.target.value as T)}
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}

function NumberField({
  defaultLabel,
  label,
  min,
  onChange,
  value,
}: {
  defaultLabel?: string;
  label: string;
  min?: number;
  onChange: (value: number | null) => void;
  value: number | null;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      <input
        aria-label={label}
        min={min}
        step={1}
        type="number"
        value={value ?? ""}
        onChange={(event) => onChange(parseNullableInteger(event.target.value))}
      />
      {value === null && defaultLabel ? <span className="field-hint">{defaultLabel}</span> : null}
    </label>
  );
}

function PasswordField({
  label,
  onChange,
  placeholder,
  value,
}: {
  label: string;
  onChange: (value: string) => void;
  placeholder?: string;
  value: string;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      <input
        aria-label={label}
        autoComplete="off"
        placeholder={placeholder}
        spellCheck={false}
        type="password"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}

function TextareaField({
  label,
  onChange,
  value,
}: {
  label: string;
  onChange: (value: string) => void;
  value: string;
}) {
  return (
    <label className="field full">
      <span>{label}</span>
      <textarea value={value} onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}

function ToggleField({
  checked,
  label,
  onChange,
}: {
  checked: boolean;
  label: string;
  onChange: (value: boolean) => void;
}) {
  return (
    <label className="toggle-field">
      <input
        checked={checked}
        type="checkbox"
        onChange={(event) => onChange(event.target.checked)}
      />
      <span>{label}</span>
    </label>
  );
}

function TextListEditor({
  label,
  minItems = 0,
  onChange,
  values,
}: {
  label: string;
  minItems?: number;
  onChange: (values: string[]) => void;
  values: string[];
}) {
  function updateValue(index: number, value: string) {
    const next = [...values];
    next[index] = value;
    onChange(next);
  }

  function removeValue(index: number) {
    if (values.length <= minItems) {
      return;
    }
    onChange(values.filter((_, currentIndex) => currentIndex !== index));
  }

  return (
    <div className="list-editor">
      <div className="list-editor-header">
        <span>{label}</span>
        <button
          aria-label={`Add ${label}`}
          className="icon-button"
          title={`Add ${label}`}
          type="button"
          onClick={() => onChange([...values, ""])}
        >
          <Plus aria-hidden="true" size={16} />
        </button>
      </div>
      {values.length === 0 ? <p className="empty-note">None.</p> : null}
      {values.map((value, index) => (
        <div className="list-row" key={index}>
          <input
            aria-label={`${label} ${index + 1}`}
            value={value}
            onChange={(event) => updateValue(index, event.target.value)}
          />
          <button
            aria-label={`Remove ${label} ${index + 1}`}
            className="icon-button danger"
            disabled={values.length <= minItems}
            title={`Remove ${label} ${index + 1}`}
            type="button"
            onClick={() => removeValue(index)}
          >
            <Trash2 aria-hidden="true" size={16} />
          </button>
        </div>
      ))}
    </div>
  );
}

function SectionHeader({
  compact = false,
  eyebrow,
  title,
}: {
  compact?: boolean;
  eyebrow: string;
  title: string;
}) {
  return (
    <div className={`section-header ${compact ? "compact" : ""}`}>
      <span>{eyebrow}</span>
      <h2>{title}</h2>
    </div>
  );
}

function StatePanel({
  children,
  detail,
  icon: Icon,
  spin = false,
  title,
  tone,
}: {
  children?: ReactNode;
  detail?: string;
  icon: LucideIcon;
  spin?: boolean;
  title: string;
  tone?: "error";
}) {
  return (
    <div className={`state-panel ${tone ?? ""}`}>
      <Icon className={spin ? "spin" : ""} aria-hidden="true" size={28} />
      <h2>{title}</h2>
      {detail ? <p>{detail}</p> : null}
      {children}
    </div>
  );
}

function buildGenerationConfigPatch({
  baseline,
  clearGithubToken,
  clearOpenAiKey,
  clearQwenKey,
  draft,
  githubTokenDraft,
  openAiKeyDraft,
  qwenKeyDraft,
}: {
  baseline: ResumeGenerationConfig;
  clearGithubToken: boolean;
  clearOpenAiKey: boolean;
  clearQwenKey: boolean;
  draft: ResumeGenerationConfig;
  githubTokenDraft: string;
  openAiKeyDraft: string;
  qwenKeyDraft: string;
}): ResumeGenerationConfigPatch {
  const patch: ResumeGenerationConfigPatch = {};

  if (baseline.llm_provider !== draft.llm_provider) {
    patch.llm_provider = draft.llm_provider;
  }
  if (
    baseline.bullet_point_generation_strategy
    !== draft.bullet_point_generation_strategy
  ) {
    patch.bullet_point_generation_strategy = draft.bullet_point_generation_strategy;
  }
  if (baseline.skill_selection.top_n !== draft.skill_selection.top_n) {
    patch.skill_selection = { top_n: draft.skill_selection.top_n };
  }
  if (baseline.project_selection.top_n !== draft.project_selection.top_n) {
    patch.project_selection = { top_n: draft.project_selection.top_n };
  }
  if (baseline.experience_selection.top_n !== draft.experience_selection.top_n) {
    patch.experience_selection = { top_n: draft.experience_selection.top_n };
  }
  if (!deepEqual(baseline.link_scanning, draft.link_scanning)) {
    patch.link_scanning = {
      highlight_count: draft.link_scanning.highlight_count,
      max_tokens_per_highlight: draft.link_scanning.max_tokens_per_highlight,
    };
  }
  if (!deepEqual(baseline.bullet_count_range, draft.bullet_count_range)) {
    patch.bullet_count_range = draft.bullet_count_range;
  }
  if (baseline.resume_output.output_dir !== draft.resume_output.output_dir) {
    patch.resume_output = { output_dir: draft.resume_output.output_dir.trim() };
  }

  const trimmedKey = openAiKeyDraft.trim();
  if (trimmedKey) {
    patch.openai = { api_key: trimmedKey };
  } else if (clearOpenAiKey) {
    patch.openai = { clear_api_key: true };
  }

  if (baseline.qwen_base_url !== draft.qwen_base_url) {
    patch.qwen = { base_url: draft.qwen_base_url.trim() };
  }
  const trimmedQwenKey = qwenKeyDraft.trim();
  if (trimmedQwenKey) {
    patch.qwen = { ...patch.qwen, api_key: trimmedQwenKey };
  } else if (clearQwenKey) {
    patch.qwen = { ...patch.qwen, clear_api_key: true };
  }

  const trimmedGithubToken = githubTokenDraft.trim();
  if (trimmedGithubToken) {
    patch.github = { token: trimmedGithubToken };
  } else if (clearGithubToken) {
    patch.github = { clear_token: true };
  }

  return patch;
}

function normalizeJobTargetForSave(jobTarget: JobTarget): JobTarget {
  const description = jobTarget.description?.trim() ?? "";
  return {
    schema_version: 1,
    title: jobTarget.title.trim(),
    description: description ? description : null,
  };
}

function configExposedValuesChanged(
  baseline: ResumeGenerationConfig | null,
  draft: ResumeGenerationConfig | null,
): boolean {
  if (!baseline || !draft) {
    return false;
  }
  return !deepEqual(
    {
      llm_provider: baseline.llm_provider,
      bullet_point_generation_strategy: baseline.bullet_point_generation_strategy,
      skill_selection: baseline.skill_selection,
      project_selection: baseline.project_selection,
      experience_selection: baseline.experience_selection,
      link_scanning: baseline.link_scanning,
      resume_output: {
        output_dir: baseline.resume_output.output_dir,
      },
      bullet_count_range: baseline.bullet_count_range,
      qwen_base_url: baseline.qwen_base_url,
    },
    {
      llm_provider: draft.llm_provider,
      bullet_point_generation_strategy: draft.bullet_point_generation_strategy,
      skill_selection: draft.skill_selection,
      project_selection: draft.project_selection,
      experience_selection: draft.experience_selection,
      link_scanning: draft.link_scanning,
      resume_output: {
        output_dir: draft.resume_output.output_dir,
      },
      bullet_count_range: draft.bullet_count_range,
      qwen_base_url: draft.qwen_base_url,
    },
  );
}

function updateBulletCountRange(
  config: ResumeGenerationConfig,
  onChange: (mutator: (next: ResumeGenerationConfig) => void) => void,
  bound: keyof BulletCountRangeConfig,
  value: number | null,
): void {
  onChange((next) => {
    if (value === null) {
      next.bullet_count_range = null;
      return;
    }
    const current = next.bullet_count_range ?? config.default_values.bullet_count_range;
    next.bullet_count_range = { ...current, [bound]: value };
  });
}

function openAiKeyStatus(
  config: ResumeGenerationConfig,
  openAiKeyDraft: string,
  clearOpenAiKey: boolean,
): string {
  if (clearOpenAiKey) {
    return "will clear";
  }
  if (openAiKeyDraft.trim()) {
    return config.openai_api_key_saved ? "will replace" : "will save";
  }
  if (config.openai_api_key_source === "environment") {
    return "set by environment";
  }
  if (config.openai_api_key_saved) {
    return "saved";
  }
  return "not set";
}

function qwenKeyStatus(
  config: ResumeGenerationConfig,
  qwenKeyDraft: string,
  clearQwenKey: boolean,
): string {
  if (clearQwenKey) {
    return "will clear";
  }
  if (qwenKeyDraft.trim()) {
    return config.qwen_api_key_saved ? "will replace" : "will save";
  }
  if (config.qwen_api_key_source === "environment") {
    return "set by environment";
  }
  if (config.qwen_api_key_saved) {
    return "saved";
  }
  return "not set";
}

function githubTokenStatus(
  config: ResumeGenerationConfig,
  githubTokenDraft: string,
  clearGithubToken: boolean,
): string {
  if (clearGithubToken) {
    return "will clear";
  }
  if (githubTokenDraft.trim()) {
    return config.github_token_saved ? "will replace" : "will save";
  }
  if (config.github_token_source === "environment") {
    return "set by environment";
  }
  if (config.github_token_saved) {
    return "saved";
  }
  return "not set";
}

function parseNullableInteger(value: string): number | null {
  const trimmed = value.trim();
  if (!trimmed) {
    return null;
  }
  const parsed = Number(trimmed);
  return Number.isFinite(parsed) ? parsed : null;
}

function sectionCount(section: SectionKey, evidence: ResumeEvidenceRegistry): number | undefined {
  if (section === "projects") {
    return evidence.projects.projects.length;
  }
  if (section === "experience") {
    return evidence.experience.experience.length;
  }
  if (section === "education") {
    return evidence.education.education.length;
  }
  return undefined;
}

function generationRunLabel(status: ResumeGenerationStatus["status"]): string {
  if (status === "idle") {
    return "Idle";
  }
  if (status === "running") {
    return "Running";
  }
  if (status === "succeeded") {
    return "Succeeded";
  }
  return "Failed";
}

function generationStageLabel(status: ResumeGenerationStatusStage["status"]): string {
  if (status === "pending") {
    return "Pending";
  }
  if (status === "running") {
    return "Running";
  }
  if (status === "succeeded") {
    return "Done";
  }
  return "Failed";
}

function formatStatusTime(value: string | null | undefined): string {
  if (!value) {
    return "None";
  }
  return new Intl.DateTimeFormat(undefined, {
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date(value));
}

function countSkills(skills: ProjectSkills): number {
  return skills.technology.length + skills.programming.length + skills.concepts.length;
}

function optionalText(value: string): string | null {
  return value.length > 0 ? value : null;
}

function optionalList(values: string[]): string[] | null {
  return values.length > 0 ? values : null;
}

function formatError(error: unknown): string {
  if (error instanceof ApiError) {
    return error.detail;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "Unknown error.";
}

function isPdfPrerequisiteError(error: unknown): boolean {
  return (
    error instanceof ApiError &&
    error.status === 502 &&
    error.detail.startsWith(PDF_PREREQUISITE_ERROR_PREFIX)
  );
}
