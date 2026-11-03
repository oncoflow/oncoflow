import { z } from "zod";
import { normalizePriorityLevel } from "../../domain/triage.js";
import type {
  ClinicalDomain,
  Language,
  MdtAgendaSortStrategy,
  ThemeMode,
  WorklistFilter,
} from "../../domain/types.js";

/**
 * Helper to coerce unknown values to trimmed string or empty string.
 */
const trimmedString = z.preprocess(
  (val) => (val === null || val === undefined ? "" : String(val).trim()),
  z.string(),
);

const optionalTrimmedString = z.preprocess((val) => {
  if (val === null || val === undefined) return undefined;
  const s = String(val).trim();
  return s.length > 0 ? s : undefined;
}, z.string().optional());

/**
 * 1. Environment Configuration Schema (`config.ts`)
 */
export const EnvConfigSchema = z.object({
  PORT_WEB: optionalTrimmedString,
  PORT: optionalTrimmedString,
  HOST_WEB: optionalTrimmedString,
  APP_API_URL: optionalTrimmedString,
  APP_QUEUE_API_URL: optionalTrimmedString,
  APP_API_TOKEN: optionalTrimmedString,
  APP_PROXY_SECRET: optionalTrimmedString,
  APP_AUTH_MODE: optionalTrimmedString,
  APP_DEV_MODE: optionalTrimmedString,
  NODE_ENV: optionalTrimmedString,
  APP_ADMIN_USERS: optionalTrimmedString,
  APP_DOMAIN: optionalTrimmedString,
  APP_ALLOWED_DOMAINS: optionalTrimmedString,
  APP_LANGUAGE: optionalTrimmedString,
  APP_THEME: optionalTrimmedString,
  WEB_FAKE_API_FALLBACK: optionalTrimmedString,
  APP_USE_FAKE_ONLY: optionalTrimmedString,
});

/**
 * 2. Fastify BFF Route Query & Body Schemas (`server.ts`)
 */
export const PreferencesBodySchema = z.object({
  theme: z.enum(["auto", "light", "dark"]).optional().catch(undefined),
  language: z.enum(["fr", "en"]).optional().catch(undefined),
  domain: z.enum(["oncology", "sma"]).optional().catch(undefined),
  expertMode: z.enum(["true", "false"]).optional().catch(undefined),
});

export const WorklistQuerySchema = z.object({
  q: optionalTrimmedString,
  completeness: z.enum(["all", "complete", "incomplete"]).catch("all"),
  priority: z.enum(["all", "high", "medium", "low"]).catch("all"),
  orientation: z.enum(["all", "adapt", "standard", "pending"]).catch("all"),
  viewMode: z.enum(["patients", "rcp"]).catch("patients"),
  display: z.enum(["cards", "table"]).optional().catch(undefined),
  sortBy: z
    .enum(["priority", "patient", "date", "completeness", "orientation", "specialties"])
    .catch("priority"),
  sortDir: z.enum(["asc", "desc"]).catch("asc"),
  domain: optionalTrimmedString,
});

export function parseWorklistFilter(
  rawQuery: unknown,
  domain: ClinicalDomain,
  defaultDisplay: "cards" | "table",
): WorklistFilter {
  const parsed = WorklistQuerySchema.parse(rawQuery ?? {});
  return {
    query: parsed.q,
    completeness: parsed.completeness,
    priority: parsed.priority,
    orientation: parsed.orientation,
    viewMode: parsed.viewMode,
    displayMode: parsed.display ?? defaultDisplay,
    sortBy: parsed.sortBy,
    sortDir: parsed.sortDir,
    domain,
  };
}

const stringOrStringArray = z
  .union([z.string(), z.array(z.string())])
  .optional()
  .catch(undefined);

export function normalizeFormStringList(
  presentFlag: string | undefined,
  rawField: string | string[] | undefined,
): string[] | undefined {
  if (presentFlag !== "true") return undefined;
  if (Array.isArray(rawField)) {
    return rawField.map((x) => x.trim()).filter(Boolean);
  }
  if (typeof rawField === "string" && rawField.trim()) {
    return [rawField.trim()];
  }
  return [];
}

export const AgendaSortStrategySchema = z.enum([
  "hybrid",
  "urgency_first",
  "expert_grouping",
  "manual",
]);

export const AgendaOptionsBodySchema = z.object({
  sortStrategy: AgendaSortStrategySchema.optional().catch(undefined),
  deferIncompleteFilesPresent: optionalTrimmedString,
  deferIncompleteFiles: optionalTrimmedString,
  toggleExpert: optionalTrimmedString,
  attendingExpertsPresent: optionalTrimmedString,
  attendingExperts: stringOrStringArray,
  sessionDate: optionalTrimmedString,
});

export const AgendaScheduleBodySchema = z.object({
  sortStrategy: AgendaSortStrategySchema.catch("hybrid" as MdtAgendaSortStrategy),
  sessionDate: optionalTrimmedString,
  attendingExpertsPresent: optionalTrimmedString,
  attendingExperts: stringOrStringArray,
  patientIdsPresent: optionalTrimmedString,
  patientIds: stringOrStringArray,
});

export const AgendaEnrollBodySchema = z.object({
  patientId: optionalTrimmedString,
  patientIds: z
    .array(z.string())
    .transform((arr) => arr.map((x) => x.trim()).filter(Boolean))
    .optional()
    .catch(undefined),
  enrollAllCandidates: z.preprocess((v) => v === "true" || v === true, z.boolean()).catch(false),
  filterMode: z.enum(["all", "complete", "urgent"]).catch("all"),
});

export const AgendaMoveBodySchema = z.object({
  direction: z.enum(["up", "down"]).optional().catch(undefined),
  targetPosition: z
    .preprocess((v) => {
      if (v === undefined || v === null || v === "") return undefined;
      const n = Number(v);
      return Number.isNaN(n) ? undefined : n;
    }, z.number().int().positive().optional())
    .catch(undefined),
  pinned: z
    .preprocess(
      (v) => (v === "true" ? true : v === "false" ? false : undefined),
      z.boolean().optional(),
    )
    .catch(undefined),
});

export const MissingItemsBodySchema = z.object({
  toggle_item: optionalTrimmedString,
  hide_missing_items: z
    .preprocess(
      (v) => (v === "true" ? true : v === "false" ? false : undefined),
      z.boolean().optional(),
    )
    .catch(undefined),
  restore_all: z.preprocess((v) => v === "true" || v === true, z.boolean()).catch(false),
});

export const ChatBodySchema = z.object({
  question: trimmedString.catch(""),
  scope: z.enum(["patient", "form"]).catch("patient"),
  filename: optionalTrimmedString,
  agentName: optionalTrimmedString,
});

export const FeedbackCreateBodySchema = z.object({
  title: trimmedString.transform((s) => s || "Signalement"),
  description: trimmedString.catch(""),
  category: optionalTrimmedString.transform((s) => s ?? "extraction"),
  severity: optionalTrimmedString.transform((s) => s ?? "medium"),
  patientOrFile: optionalTrimmedString.transform((s) => s ?? null),
});

export const FeedbackStatusBodySchema = z.object({
  status: optionalTrimmedString.transform((s) => s ?? "open"),
});

export const QueueCleanBodySchema = z.object({
  mode: z.enum(["completed", "failed", "all"]).catch("completed"),
});

/**
 * 3. FastAPI Upstream Response Schemas (`http-oncoflow-api.adapter.ts`)
 */
const NOT_GIVEN_VALUES = new Set(["Not_given", "not_given", "Non spécifié", "None", "null", ""]);

export function formatCleanIsoDate(rawVal: unknown): string | null {
  if (!rawVal) return null;
  const str = String(rawVal).trim();
  if (NOT_GIVEN_VALUES.has(str)) {
    return null;
  }
  if (str.includes("T") && str.length >= 10) {
    return str.slice(0, 10);
  }
  return str;
}

export function cleanNullableString(rawVal: unknown): string | null {
  if (rawVal === null || rawVal === undefined) return null;
  const str = String(rawVal).trim();
  return NOT_GIVEN_VALUES.has(str) ? null : str;
}

export const RawQueueStatsSchema = z
  .object({
    pending: z.coerce.number().catch(0),
    processing: z.coerce.number().optional(),
    running: z.coerce.number().optional(),
    completed: z.coerce.number().catch(0),
    failed: z.coerce.number().catch(0),
    cancelled: z.coerce.number().catch(0),
    total: z.coerce.number().optional(),
    active_filename: z.string().nullable().optional(),
    active_step: z.string().nullable().optional(),
    active_progress_pct: z.coerce.number().optional(),
    thinking_preview: z.string().nullable().optional(),
    active_locks: z.coerce.number().optional(),
    gpu_locks_count: z.coerce.number().optional(),
  })
  .passthrough();

export const RawQueueJobSchema = z
  .object({
    job_id: z.unknown().optional(),
    id: z.unknown().optional(),
    job_type: z.unknown().optional(),
    status: z.unknown().optional(),
    priority: z.coerce.number().catch(2),
    domain: z.unknown().optional(),
    filename: z.unknown().optional(),
    model_name: z.unknown().optional(),
    section: z.unknown().optional(),
    progress_pct: z.coerce.number().catch(0),
    current_step: z.unknown().optional(),
    step: z.unknown().optional(),
    created_at: z.unknown().optional(),
    started_at: z.unknown().optional(),
    completed_at: z.unknown().optional(),
    error_message: z.unknown().optional(),
    error: z.unknown().optional(),
    preserve_manual_edits: z.boolean().optional(),
  })
  .passthrough();

export const RawResourceSchema = z
  .object({
    filename: z.unknown().optional(),
    name: z.unknown().optional(),
    size_bytes: z.coerce.number().optional(),
    size: z.coerce.number().optional(),
    is_indexed: z.boolean().optional(),
    indexed: z.boolean().optional(),
    chunk_count: z.coerce.number().optional(),
    chunks: z.coerce.number().optional(),
    updated_at: z.unknown().optional(),
  })
  .passthrough();

export const RawBugReportSchema = z
  .object({
    bug_id: z.unknown().optional(),
    id: z.unknown().optional(),
    _id: z.unknown().optional(),
    title: z.unknown().optional(),
    description: z.unknown().optional(),
    category: z.unknown().optional(),
    severity: z.unknown().optional(),
    status: z.unknown().optional(),
    domain: z.unknown().optional(),
    patient_or_file: z.unknown().optional(),
    patient_id: z.unknown().optional(),
    rcp_file: z.unknown().optional(),
    author: z.unknown().optional(),
    reporter: z.unknown().optional(),
    created_at: z.unknown().optional(),
  })
  .passthrough();

export function resolveClinicalDomain(
  raw: string | undefined,
  fallback: ClinicalDomain = "oncology",
): ClinicalDomain {
  const norm = (raw ?? "").trim().toLowerCase();
  if (norm === "sma") return "sma";
  if (norm === "oncology") return "oncology";
  return fallback;
}

export function resolveLanguage(raw: string | undefined, fallback: Language = "fr"): Language {
  const norm = (raw ?? "").trim().toLowerCase();
  if (norm === "en" || norm === "english") return "en";
  if (norm === "fr" || norm === "french") return "fr";
  return fallback;
}

export function resolveThemeMode(raw: string | undefined, fallback: ThemeMode = "auto"): ThemeMode {
  const norm = (raw ?? "").trim().toLowerCase();
  if (norm === "dark") return "dark";
  if (norm === "light") return "light";
  if (norm === "auto") return "auto";
  return fallback;
}

export { normalizePriorityLevel };
