export type ClinicalDomain = "oncology" | "sma";
export type PriorityLevel = "high" | "medium" | "low" | "none";
export type CompletenessStatus = "complete" | "incomplete";
export type OrientationStatus = "adapt" | "standard" | "pending";
export type Language = "fr" | "en";
export type ThemeMode = "auto" | "light" | "dark";

export interface UserSession {
  userId: string;
  userName: string;
  isAdmin: boolean;
  domain: ClinicalDomain;
  hostBoundDomain?: boolean;
  allowedDomains: ClinicalDomain[];
  language: Language;
  theme: ThemeMode;
  expertMode: boolean;
}

export interface MdtFormCard {
  id: string;
  file: string;
  link?: string;
  patientId: string | null;
  patientName: string;
  firstName: string;
  lastName: string;
  dateBirth?: string | null;
  gender?: string | null;
  domain: ClinicalDomain;
  mdtDate: string | null;
  priorityLevel: PriorityLevel;
  isComplete: boolean;
  missingCount: number;
  missingItems: string[];
  careAdaptationSuggested: boolean | null;
  proposedCareType: string | null;
  specialties: string[];
  processingStatus: "PENDING" | "RUNNING" | "COMPLETED" | "FAILED" | string;
  processingStep: string | null;
  processingProgressPct: number;
  rcpCount: number;
  summaryText: string;
}

export interface ManualFieldDiff {
  ai_value?: unknown;
  human_value?: unknown;
}

export interface ManualEditMetadata {
  is_manual?: boolean;
  edited_at?: string;
  edited_by?: string;
  previous_ai_value?: unknown;
  modified_fields?: Record<string, ManualFieldDiff>;
}

export interface CardMetrics {
  priority_level?: string | null;
  is_complete?: boolean;
  missing_count?: number;
  missing_items?: string[];
  all_missing_items?: string[];
  hidden_missing_items?: string[];
  hide_missing_items?: boolean;
  care_adaptation_suggested?: boolean | null;
  proposed_care_type?: string | null;
  specialties?: string[];
  [key: string]: unknown;
}

export interface MdtFormDetail {
  file: string;
  link?: string | null;
  patientId: string | null;
  domain: ClinicalDomain;
  mdtDate: string | null;
  processingStatus: string;
  processingStep: string | null;
  processingProgressPct: number;
  sections: Record<string, Record<string, unknown>>;
  manualEdits: Record<string, ManualEditMetadata>;
  executionTimes: Record<string, number>;
  metrics: CardMetrics;
  markdownText?: string;
  chunks?: Array<{
    index: number;
    content: string;
    metadata?: Record<string, unknown>;
  }>;
}

export interface PatientListItem {
  id: string;
  firstName: string;
  lastName: string;
  bornName?: string | null;
  dateBirth?: string | null;
  gender?: string | null;
  rcpCount: number;
}

export interface LongitudinalDelta {
  key: string;
  label: string;
  currentValue: string;
  previousValue: string;
  previousDate: string;
  deltaText: string;
  direction: "better" | "worse" | "stable" | "new";
  icon: string;
}

export interface CitationRef {
  name: string;
  page?: string | number | null;
  position?: string | null;
  excerpt?: string | null;
}

export interface ExpertSuggestion {
  suggestion: string;
  why?: string;
  references: CitationRef[];
}

export interface SpecialtyOpinionItem {
  agentKey: string;
  agentLabel: string;
  agentIcon: string;
  relevant: boolean;
  priorityLevel: PriorityLevel;
  whyRelevant: string;
  suggestions: ExpertSuggestion[];
  sources: CitationRef[];
  reasoningThinking?: string | null;
  executionSeconds?: number | null;
}

export interface QueueJobItem {
  jobId: string;
  jobType: string;
  status: string;
  priority: number;
  domain: string;
  filename: string | null;
  section: string | null;
  progressPct: number;
  step: string | null;
  createdAt: string | null;
  startedAt: string | null;
  completedAt: string | null;
  error: string | null;
  preserveManualEdits?: boolean;
}

export interface QueueStats {
  pending: number;
  running: number;
  completed: number;
  failed: number;
  cancelled: number;
  total: number;
  activeFormFile: string | null;
  activeStep: string | null;
  activeProgressPct: number;
  thinkingPreview: string | null;
  gpuLocksCount: number;
}

export interface BatchFileStatus {
  filename: string;
  status: string;
  step: string | null;
  progressPct: number;
  error: string | null;
  patientId: string | null;
}

export interface BatchStatus {
  batchId: string;
  total: number;
  completed: number;
  running: number;
  pending: number;
  failed: number;
  progressPct: number;
  files: BatchFileStatus[];
}

export interface ResourceDocument {
  filename: string;
  sizeBytes: number;
  indexed: boolean;
  chunkCount: number;
  updatedAt: string | null;
}

export interface AgentUserPromptItem {
  section: string;
  title: string;
  prompt: string;
}

export interface AgentModuleInfo {
  name: string;
  label: string;
  icon: string;
  role: string;
  description: string;
  guidelines: string[];
  models?: string[];
  systemPrompt?: string;
  userPrompts?: AgentUserPromptItem[];
}

export interface BugReportItem {
  id: string;
  title: string;
  description: string;
  category: string;
  severity: string;
  status: "open" | "in_progress" | "resolved" | "closed" | string;
  domain: string;
  patientOrFile: string | null;
  author: string | null;
  createdAt: string;
}

export interface WorklistFilter {
  query?: string;
  completeness?: "all" | "complete" | "incomplete";
  priority?: "all" | "high" | "medium" | "low";
  orientation?: "all" | "adapt" | "standard" | "pending";
  domain?: "all" | ClinicalDomain;
  viewMode?: "patients" | "rcp";
  displayMode?: "table" | "cards";
  sortBy?: "priority" | "patient" | "date" | "completeness" | "orientation" | "specialties";
  sortDir?: "asc" | "desc";
  dense?: boolean;
}

export interface WorklistKpis {
  structuredCount: number;
  highPriorityCount: number;
  incompleteCount: number;
  adaptationSuggestedCount: number;
}

export type MdtAgendaSortStrategy = "hybrid" | "urgency_first" | "expert_grouping" | "manual";

export interface MdtAgendaItem {
  position: number;
  patientId: string;
  filename: string;
  patientName: string;
  firstName: string;
  lastName: string;
  dateBirth: string | null;
  urgency: string;
  urgencyScore: number;
  priorityLevel: PriorityLevel;
  isComplete: boolean;
  missingCount: number;
  missingItems: string[];
  careAdaptationSuggested: boolean | null;
  proposedCareType: string | null;
  requiredExperts: string[];
  presentRequiredExperts: string[];
  absentRequiredExperts: string[];
  quorumMet: boolean;
  expertCoverageRatio: number;
  clusterKey: string;
  pinned: boolean;
  rankReason: string;
  mdtDate: string | null;
}

export interface MdtExpertWindow {
  expertName: string;
  isAttending: boolean;
  caseCount: number;
  urgentCaseCount: number;
  firstPosition: number | null;
  lastPosition: number | null;
  isContiguous: boolean;
  patientIds: string[];
}

export interface MdtAgendaCandidate {
  patientId: string;
  filename: string;
  patientName: string;
  firstName: string;
  lastName: string;
  dateBirth: string | null;
  urgency: string;
  urgencyScore: number;
  priorityLevel: PriorityLevel;
  isComplete: boolean;
  missingCount: number;
  missingItems: string[];
  careAdaptationSuggested: boolean | null;
  proposedCareType: string | null;
  requiredExperts: string[];
  mdtDate: string | null;
}

export interface MdtAgendaView {
  agendaId: string;
  domain: ClinicalDomain;
  sessionDate: string;
  sortStrategy: MdtAgendaSortStrategy;
  deferIncompleteFiles: boolean;
  availableExperts: string[];
  attendingExperts: string[];
  totalEnrolled: number;
  urgentCount: number;
  incompleteCount: number;
  quorumWarningCount: number;
  items: MdtAgendaItem[];
  expertWindows: MdtExpertWindow[];
  candidates: MdtAgendaCandidate[];
  updatedAt: string | null;
}

export interface MdtAgendaUpdateInput {
  sessionDate?: string;
  sortStrategy?: MdtAgendaSortStrategy;
  deferIncompleteFiles?: boolean;
  attendingExperts?: string[];
  toggleExpert?: string;
  patientIds?: string[];
  resetEnrolledPatients?: boolean;
}

export interface MdtAgendaEnrollInput {
  patientIds?: string[];
  patientId?: string;
  enrollAllCandidates?: boolean;
  filterMode?: "all" | "complete" | "urgent";
}

export interface MdtAgendaMoveInput {
  direction?: "up" | "down";
  targetPosition?: number;
  pinned?: boolean;
}

export interface FormSectionSchema {
  name: string;
  description: string;
  question?: string | null;
  multi_agent: boolean;
  collaborative?: boolean;
  agents: string[];
  editable: boolean;
  json_schema: Record<string, unknown>;
}

export interface DomainFormSchema {
  domain: ClinicalDomain | string;
  sections: FormSectionSchema[];
  enums: Record<string, Array<string | number>>;
}
