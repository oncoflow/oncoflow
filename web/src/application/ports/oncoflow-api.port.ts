import type {
  AgentModuleInfo,
  BatchStatus,
  BugReportItem,
  CitationRef,
  ClinicalDomain,
  Language,
  MdtFormCard,
  MdtFormDetail,
  PatientListItem,
  QueueJobItem,
  QueueStats,
  ResourceDocument,
} from "../../domain/types.js";

export interface UploadFileInput {
  filename: string;
  content: Buffer;
  patientId?: string | null;
}

export interface ChatReply {
  answer: string;
  references: CitationRef[];
}

export interface OncoflowApiPort {
  // Worklist & Patients
  listPatientCards(domain: ClinicalDomain): Promise<MdtFormCard[]>;
  listRcpCards(domain: ClinicalDomain): Promise<MdtFormCard[]>;
  listPatients(domain: ClinicalDomain, identifiedOnly?: boolean): Promise<PatientListItem[]>;
  deletePatient(patientId: string, domain: ClinicalDomain): Promise<void>;
  deleteForm(filename: string, domain: ClinicalDomain): Promise<void>;

  // Dossier & Longitudinal Forms
  resolveTarget(
    target: string,
    domain: ClinicalDomain,
  ): Promise<{ kind: "patient" | "form"; patientId?: string | null; filename?: string | null }>;
  getFormDetail(filename: string, domain: ClinicalDomain): Promise<MdtFormDetail | null>;
  getPatientForms(patientId: string, domain: ClinicalDomain): Promise<MdtFormDetail[]>;
  updateFormSection(
    filename: string,
    section: string,
    data: Record<string, unknown>,
    editedBy: string,
    domain: ClinicalDomain,
  ): Promise<MdtFormDetail>;
  rerunSection(
    filename: string,
    section: string,
    preserveManualEdits: boolean,
    domain: ClinicalDomain,
  ): Promise<{ jobId: string; preserveManualEdits: boolean }>;
  processFullForm(
    filename: string,
    preserveManualEdits: boolean,
    domain: ClinicalDomain,
  ): Promise<{ jobId: string }>;
  linkFormToPatient(
    filename: string,
    patientId: string | null,
    domain: ClinicalDomain,
  ): Promise<void>;
  getFormPdfBuffer(
    filename: string,
    domain: ClinicalDomain,
    variant?: "plain" | "bbox",
  ): Promise<Buffer | null>;
  askDossierQuestion(
    target: { filename?: string; patientId?: string },
    question: string,
    domain: ClinicalDomain,
    language: Language,
    agentName?: string,
  ): Promise<ChatReply>;

  // Ingest & Batch Tracking
  uploadForms(
    files: UploadFileInput[],
    batchId: string,
    domain: ClinicalDomain,
  ): Promise<{ batchId: string; filenames: string[] }>;
  getBatchStatus(batchId: string, domain: ClinicalDomain): Promise<BatchStatus>;

  // Guidelines & Specialty Agents
  listResources(domain: ClinicalDomain): Promise<ResourceDocument[]>;
  uploadResource(
    filename: string,
    content: Buffer,
    domain: ClinicalDomain,
  ): Promise<ResourceDocument>;
  reindexResource(filename: string, domain: ClinicalDomain): Promise<void>;
  deleteResource(filename: string, domain: ClinicalDomain): Promise<void>;
  getResourcePdfBuffer(filename: string, domain: ClinicalDomain): Promise<Buffer | null>;
  listAgents(domain: ClinicalDomain, language: Language): Promise<AgentModuleInfo[]>;
  askGuidelineQuestion(
    question: string,
    domain: ClinicalDomain,
    language: Language,
    filename?: string,
  ): Promise<ChatReply>;

  // Bug Reports & Feedback
  listBugs(domain: ClinicalDomain): Promise<BugReportItem[]>;
  createBug(input: Omit<BugReportItem, "id" | "createdAt" | "status">): Promise<BugReportItem>;
  updateBugStatus(id: string, status: string, domain: ClinicalDomain): Promise<BugReportItem>;
  deleteBug(id: string, domain: ClinicalDomain): Promise<void>;

  // Queue Supervision & Admin
  getQueueStats(domain: ClinicalDomain, allDomains?: boolean): Promise<QueueStats>;
  listQueueJobs(domain: ClinicalDomain, allDomains?: boolean): Promise<QueueJobItem[]>;
  retryQueueJob(jobId: string, domain: ClinicalDomain): Promise<void>;
  cancelOrDeleteQueueJob(jobId: string, domain: ClinicalDomain): Promise<void>;
  cleanQueue(mode: "completed" | "failed" | "all", domain: ClinicalDomain): Promise<number>;
  releaseGpuLocks(domain: ClinicalDomain): Promise<{ released: number }>;
}
