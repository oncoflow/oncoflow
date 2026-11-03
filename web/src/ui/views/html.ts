import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ICONS_SVG_PATH = path.resolve(__dirname, "../../../public/img/icons.svg");
export const INLINE_ICONS_SVG = fs.existsSync(ICONS_SVG_PATH)
  ? fs.readFileSync(ICONS_SVG_PATH, "utf8")
  : "";

const ISO_MIDNIGHT_RE = /(\d{4})-(\d{2})-(\d{2})T00:00:00(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?/g;

/**
 * Pure HTML escaping without date formatting side-effects.
 */
export function escapeHtml(val: unknown): string {
  if (val === null || val === undefined) return "";
  return String(val)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

/**
 * Escapes HTML and normalizes ISO midnight timestamps (`YYYY-MM-DDT00:00:00...` -> `DD/MM/YYYY`).
 * Fast-path skips the regex unless `T00:00:00` is present in the string.
 */
export function esc(val: unknown): string {
  if (val === null || val === undefined) return "";
  const str = String(val);
  const normalized = str.includes("T00:00:00") ? str.replace(ISO_MIDNIGHT_RE, "$3/$2/$1") : str;
  return normalized
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

/**
 * Marker class for pre-sanitized / trusted HTML fragments inside `html` tagged templates.
 */
export class SafeHtml {
  constructor(public readonly value: string) {}
  toString(): string {
    return this.value;
  }
}

/**
 * Marks a string as trusted HTML so the `html` tagged template does not double-escape it.
 */
export function raw(trustedHtml: string | SafeHtml | null | undefined): SafeHtml {
  if (!trustedHtml) return new SafeHtml("");
  if (trustedHtml instanceof SafeHtml) return trustedHtml;
  return new SafeHtml(trustedHtml);
}

function renderInterpolatedValue(val: unknown): string {
  if (val === null || val === undefined || val === false) return "";
  if (val instanceof SafeHtml) return val.value;
  if (Array.isArray(val)) {
    return val.map(renderInterpolatedValue).join("");
  }
  return esc(val);
}

/**
 * Auto-escaping tagged template literal for XSS-safe SSR HTML generation.
 * All interpolated values are automatically escaped via `esc()` unless wrapped in `raw()`.
 */
export function html(strings: TemplateStringsArray, ...values: unknown[]): string {
  let out = "";
  for (let i = 0; i < strings.length; i++) {
    out += strings[i];
    if (i < values.length) {
      out += renderInterpolatedValue(values[i]);
    }
  }
  return out;
}

/**
 * Formats a duration in seconds as "X min YY s" (e.g., "0 min 12 s", "1 min 08 s").
 */
export function formatDurationMinSec(seconds: number): string {
  const totalSec = Math.max(0, Math.round(Number(seconds) || 0));
  const mins = Math.floor(totalSec / 60);
  const secs = totalSec % 60;
  return `${mins} min ${String(secs).padStart(2, "0")} s`;
}

export function iconSvg(id: string, sizeClass = ""): string {
  const cls = sizeClass ? `ds-icon ${sizeClass}` : "ds-icon";
  return `<svg class="${cls}" aria-hidden="true"><use href="#${escapeHtml(id)}"/></svg>`;
}

export function deriveRcpTone(
  priorityLevel: string | undefined,
  isComplete = true,
): "red" | "orange" | "green" {
  const norm = (priorityLevel ?? "").toLowerCase();
  if (norm === "high" || (norm.includes("urgent") && !norm.includes("semi"))) {
    return "red";
  }
  if (norm === "medium" || norm.includes("semi") || norm.includes("mod") || !isComplete) {
    return "orange";
  }
  return "green";
}

export function extractDobFromPatientId(id: string | null | undefined): string | null {
  if (!id) return null;
  const m = id.match(/(?:_|-)(\d{4})[_-](\d{2})[_-](\d{2})$/);
  if (!m) return null;
  return `${m[3]}/${m[2]}/${m[1]}`;
}

export function formatPatientSubtitle(id: string, rcpCount: number): string {
  const rcpLabel = `${rcpCount} ${rcpCount > 1 ? "séances RCP" : "séance RCP"}`;
  const dob = extractDobFromPatientId(id);
  if (dob) {
    return `Né(e) le ${dob} · ${rcpLabel}`;
  }
  if (id && !id.includes("_") && !id.toLowerCase().endsWith(".pdf")) {
    return `Dossier ${id} · ${rcpLabel}`;
  }
  return rcpLabel;
}

export function stripDomainQuery(input: string): string {
  return input
    .replace(/<input type="hidden" name="domain" value="(?:oncology|sma)">\s*/g, "")
    .replace(/ data-domain="(?:oncology|sma)"/g, "")
    .replace(/\?domain=(?:oncology|sma)&/g, "?")
    .replace(/&domain=(?:oncology|sma)(?=[&#"'\s]|$)/g, "")
    .replace(/\?domain=(?:oncology|sma)(?=[#"'\s]|$)/g, "");
}
