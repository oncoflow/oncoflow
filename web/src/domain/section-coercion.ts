import {
  type FieldSelectOption,
  getSectionFieldSchemas,
  resolveCanonicalSectionName,
  type SectionFieldSchema,
} from "./field-schema.js";
import type { DomainFormSchema } from "./types.js";

const EMPTY_PLACEHOLDERS = new Set([
  "",
  "-",
  "—",
  "null",
  "undefined",
  "none",
  "aucun",
  "aucune",
  "non renseigné",
  "non renseigne",
  "non spécifié",
  "non specifie",
  "non mentionné",
  "non mentionne",
  "not documented",
  "not documented in record",
  "not mentioned",
  "not mentioned in record",
  "not_given",
  "no data",
]);

export function isPlaceholderValue(val: unknown): boolean {
  if (val === null || val === undefined) return true;
  if (typeof val === "string") {
    return EMPTY_PLACEHOLDERS.has(val.trim().toLowerCase());
  }
  return false;
}

export function formatRawEditValue(val: unknown, schema?: SectionFieldSchema): string {
  if (val === null || val === undefined) return "";
  if (schema?.inputType === "boolean") {
    return coerceBooleanValue(val, Boolean(schema.defaultValue ?? false)) ? "true" : "false";
  }
  if (schema?.inputType === "nullable_boolean") {
    const parsed = coerceNullableBooleanValue(val);
    return parsed === null ? "" : parsed ? "true" : "false";
  }
  if (schema?.inputType === "string_list") {
    if (Array.isArray(val)) {
      return val
        .map((item) => String(item ?? "").trim())
        .filter((s) => s.length > 0 && !isPlaceholderValue(s))
        .join(", ");
    }
    if (typeof val === "string") {
      return isPlaceholderValue(val) ? "" : val.trim();
    }
    return "";
  }
  if (schema?.inputType === "date") {
    const iso = coerceDateValue(val);
    return iso ?? "";
  }
  if (schema?.inputType === "integer" || schema?.inputType === "integer_select") {
    const num = coerceNumberValue(val, true, schema.min, schema.max);
    if (num === null) {
      return schema.nullable ? "" : String(schema.defaultValue ?? 0);
    }
    return String(num);
  }
  if (schema?.inputType === "float") {
    const num = coerceNumberValue(val, false, schema.min, schema.max);
    if (num === null) {
      return schema.nullable ? "" : String(schema.defaultValue ?? 0);
    }
    return String(num);
  }
  if (schema?.inputType === "select" && schema.options) {
    return coerceSelectValue(val, schema.options, String(schema.defaultValue ?? ""));
  }
  if (typeof val === "string") {
    return isPlaceholderValue(val) ? "" : val;
  }
  if (typeof val === "number" || typeof val === "boolean") {
    return String(val);
  }
  return "";
}

export function coerceBooleanValue(val: unknown, fallback = false): boolean {
  if (typeof val === "boolean") return val;
  if (typeof val === "number") return val !== 0;
  if (typeof val === "string") {
    const clean = val.trim().toLowerCase();
    if (
      ["true", "1", "yes", "oui", "vrai", "on", "present", "présent", "confirmé"].includes(clean)
    ) {
      return true;
    }
    if (["false", "0", "no", "non", "faux", "off", "absent", "none", "aucun"].includes(clean)) {
      return false;
    }
  }
  return fallback;
}

export function coerceNullableBooleanValue(val: unknown): boolean | null {
  if (val === null || val === undefined) return null;
  if (typeof val === "boolean") return val;
  if (typeof val === "string") {
    const clean = val.trim().toLowerCase();
    if (!clean || isPlaceholderValue(clean)) return null;
    if (["true", "1", "yes", "oui", "msi", "instabilité microsatellitaire"].includes(clean)) {
      return true;
    }
    if (["false", "0", "no", "non", "mss", "microsatellite stable"].includes(clean)) {
      return false;
    }
  }
  return null;
}

export function coerceNumberValue(
  val: unknown,
  asInteger: boolean,
  min?: number,
  max?: number,
): number | null {
  if (val === null || val === undefined) return null;
  if (typeof val === "number") {
    if (!Number.isFinite(val)) return null;
    let num = asInteger ? Math.round(val) : val;
    if (min !== undefined && num < min) num = min;
    if (max !== undefined && num > max) num = max;
    return num;
  }
  if (typeof val === "string") {
    const trimmed = val.trim();
    if (!trimmed || isPlaceholderValue(trimmed)) return null;
    // Extract first numeric token (supports French comma decimal "72,5", "OMS 2", "42/66", "72 %")
    const normalized = trimmed.replace(/,/g, ".");
    const match = normalized.match(/[-+]?\d+(?:\.\d+)?/);
    if (!match) return null;
    const parsed = Number(match[0]);
    if (!Number.isFinite(parsed)) return null;
    let num = asInteger ? Math.round(parsed) : parsed;
    if (min !== undefined && num < min) num = min;
    if (max !== undefined && num > max) num = max;
    return num;
  }
  return null;
}

export function coerceDateValue(val: unknown): string | null {
  if (val === null || val === undefined) return null;
  if (val instanceof Date && !Number.isNaN(val.getTime())) {
    return val.toISOString().slice(0, 10);
  }
  if (typeof val === "string") {
    const trimmed = val.trim();
    if (!trimmed || isPlaceholderValue(trimmed)) return null;
    const isoMatch = trimmed.match(/^(\d{4})-(\d{2})-(\d{2})/);
    if (isoMatch) {
      return `${isoMatch[1]}-${isoMatch[2]}-${isoMatch[3]}`;
    }
    const frMatch = trimmed.match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
    if (frMatch) {
      return `${frMatch[3]}-${frMatch[2]}-${frMatch[1]}`;
    }
    const parsed = new Date(trimmed);
    if (!Number.isNaN(parsed.getTime())) {
      return parsed.toISOString().slice(0, 10);
    }
  }
  return null;
}

export function coerceSelectValue(
  val: unknown,
  options: FieldSelectOption[],
  fallback: string,
): string {
  if (val === null || val === undefined) return fallback;
  const raw = String(val).trim();
  if (!raw) return fallback;
  const rawLower = raw.toLowerCase();
  for (const opt of options) {
    if (
      opt.value === raw ||
      opt.value.toLowerCase() === rawLower ||
      opt.labelFr.toLowerCase() === rawLower ||
      opt.labelEn.toLowerCase() === rawLower
    ) {
      return opt.value;
    }
  }
  // Partial / alias matching for clinical enums
  if (rawLower.includes("bipap") || rawLower.includes("vni") || rawLower.includes("non-invasive")) {
    const niv = options.find((o) => o.value.includes("NIV") || o.value.includes("BiPAP"));
    if (niv) return niv.value;
  }
  if (rawLower.includes("gpe") || rawLower.includes("gastrostom") || rawLower.includes("g-tube")) {
    const gpe = options.find((o) => o.value.includes("Gastrostomy"));
    if (gpe) return gpe.value;
  }
  if (
    rawLower.includes("underweight") ||
    rawLower.includes("maigreur") ||
    rawLower.includes("cassure")
  ) {
    const uw = options.find((o) => o.value.includes("Underweight"));
    if (uw) return uw.value;
  }
  return fallback;
}

export function coerceStringListValue(val: unknown): string[] {
  if (Array.isArray(val)) {
    return val
      .map((item) => String(item ?? "").trim())
      .filter((s) => s.length > 0 && !isPlaceholderValue(s));
  }
  if (typeof val === "string") {
    const trimmed = val.trim();
    if (!trimmed || isPlaceholderValue(trimmed)) return [];
    return trimmed
      .split(/[,;\r\n]+/)
      .map((s) => s.trim())
      .filter((s) => s.length > 0 && !isPlaceholderValue(s));
  }
  return [];
}

function normalizeExamType(raw: unknown): "CT" | "MRI" | "PET" | "EUS" {
  const s = String(raw ?? "")
    .trim()
    .toUpperCase();
  if (s === "MRI" || s.includes("IRM")) return "MRI";
  if (s === "PET" || s.includes("TEP")) return "PET";
  if (s === "EUS" || s.includes("ECHO")) return "EUS";
  return "CT";
}

function normalizeChemoTolerance(raw: unknown): "Good" | "Medium" | "Poor" {
  const s = String(raw ?? "")
    .trim()
    .toLowerCase();
  if (s === "good" || s.includes("bon")) return "Good";
  if (
    s === "poor" ||
    s.includes("mauvais") ||
    s.includes("sévère") ||
    s.includes("grade 3") ||
    s.includes("grade 4")
  ) {
    return "Poor";
  }
  return "Medium";
}

export interface NormalizedExamItem {
  exam_name: string;
  exam_date: string | null;
  exam_type: "CT" | "MRI" | "PET" | "EUS";
  exam_result: string | null;
}

export interface NormalizedChemoItem {
  chemotherapy_name: string;
  chemotherapy_start_date: string | null;
  chemotherapy_end_date: string | null;
  chemotherapy_tolerance: "Good" | "Medium" | "Poor";
}

export function extractNormalizedExamsList(
  rawSectionObj: Record<string, unknown>,
): NormalizedExamItem[] {
  const rawList = Array.isArray(rawSectionObj.exams_list)
    ? rawSectionObj.exams_list
    : Array.isArray(rawSectionObj.radiological_exams)
      ? rawSectionObj.radiological_exams
      : [];
  const items: NormalizedExamItem[] = [];
  for (const item of rawList) {
    if (item && typeof item === "object") {
      const ex = item as Record<string, unknown>;
      const name = String(ex.exam_name ?? "").trim();
      if (!name && !ex.exam_result) continue;
      items.push({
        exam_name: name || "Examen d'imagerie",
        exam_date: coerceDateValue(ex.exam_date),
        exam_type: normalizeExamType(ex.exam_type),
        exam_result: isPlaceholderValue(ex.exam_result)
          ? null
          : String(ex.exam_result ?? "").trim() || null,
      });
    }
  }
  return items;
}

export function extractNormalizedChemoList(
  rawSectionObj: Record<string, unknown>,
): NormalizedChemoItem[] {
  const rawList = Array.isArray(rawSectionObj.chemotherapy_list)
    ? rawSectionObj.chemotherapy_list
    : [];
  const items: NormalizedChemoItem[] = [];
  for (const item of rawList) {
    if (item && typeof item === "object") {
      const ch = item as Record<string, unknown>;
      const name = String(ch.chemotherapy_name ?? "").trim();
      if (!name) continue;
      items.push({
        chemotherapy_name: name,
        chemotherapy_start_date: coerceDateValue(ch.chemotherapy_start_date),
        chemotherapy_end_date: coerceDateValue(ch.chemotherapy_end_date),
        chemotherapy_tolerance: normalizeChemoTolerance(ch.chemotherapy_tolerance),
      });
    }
  }
  if (items.length === 0 && typeof rawSectionObj.chemotherapy_name === "string") {
    const topName = rawSectionObj.chemotherapy_name.trim();
    if (topName && !isPlaceholderValue(topName)) {
      items.push({
        chemotherapy_name: topName,
        chemotherapy_start_date: coerceDateValue(rawSectionObj.chemotherapy_start_date),
        chemotherapy_end_date: coerceDateValue(rawSectionObj.chemotherapy_end_date),
        chemotherapy_tolerance: normalizeChemoTolerance(rawSectionObj.chemotherapy_tolerance),
      });
    }
  }
  return items;
}

/**
 * Systematically coerces an incoming section edit payload (`req.body` or API object)
 * into strict domain-compliant types matching the Python Pydantic section models.
 */
export function coerceSectionUpdatePayload(
  sectionName: string,
  rawBody: Record<string, unknown>,
  existingSectionData: Record<string, unknown> = {},
  domainSchema?: DomainFormSchema | null,
): Record<string, unknown> {
  const canonical = resolveCanonicalSectionName(sectionName);
  const schemas = getSectionFieldSchemas(sectionName, domainSchema);
  const mergedSource: Record<string, unknown> = {
    ...existingSectionData,
    ...rawBody,
  };

  if (canonical === "MTDCompleted") {
    const existingNested =
      existingSectionData.mtd_complete &&
      typeof existingSectionData.mtd_complete === "object" &&
      !Array.isArray(existingSectionData.mtd_complete)
        ? (existingSectionData.mtd_complete as Record<string, unknown>)
        : {};
    const rawMissing =
      rawBody.what_missing !== undefined
        ? rawBody.what_missing
        : (existingSectionData.what_missing ?? existingNested.what_missing ?? []);
    const whatMissing = coerceStringListValue(rawMissing);
    const rawComplete =
      rawBody.is_mtd_complete !== undefined
        ? rawBody.is_mtd_complete
        : (existingSectionData.is_mtd_complete ?? existingNested.is_mtd_complete);
    const isComplete =
      rawComplete !== undefined
        ? coerceBooleanValue(rawComplete, whatMissing.length === 0)
        : whatMissing.length === 0;
    const rawReflection =
      rawBody.reflection !== undefined
        ? rawBody.reflection
        : (existingSectionData.reflection ?? existingNested.reflection ?? null);
    const reflection = isPlaceholderValue(rawReflection)
      ? null
      : String(rawReflection ?? "").trim() || null;
    const references = Array.isArray(existingNested.references)
      ? existingNested.references
      : Array.isArray(existingSectionData.references)
        ? existingSectionData.references
        : [];

    return {
      mtd_complete: {
        is_mtd_complete: isComplete,
        what_missing: whatMissing,
        reflection,
        references,
      },
      is_mtd_complete: isComplete,
      what_missing: whatMissing,
      reflection,
    };
  }

  if (canonical === "RadiologicExams") {
    let examsList: NormalizedExamItem[] = [];
    const indexedIndices = new Set<number>();
    for (const k of Object.keys(rawBody)) {
      const m = k.match(/^exam_(?:name|type|date|result)_(\d+)$/);
      if (m?.[1]) indexedIndices.add(Number(m[1]));
    }
    if (indexedIndices.size > 0) {
      const sortedIdx = Array.from(indexedIndices).sort((a, b) => a - b);
      for (const idx of sortedIdx) {
        const name = String(rawBody[`exam_name_${idx}`] ?? "").trim();
        const resultRaw = rawBody[`exam_result_${idx}`];
        const result = isPlaceholderValue(resultRaw)
          ? null
          : String(resultRaw ?? "").trim() || null;
        if (!name && !result) continue;
        examsList.push({
          exam_name: name || "Examen d'imagerie",
          exam_date: coerceDateValue(rawBody[`exam_date_${idx}`]),
          exam_type: normalizeExamType(rawBody[`exam_type_${idx}`]),
          exam_result: result,
        });
      }
    } else if (Array.isArray(rawBody.exams_list)) {
      examsList = extractNormalizedExamsList(rawBody);
    } else {
      examsList = extractNormalizedExamsList(existingSectionData);
    }
    return { exams_list: examsList };
  }

  if (canonical === "ChemotherapyTreament") {
    let chemoList: NormalizedChemoItem[] = [];
    const indexedIndices = new Set<number>();
    for (const k of Object.keys(rawBody)) {
      const m = k.match(/^chemotherapy_(?:name|tolerance|start_date|end_date)_(\d+)$/);
      if (m?.[1]) indexedIndices.add(Number(m[1]));
    }
    if (indexedIndices.size > 0) {
      const sortedIdx = Array.from(indexedIndices).sort((a, b) => a - b);
      for (const idx of sortedIdx) {
        const name = String(rawBody[`chemotherapy_name_${idx}`] ?? "").trim();
        if (!name || isPlaceholderValue(name)) continue;
        chemoList.push({
          chemotherapy_name: name,
          chemotherapy_start_date: coerceDateValue(rawBody[`chemotherapy_start_date_${idx}`]),
          chemotherapy_end_date: coerceDateValue(rawBody[`chemotherapy_end_date_${idx}`]),
          chemotherapy_tolerance: normalizeChemoTolerance(rawBody[`chemotherapy_tolerance_${idx}`]),
        });
      }
    } else if (Array.isArray(rawBody.chemotherapy_list)) {
      chemoList = extractNormalizedChemoList(rawBody);
    } else if (typeof rawBody.chemotherapy_name === "string" && rawBody.chemotherapy_name.trim()) {
      chemoList = extractNormalizedChemoList({
        ...existingSectionData,
        ...rawBody,
        chemotherapy_list: [],
      });
    } else {
      chemoList = extractNormalizedChemoList(existingSectionData);
    }

    const hasChemo =
      rawBody.chemotherapy !== undefined
        ? coerceBooleanValue(rawBody.chemotherapy, chemoList.length > 0)
        : chemoList.length > 0 || coerceBooleanValue(existingSectionData.chemotherapy, false);

    const out: Record<string, unknown> = {
      chemotherapy: hasChemo,
      chemotherapy_list: hasChemo ? chemoList : [],
    };
    if (typeof rawBody.chemotherapy_name === "string" && rawBody.chemotherapy_name.trim()) {
      out.chemotherapy_name = rawBody.chemotherapy_name.trim();
    } else if (chemoList[0]?.chemotherapy_name) {
      out.chemotherapy_name = chemoList[0].chemotherapy_name;
    }
    if (
      typeof rawBody.chemotherapy_tolerance === "string" &&
      rawBody.chemotherapy_tolerance.trim()
    ) {
      out.chemotherapy_tolerance = rawBody.chemotherapy_tolerance.trim();
    }
    return out;
  }

  if (schemas.length === 0) {
    return mergedSource;
  }

  const out: Record<string, unknown> = {};
  const schemaKeys = new Set(schemas.map((s) => s.key));

  for (const fieldSchema of schemas) {
    const rawVal =
      rawBody[fieldSchema.key] !== undefined
        ? rawBody[fieldSchema.key]
        : existingSectionData[fieldSchema.key];

    switch (fieldSchema.inputType) {
      case "boolean": {
        out[fieldSchema.key] = coerceBooleanValue(
          rawVal,
          Boolean(fieldSchema.defaultValue ?? false),
        );
        break;
      }
      case "nullable_boolean": {
        out[fieldSchema.key] = coerceNullableBooleanValue(rawVal);
        break;
      }
      case "integer":
      case "integer_select": {
        const num = coerceNumberValue(rawVal, true, fieldSchema.min, fieldSchema.max);
        out[fieldSchema.key] =
          num !== null ? num : fieldSchema.nullable ? null : Number(fieldSchema.defaultValue ?? 0);
        break;
      }
      case "float": {
        const num = coerceNumberValue(rawVal, false, fieldSchema.min, fieldSchema.max);
        out[fieldSchema.key] =
          num !== null ? num : fieldSchema.nullable ? null : Number(fieldSchema.defaultValue ?? 0);
        break;
      }
      case "date": {
        out[fieldSchema.key] = coerceDateValue(rawVal);
        break;
      }
      case "select": {
        out[fieldSchema.key] = coerceSelectValue(
          rawVal,
          fieldSchema.options ?? [],
          String(fieldSchema.defaultValue ?? ""),
        );
        break;
      }
      case "string_list": {
        out[fieldSchema.key] = coerceStringListValue(rawVal);
        break;
      }
      default: {
        if (isPlaceholderValue(rawVal)) {
          out[fieldSchema.key] = fieldSchema.nullable
            ? null
            : String(fieldSchema.defaultValue ?? "");
        } else {
          out[fieldSchema.key] = String(rawVal ?? "").trim();
        }
        break;
      }
    }
  }

  // Domain consistency rules to prevent backend ValueError
  if (canonical === "PatientAdministrative") {
    const dob = out.date_birth as string | null;
    const dRcp = out.date_rcp as string | null;
    if (dob && dRcp && dob > dRcp) {
      out.date_birth = dRcp;
    }
  }

  // Preserve extra display keys on TumorBiology (e.g. ca19_9, kras_mutation in in-memory fake) if provided
  for (const [extraKey, extraVal] of Object.entries(rawBody)) {
    if (schemaKeys.has(extraKey)) continue;
    if (extraKey.startsWith("exam_") || extraKey.startsWith("chemotherapy_")) continue;
    if (isPlaceholderValue(extraVal)) {
      out[extraKey] = null;
    } else if (typeof extraVal === "string") {
      out[extraKey] = extraVal.trim();
    } else {
      out[extraKey] = extraVal;
    }
  }

  return out;
}

/**
 * Strips non-schema display keys so the JSON payload sent to FastAPI `model_validate`
 * contains only exact Pydantic fields for the target section.
 */
export function buildStrictBackendSectionPayload(
  sectionName: string,
  coercedPayload: Record<string, unknown>,
  domainSchema?: DomainFormSchema | null,
): Record<string, unknown> {
  const canonical = resolveCanonicalSectionName(sectionName);
  if (canonical === "MTDCompleted") {
    return {
      mtd_complete: coercedPayload.mtd_complete,
    };
  }
  if (canonical === "ChemotherapyTreament") {
    return {
      chemotherapy: Boolean(coercedPayload.chemotherapy),
      chemotherapy_list: Array.isArray(coercedPayload.chemotherapy_list)
        ? coercedPayload.chemotherapy_list
        : [],
    };
  }
  if (canonical === "RadiologicExams") {
    return {
      exams_list: Array.isArray(coercedPayload.exams_list) ? coercedPayload.exams_list : [],
    };
  }
  const schemas = getSectionFieldSchemas(sectionName, domainSchema);
  if (schemas.length === 0) return coercedPayload;
  const out: Record<string, unknown> = {};
  for (const s of schemas) {
    out[s.key] = coercedPayload[s.key] ?? (s.nullable ? null : s.defaultValue);
  }
  return out;
}
