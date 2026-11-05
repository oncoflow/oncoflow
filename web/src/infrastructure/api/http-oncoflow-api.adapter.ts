import type {
  ChatReply,
  MissingItemsUpdateInput,
  OncoflowApiPort,
  UploadFileInput,
} from "../../application/ports/oncoflow-api.port.js";
import {
  buildDefaultDomainFormSchema,
  buildStrictBackendSectionPayload,
  coerceSectionUpdatePayload,
  getAgentPresentation,
  getDomainUserPromptsForAgent,
  resolveCanonicalSectionName,
} from "../../domain/catalog.js";
import { normalizePriorityLevel } from "../../domain/triage.js";
import type {
  AgentModuleInfo,
  BatchStatus,
  BugReportItem,
  ClinicalDomain,
  DomainFormSchema,
  Language,
  MdtAgendaEnrollInput,
  MdtAgendaMoveInput,
  MdtAgendaSortStrategy,
  MdtAgendaUpdateInput,
  MdtAgendaView,
  MdtFormCard,
  MdtFormDetail,
  PatientListItem,
  QueueJobItem,
  QueueStats,
  ResourceDocument,
} from "../../domain/types.js";
import {
  formatCleanIsoDate,
  RawBugReportSchema,
  RawQueueJobSchema,
  RawQueueStatsSchema,
  RawResourceSchema,
} from "../validation/schemas.js";

export interface HttpOncoflowApiAdapterOptions {
  baseUrl: string;
  apiToken?: string;
  proxySecret?: string;
  fetchImpl?: typeof fetch;
  fallbackPort?: OncoflowApiPort;
  timeoutMs?: number;
  chatTimeoutMs?: number;
}

export class HttpOncoflowApiAdapter implements OncoflowApiPort {
  private readonly baseUrl: string;
  private readonly apiToken: string;
  private readonly proxySecret: string;
  private readonly fetchImpl: typeof fetch;
  private readonly fallback?: OncoflowApiPort;
  private readonly timeoutMs: number;
  private readonly chatTimeoutMs: number;
  private readonly domainSchemaCache = new Map<ClinicalDomain, DomainFormSchema>();

  constructor(options: HttpOncoflowApiAdapterOptions) {
    this.baseUrl = options.baseUrl.replace(/\/$/, "");
    this.apiToken = options.apiToken ?? "";
    this.proxySecret = options.proxySecret ?? "";
    this.fetchImpl = options.fetchImpl ?? fetch;
    this.fallback = options.fallbackPort;
    this.timeoutMs = options.timeoutMs ?? 30_000;
    this.chatTimeoutMs = options.chatTimeoutMs ?? Math.max(this.timeoutMs, 300_000);
  }

  private buildHeaders(
    domain: ClinicalDomain,
    extra: Record<string, string> = {},
  ): Record<string, string> {
    const headers: Record<string, string> = {
      Accept: "application/json",
      "X-Oncoflow-Domain": domain,
      ...extra,
    };
    if (this.apiToken) {
      headers.Authorization = `Bearer ${this.apiToken}`;
      headers["X-API-Key"] = this.apiToken;
      headers["X-App-Token"] = this.apiToken;
    }
    if (this.proxySecret) {
      headers["X-Oncoflow-Proxy-Secret"] = this.proxySecret;
    }
    return headers;
  }

  private async requestJson<T>(
    path: string,
    domain: ClinicalDomain,
    init: RequestInit = {},
    timeoutOverrideMs?: number,
  ): Promise<T> {
    const url = `${this.baseUrl}${path}`;
    const headers = this.buildHeaders(
      domain,
      (init.headers as Record<string, string> | undefined) ?? {},
    );
    const effectiveTimeout = timeoutOverrideMs ?? this.timeoutMs;
    const signal =
      init.signal ??
      (effectiveTimeout > 0 &&
      typeof AbortSignal !== "undefined" &&
      typeof AbortSignal.timeout === "function"
        ? AbortSignal.timeout(effectiveTimeout)
        : undefined);
    const resp = await this.fetchImpl(url, {
      ...init,
      headers,
      signal,
    });
    if (!resp.ok) {
      const httpErr = new Error(`HTTP ${resp.status} on ${path}`) as Error & {
        statusCode?: number;
      };
      httpErr.statusCode = resp.status;
      throw httpErr;
    }
    return (await resp.json()) as T;
  }

  private formatIsoDate(rawVal: unknown): string | null {
    return formatCleanIsoDate(rawVal);
  }

  private mapRawCard(raw: Record<string, unknown>, domain: ClinicalDomain): MdtFormCard {
    const file = String(raw.file ?? raw.latest_file ?? "");
    const rawFirst = raw.first_name && raw.first_name !== "Not_given" ? String(raw.first_name) : "";
    const rawLast = raw.last_name && raw.last_name !== "Not_given" ? String(raw.last_name) : "";
    const fullFromParts = `${rawLast} ${rawFirst}`.trim();
    const patientName =
      fullFromParts ||
      (raw.patient && raw.patient !== "Not_given" ? String(raw.patient) : "") ||
      file ||
      String(raw.patient_id ?? "");

    const missingItems = Array.isArray(raw.missing_items)
      ? (raw.missing_items as string[])
      : Array.isArray(raw.missing)
        ? (raw.missing as string[])
        : [];
    const missingCount =
      typeof raw.missing_count === "number" ? raw.missing_count : missingItems.length;
    const processingStatus = String(raw.processing_status ?? "COMPLETED");
    const isAiCompleted = processingStatus.trim().toUpperCase() === "COMPLETED";
    const isComplete =
      isAiCompleted &&
      (typeof raw.is_complete === "boolean" ? raw.is_complete : missingCount === 0) &&
      missingCount === 0;
    const specialties = Array.isArray(raw.specialties)
      ? (raw.specialties as string[])
      : Array.isArray(raw.experts)
        ? (raw.experts as string[])
        : [];

    return {
      id: String(raw.patient_id ?? raw.id ?? file),
      file,
      link: raw.link ? String(raw.link) : undefined,
      patientId: raw.patient_id ? String(raw.patient_id) : null,
      patientName,
      firstName: rawFirst,
      lastName: rawLast || patientName,
      dateBirth: this.formatIsoDate(raw.date_birth),
      gender: raw.gender && raw.gender !== "Not_given" ? String(raw.gender) : null,
      domain,
      mdtDate: this.formatIsoDate(raw.mdt_date ?? raw.date),
      priorityLevel: normalizePriorityLevel(raw.priority_level ?? raw.priority ?? raw.urgency),
      isComplete,
      missingCount,
      missingItems,
      careAdaptationSuggested:
        typeof raw.care_adaptation_suggested === "boolean" ? raw.care_adaptation_suggested : null,
      proposedCareType: raw.proposed_care_type ? String(raw.proposed_care_type) : null,
      specialties,
      processingStatus,
      processingStep: raw.processing_step ? String(raw.processing_step) : null,
      processingProgressPct: Number(raw.processing_progress_pct ?? 100),
      rcpCount: Number(raw.rcp_count ?? 1),
      summaryText: String(raw.summary ?? raw.tumor_location ?? raw.proposed_care_type ?? ""),
    };
  }

  private mapRawDetail(raw: Record<string, unknown>, domain: ClinicalDomain): MdtFormDetail {
    const reserved = new Set([
      "file",
      "link",
      "patient_id",
      "domain",
      "mdt_date",
      "ui_date",
      "date",
      "processing_status",
      "processing_step",
      "processing_progress_pct",
      "manual_edits",
      "manually_edited_sections",
      "execution_times",
      "metrics",
      "sections",
      "markdown_text",
      "text",
      "chunks",
      "_id",
    ]);
    const sections: Record<string, Record<string, unknown>> = {};
    if (raw.sections && typeof raw.sections === "object") {
      Object.assign(sections, raw.sections);
    } else {
      for (const [k, v] of Object.entries(raw)) {
        if (!reserved.has(k) && v && typeof v === "object" && !Array.isArray(v)) {
          sections[k] = v as Record<string, unknown>;
        }
      }
    }

    const adminSec = sections.PatientAdministrative ?? {};
    const mdtDate = this.formatIsoDate(
      raw.mdt_date ?? adminSec.date_rcp ?? raw.ui_date ?? raw.date,
    );

    const rawMetrics =
      raw.metrics && typeof raw.metrics === "object"
        ? (raw.metrics as Record<string, unknown>)
        : {};

    // Derive completeness, orientation, priority & specialties from sections when raw.metrics is absent
    const mtdComp = sections.MTDCompleted ?? {};
    const nestedComp =
      mtdComp.mtd_complete && typeof mtdComp.mtd_complete === "object"
        ? (mtdComp.mtd_complete as Record<string, unknown>)
        : mtdComp;
    const derivedMissing = Array.isArray(nestedComp.what_missing)
      ? (nestedComp.what_missing as string[])
      : [];
    const derivedIsComplete =
      typeof nestedComp.is_mtd_complete === "boolean"
        ? nestedComp.is_mtd_complete
        : derivedMissing.length === 0;

    const orientSec = sections.CareOrientationProposal ?? {};
    const derivedAdapt =
      typeof orientSec.care_adaptation_suggested === "boolean"
        ? orientSec.care_adaptation_suggested
        : typeof orientSec.intervention_required === "boolean"
          ? orientSec.intervention_required
          : null;
    const derivedProposedCare = orientSec.proposed_care_type ?? orientSec.intervention_type ?? null;

    const expertSec = sections.ExpertAnswer ?? {};
    const derivedSpecialties: string[] = [];
    let highestPriority: string | null = orientSec.suggested_priority
      ? String(orientSec.suggested_priority)
      : null;
    for (const [agentKey, val] of Object.entries(expertSec)) {
      if (!val || typeof val !== "object") continue;
      const op = val as Record<string, unknown>;
      if (op.expert_relevant !== false) {
        derivedSpecialties.push(agentKey);
      }
      const p = normalizePriorityLevel(op.patient_priority);
      if (p === "high") highestPriority = "high";
      else if (p === "medium" && highestPriority !== "high") highestPriority = "medium";
      else if (p === "low" && !highestPriority) highestPriority = "low";
    }

    const allMissingItems = Array.isArray(rawMetrics.all_missing_items)
      ? (rawMetrics.all_missing_items as string[])
      : Array.isArray(rawMetrics.missing_items)
        ? (rawMetrics.missing_items as string[])
        : Array.isArray(rawMetrics.missing)
          ? (rawMetrics.missing as string[])
          : derivedMissing;
    const hiddenMissingItems = Array.isArray(raw.hidden_missing_items)
      ? (raw.hidden_missing_items as string[])
      : Array.isArray(rawMetrics.hidden_missing_items)
        ? (rawMetrics.hidden_missing_items as string[])
        : [];
    const hideMissingItems = Boolean(
      raw.hide_missing_items ?? rawMetrics.hide_missing_items ?? false,
    );
    const hiddenSet = new Set(hiddenMissingItems);
    const missingItems = hideMissingItems
      ? []
      : Array.isArray(rawMetrics.missing_items)
        ? (rawMetrics.missing_items as string[]).filter((x) => !hiddenSet.has(x))
        : Array.isArray(rawMetrics.missing)
          ? (rawMetrics.missing as string[]).filter((x) => !hiddenSet.has(x))
          : allMissingItems.filter((x) => !hiddenSet.has(x));
    const missingCount = missingItems.length;
    const processingStatus = String(raw.processing_status ?? "COMPLETED");
    const isAiCompleted = processingStatus.trim().toUpperCase() === "COMPLETED";
    const hasMtdCompleted = Boolean(
      sections.MTDCompleted && Object.keys(sections.MTDCompleted).length > 0,
    );
    const isComplete =
      hideMissingItems || (allMissingItems.length > 0 && missingCount === 0)
        ? true
        : !isAiCompleted || !hasMtdCompleted
          ? false
          : missingCount === 0
            ? typeof rawMetrics.is_complete === "boolean"
              ? rawMetrics.is_complete
              : derivedIsComplete
            : false;
    const specialties = Array.isArray(rawMetrics.specialties)
      ? (rawMetrics.specialties as string[])
      : Array.isArray(rawMetrics.experts)
        ? (rawMetrics.experts as string[])
        : derivedSpecialties;

    const metrics: MdtFormDetail["metrics"] = {
      ...rawMetrics,
      priority_level: String(
        rawMetrics.priority_level ?? rawMetrics.urgency ?? highestPriority ?? "none",
      ),
      is_complete: isComplete,
      missing_count: missingCount,
      missing_items: missingItems,
      all_missing_items: allMissingItems,
      hidden_missing_items: hiddenMissingItems,
      hide_missing_items: hideMissingItems,
      care_adaptation_suggested:
        typeof rawMetrics.care_adaptation_suggested === "boolean"
          ? rawMetrics.care_adaptation_suggested
          : derivedAdapt,
      proposed_care_type: rawMetrics.proposed_care_type
        ? String(rawMetrics.proposed_care_type)
        : derivedProposedCare
          ? String(derivedProposedCare)
          : null,
      specialties,
    };

    const rawManualEdits =
      ((raw.manual_edits ?? raw.manually_edited_sections) as Record<
        string,
        Record<string, unknown>
      >) ?? {};
    const manualEdits: MdtFormDetail["manualEdits"] = {};
    for (const [secKey, metaVal] of Object.entries(rawManualEdits)) {
      if (metaVal && typeof metaVal === "object" && metaVal.is_manual !== false) {
        manualEdits[secKey] = metaVal as MdtFormDetail["manualEdits"][string];
      }
    }

    return {
      file: String(raw.file ?? ""),
      link: raw.link ? String(raw.link) : null,
      patientId: raw.patient_id ? String(raw.patient_id) : null,
      domain,
      mdtDate,
      processingStatus: String(raw.processing_status ?? "COMPLETED"),
      processingStep: raw.processing_step ? String(raw.processing_step) : null,
      processingProgressPct: Number(raw.processing_progress_pct ?? 100),
      sections,
      manualEdits,
      executionTimes: (raw.execution_times as Record<string, number>) ?? {},
      metrics,
      markdownText: raw.markdown_text
        ? String(raw.markdown_text)
        : raw.text
          ? String(raw.text)
          : undefined,
      chunks: Array.isArray(raw.chunks) ? (raw.chunks as MdtFormDetail["chunks"]) : undefined,
    };
  }

  async listPatientCards(domain: ClinicalDomain): Promise<MdtFormCard[]> {
    try {
      const rows = await this.requestJson<Array<Record<string, unknown>>>(
        `/api/v1/patientmdtform/patients?domain=${encodeURIComponent(domain)}`,
        domain,
      );
      return rows.map((r) => this.mapRawCard(r, domain));
    } catch (err) {
      if (this.fallback) return this.fallback.listPatientCards(domain);
      throw err;
    }
  }

  async listRcpCards(domain: ClinicalDomain): Promise<MdtFormCard[]> {
    try {
      const rows = await this.requestJson<Array<Record<string, unknown>>>(
        `/api/v1/patientmdtform?domain=${encodeURIComponent(domain)}`,
        domain,
      );
      return rows.map((r) => this.mapRawCard(r, domain));
    } catch (err) {
      if (this.fallback) return this.fallback.listRcpCards(domain);
      throw err;
    }
  }

  async listPatients(domain: ClinicalDomain, identifiedOnly = false): Promise<PatientListItem[]> {
    try {
      const rows = await this.requestJson<Array<Record<string, unknown>>>(
        `/api/v1/patientmdtform/patients?domain=${encodeURIComponent(domain)}&identified_only=${String(identifiedOnly)}`,
        domain,
      );
      return rows.map((r) => ({
        id: String(r.patient_id ?? r.id ?? ""),
        firstName: r.first_name && r.first_name !== "Not_given" ? String(r.first_name) : "",
        lastName:
          r.last_name && r.last_name !== "Not_given"
            ? String(r.last_name)
            : String(r.patient ?? r.patient_id ?? ""),
        bornName: r.born_name && r.born_name !== "Not_given" ? String(r.born_name) : null,
        dateBirth: this.formatIsoDate(r.date_birth),
        gender: r.gender && r.gender !== "Not_given" ? String(r.gender) : null,
        rcpCount: Number(r.rcp_count ?? 1),
      }));
    } catch (err) {
      if (this.fallback) return this.fallback.listPatients(domain, identifiedOnly);
      throw err;
    }
  }

  async deletePatient(patientId: string, domain: ClinicalDomain): Promise<void> {
    try {
      await this.requestJson(
        `/api/v1/patientmdtform/patients/${encodeURIComponent(patientId)}?domain=${encodeURIComponent(domain)}`,
        domain,
        { method: "DELETE" },
      );
    } catch (err) {
      if (this.fallback) return this.fallback.deletePatient(patientId, domain);
      throw err;
    }
  }

  async deleteForm(filename: string, domain: ClinicalDomain): Promise<void> {
    try {
      await this.requestJson(
        `/api/v1/patientmdtform/${encodeURIComponent(filename)}?domain=${encodeURIComponent(domain)}`,
        domain,
        { method: "DELETE" },
      );
    } catch (err) {
      if (this.fallback) return this.fallback.deleteForm(filename, domain);
      throw err;
    }
  }

  async getDomainSchema(domain: ClinicalDomain): Promise<DomainFormSchema> {
    const cached = this.domainSchemaCache.get(domain);
    if (cached) return cached;
    try {
      const res = await this.requestJson<Record<string, unknown>>(
        `/api/v1/patientmdtform/schema?domain=${encodeURIComponent(domain)}`,
        domain,
      );
      if (res && Array.isArray(res.sections)) {
        const schema: DomainFormSchema = {
          domain: String(res.domain ?? domain),
          sections: res.sections as DomainFormSchema["sections"],
          enums:
            res.enums && typeof res.enums === "object"
              ? (res.enums as Record<string, Array<string | number>>)
              : {},
        };
        this.domainSchemaCache.set(domain, schema);
        return schema;
      }
      return buildDefaultDomainFormSchema(domain);
    } catch {
      if (this.fallback) {
        return this.fallback.getDomainSchema(domain);
      }
      return buildDefaultDomainFormSchema(domain);
    }
  }

  async resolveTarget(
    target: string,
    domain: ClinicalDomain,
  ): Promise<{
    kind: "patient" | "form";
    patientId?: string | null;
    filename?: string | null;
  }> {
    try {
      const isPdf = target.toLowerCase().endsWith(".pdf");
      const query = isPdf
        ? `file=${encodeURIComponent(target)}`
        : `patient_id=${encodeURIComponent(target)}&file=${encodeURIComponent(target)}`;
      const res = await this.requestJson<Record<string, unknown>>(
        `/api/v1/patientmdtform/resolve?${query}&domain=${encodeURIComponent(domain)}`,
        domain,
      );
      const nestedPatient =
        res.patient && typeof res.patient === "object"
          ? (res.patient as Record<string, unknown>)
          : null;
      const resolvedPatientId = nestedPatient?.patient_id ?? res.patient_id ?? res.resolved_id;
      const resolvedFile = res.selected_file ?? res.latest_file ?? res.filename ?? res.resolved_id;
      if (res.resolved_type === "rcp" || res.kind === "form" || (!resolvedPatientId && isPdf)) {
        return {
          kind: "form",
          patientId: resolvedPatientId ? String(resolvedPatientId) : null,
          filename: String(resolvedFile ?? target),
        };
      }
      return {
        kind: "patient",
        patientId: String(resolvedPatientId ?? target),
        filename: resolvedFile ? String(resolvedFile) : null,
      };
    } catch (err) {
      if (this.fallback) return this.fallback.resolveTarget(target, domain);
      throw err;
    }
  }

  async getFormDetail(filename: string, domain: ClinicalDomain): Promise<MdtFormDetail | null> {
    try {
      const res = await this.requestJson<Record<string, unknown>>(
        `/api/v1/patientmdtform/${encodeURIComponent(filename)}?domain=${encodeURIComponent(domain)}`,
        domain,
      );
      return this.mapRawDetail(res, domain);
    } catch (err) {
      if (this.fallback) return this.fallback.getFormDetail(filename, domain);
      if (
        err instanceof Error &&
        (err.message.includes("HTTP 404") || err.message.includes("HTTP 400"))
      ) {
        return null;
      }
      throw err;
    }
  }

  async getPatientForms(patientId: string, domain: ClinicalDomain): Promise<MdtFormDetail[]> {
    try {
      const res = await this.requestJson<Record<string, unknown> | Array<Record<string, unknown>>>(
        `/api/v1/patientmdtform/patients/${encodeURIComponent(patientId)}?domain=${encodeURIComponent(domain)}`,
        domain,
      );
      const topPatientObj =
        !Array.isArray(res) && res.patient && typeof res.patient === "object"
          ? (res.patient as Record<string, unknown>)
          : null;
      const topPatientId = topPatientObj?.patient_id
        ? String(topPatientObj.patient_id)
        : !Array.isArray(res) && res.patient_id
          ? String(res.patient_id)
          : patientId;
      const list = Array.isArray(res)
        ? res
        : Array.isArray(res.enriched_rcps)
          ? (res.enriched_rcps as Array<Record<string, unknown>>)
          : Array.isArray(res.forms)
            ? (res.forms as Array<Record<string, unknown>>)
            : Array.isArray(res.rcps)
              ? (res.rcps as Array<Record<string, unknown>>)
              : [res];
      return list.map((item) => {
        const mapped = this.mapRawDetail(item, domain);
        if (!mapped.patientId && topPatientId) {
          mapped.patientId = topPatientId;
        }
        return mapped;
      });
    } catch (err) {
      if (this.fallback) return this.fallback.getPatientForms(patientId, domain);
      if (
        err instanceof Error &&
        (err.message.includes("HTTP 404") || err.message.includes("HTTP 400"))
      ) {
        return [];
      }
      throw err;
    }
  }

  async updateFormSection(
    filename: string,
    section: string,
    data: Record<string, unknown>,
    editedBy: string,
    domain: ClinicalDomain,
  ): Promise<MdtFormDetail> {
    try {
      const canonicalSection = resolveCanonicalSectionName(section);
      const domainSchema = await this.getDomainSchema(domain).catch(() => null);
      const coerced = coerceSectionUpdatePayload(canonicalSection, data, {}, domainSchema);
      const strictPayload = buildStrictBackendSectionPayload(
        canonicalSection,
        coerced,
        domainSchema,
      );
      await this.requestJson<Record<string, unknown>>(
        `/api/v1/patientmdtform/${encodeURIComponent(filename)}/sections/${encodeURIComponent(canonicalSection)}?domain=${encodeURIComponent(domain)}`,
        domain,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            section_data: strictPayload,
            edited_by: editedBy,
          }),
        },
      );
      const refreshed = await this.getFormDetail(filename, domain);
      if (!refreshed) {
        throw new Error(`Form ${filename} not found after section update`);
      }
      return refreshed;
    } catch (err) {
      if (this.fallback) {
        return this.fallback.updateFormSection(filename, section, data, editedBy, domain);
      }
      throw err;
    }
  }

  async rollbackSection(
    filename: string,
    section: string,
    domain: ClinicalDomain,
  ): Promise<MdtFormDetail> {
    try {
      const canonicalSection = resolveCanonicalSectionName(section);
      const res = await this.requestJson<Record<string, unknown>>(
        `/api/v1/patientmdtform/${encodeURIComponent(filename)}/sections/${encodeURIComponent(canonicalSection)}/rollback?domain=${encodeURIComponent(domain)}`,
        domain,
        {
          method: "POST",
        },
      );
      return this.mapRawDetail(res, domain);
    } catch (err) {
      if (this.fallback) {
        return this.fallback.rollbackSection(filename, section, domain);
      }
      throw err;
    }
  }

  async updateMissingItems(
    filename: string,
    input: MissingItemsUpdateInput,
    domain: ClinicalDomain,
  ): Promise<MdtFormDetail> {
    try {
      const res = await this.requestJson<Record<string, unknown>>(
        `/api/v1/patientmdtform/${encodeURIComponent(filename)}/missing-items?domain=${encodeURIComponent(domain)}`,
        domain,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            hide_missing_items: input.hideMissingItems,
            toggle_item: input.toggleItem,
            hidden_missing_items: input.hiddenMissingItems,
            what_missing: input.whatMissing,
            edited_by: input.editedBy ?? "Clinicien",
          }),
        },
      );
      return this.mapRawDetail(res, domain);
    } catch (err) {
      if (this.fallback) {
        return this.fallback.updateMissingItems(filename, input, domain);
      }
      throw err;
    }
  }

  async rerunSection(
    filename: string,
    section: string,
    preserveManualEdits: boolean,
    domain: ClinicalDomain,
  ): Promise<{ jobId: string; preserveManualEdits: boolean }> {
    const canonicalSection = resolveCanonicalSectionName(section);
    try {
      const res = await this.requestJson<Record<string, unknown>>(
        `/api/v1/queue/rerun?domain=${encodeURIComponent(domain)}`,
        domain,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            filename,
            model_name: canonicalSection,
            preserve_manual_edits: preserveManualEdits,
          }),
        },
      );
      return {
        jobId: String(res.job_id ?? res.id ?? "job"),
        preserveManualEdits,
      };
    } catch (err) {
      if (this.fallback) {
        return this.fallback.rerunSection(filename, section, preserveManualEdits, domain);
      }
      throw err;
    }
  }

  async processFullForm(
    filename: string,
    preserveManualEdits: boolean,
    domain: ClinicalDomain,
  ): Promise<{ jobId: string }> {
    try {
      const res = await this.requestJson<Record<string, unknown>>(
        `/api/v1/patientmdtform/${encodeURIComponent(filename)}/process?domain=${encodeURIComponent(domain)}`,
        domain,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            model_name: null,
            preserve_manual_edits: preserveManualEdits,
          }),
        },
      );
      const jobs = Array.isArray(res.jobs) ? (res.jobs as Array<Record<string, unknown>>) : [];
      return {
        jobId: String(jobs[0]?.job_id ?? res.job_id ?? filename),
      };
    } catch (err) {
      if (this.fallback) {
        return this.fallback.processFullForm(filename, preserveManualEdits, domain);
      }
      throw err;
    }
  }

  async linkFormToPatient(
    filename: string,
    patientId: string | null,
    domain: ClinicalDomain,
  ): Promise<void> {
    try {
      await this.requestJson(
        `/api/v1/patientmdtform/${encodeURIComponent(filename)}/link-patient?domain=${encodeURIComponent(domain)}`,
        domain,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            target_patient_id: patientId || "CREATE_NEW",
            edited_by: "Clinicien",
          }),
        },
      );
    } catch (err) {
      if (this.fallback) return this.fallback.linkFormToPatient(filename, patientId, domain);
      throw err;
    }
  }

  async getFormPdfBuffer(
    filename: string,
    domain: ClinicalDomain,
    variant: "plain" | "bbox" = "plain",
  ): Promise<Buffer | null> {
    try {
      const url = `${this.baseUrl}/api/v1/patientmdtform/${encodeURIComponent(filename)}/pdf?inline=true&variant=${variant}&domain=${encodeURIComponent(domain)}`;
      const resp = await this.fetchImpl(url, {
        headers: this.buildHeaders(domain, { Accept: "application/pdf" }),
      });
      if (!resp.ok) {
        if (this.fallback) return this.fallback.getFormPdfBuffer(filename, domain, variant);
        return null;
      }
      const arr = await resp.arrayBuffer();
      return Buffer.from(arr);
    } catch (err) {
      if (this.fallback) return this.fallback.getFormPdfBuffer(filename, domain, variant);
      throw err;
    }
  }

  async askDossierQuestion(
    target: { filename?: string; patientId?: string },
    question: string,
    domain: ClinicalDomain,
    language: Language,
    agentName?: string,
  ): Promise<ChatReply> {
    try {
      const apiLang = language === "en" ? "english" : "french";
      const trimmedAgent = agentName?.trim();
      let resolvedAgent = trimmedAgent && trimmedAgent !== "coordinator" ? trimmedAgent : "";
      if (!resolvedAgent) {
        const agents = await this.listAgents(domain, language).catch(() => []);
        resolvedAgent =
          agents.find((a) => a.name.toLowerCase().includes("expert"))?.name ??
          agents[0]?.name ??
          "Administrative";
      }

      const path = target.patientId
        ? `/api/v1/patientmdtform/patients/${encodeURIComponent(target.patientId)}/chat?domain=${encodeURIComponent(domain)}`
        : `/api/v1/patientmdtform/${encodeURIComponent(target.filename ?? "")}/chat?domain=${encodeURIComponent(domain)}`;
      const res = await this.requestJson<Record<string, unknown>>(
        path,
        domain,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            agent_name: resolvedAgent,
            message: question,
            language: apiLang,
          }),
        },
        this.chatTimeoutMs,
      );
      return {
        answer: String(res.answer ?? res.response ?? ""),
        references: Array.isArray(res.references)
          ? (res.references as ChatReply["references"])
          : [],
      };
    } catch (err) {
      if (this.fallback) {
        return this.fallback.askDossierQuestion(target, question, domain, language, agentName);
      }
      throw err;
    }
  }

  async uploadForms(
    files: UploadFileInput[],
    batchId: string,
    domain: ClinicalDomain,
  ): Promise<{ batchId: string; filenames: string[] }> {
    try {
      const filenames: string[] = [];
      for (const f of files) {
        const formData = new FormData();
        const blob = new Blob([new Uint8Array(f.content)], {
          type: "application/pdf",
        });
        formData.append("file", blob, f.filename);
        formData.append("batch_id", batchId);
        if (f.patientId) {
          formData.append("patient_id", f.patientId);
        }
        await this.requestJson(
          `/api/v1/patientmdtform/upload?domain=${encodeURIComponent(domain)}`,
          domain,
          {
            method: "POST",
            body: formData,
          },
        );
        filenames.push(f.filename);
      }
      return { batchId, filenames };
    } catch (err) {
      if (this.fallback) return this.fallback.uploadForms(files, batchId, domain);
      throw err;
    }
  }

  async getBatchStatus(batchId: string, domain: ClinicalDomain): Promise<BatchStatus> {
    try {
      const res = await this.requestJson<Record<string, unknown>>(
        `/api/v1/patientmdtform/batches/${encodeURIComponent(batchId)}?domain=${encodeURIComponent(domain)}`,
        domain,
      );
      const rawFiles = Array.isArray(res.files)
        ? (res.files as Array<Record<string, unknown>>)
        : [];
      const files = rawFiles.map((f) => ({
        filename: String(f.filename ?? ""),
        status: String(f.status ?? f.processing_status ?? "COMPLETED"),
        step: f.step ? String(f.step) : null,
        progressPct: Number(f.progress_pct ?? f.pct ?? 100),
        error: f.error ? String(f.error) : null,
        patientId: f.patient_id ? String(f.patient_id) : null,
      }));
      const countBy = (st: string) => files.filter((f) => f.status.toUpperCase() === st).length;
      return {
        batchId: String(res.batch_id ?? batchId),
        total: Number(res.total ?? files.length),
        completed: Number(res.completed ?? countBy("COMPLETED")),
        running: Number(res.running ?? countBy("RUNNING")),
        pending: Number(res.pending ?? countBy("PENDING")),
        failed: Number(res.failed ?? countBy("FAILED")),
        progressPct: Number(res.progress_pct ?? res.overall_pct ?? 100),
        files,
      };
    } catch (err) {
      if (this.fallback) return this.fallback.getBatchStatus(batchId, domain);
      throw err;
    }
  }

  async listResources(domain: ClinicalDomain): Promise<ResourceDocument[]> {
    try {
      const rows = await this.requestJson<Array<Record<string, unknown>>>(
        `/api/v1/resources?domain=${encodeURIComponent(domain)}`,
        domain,
      );
      return rows.map((rawRow) => {
        const r = RawResourceSchema.parse(rawRow);
        return {
          filename: String(r.filename ?? r.name ?? ""),
          sizeBytes: Number(r.size_bytes ?? r.size ?? 0),
          indexed: Boolean(r.is_indexed ?? r.indexed ?? false),
          chunkCount: Number(r.chunk_count ?? r.chunks ?? 0),
          updatedAt: r.updated_at ? String(r.updated_at) : null,
        };
      });
    } catch (err) {
      if (this.fallback) return this.fallback.listResources(domain);
      throw err;
    }
  }

  async uploadResource(
    filename: string,
    content: Buffer,
    domain: ClinicalDomain,
  ): Promise<ResourceDocument> {
    try {
      const formData = new FormData();
      formData.append(
        "file",
        new Blob([new Uint8Array(content)], { type: "application/pdf" }),
        filename,
      );
      await this.requestJson(
        `/api/v1/resources/upload?domain=${encodeURIComponent(domain)}`,
        domain,
        {
          method: "POST",
          body: formData,
        },
      );
      return {
        filename,
        sizeBytes: content.byteLength,
        indexed: true,
        chunkCount: 0,
        updatedAt: new Date().toISOString().slice(0, 10),
      };
    } catch (err) {
      if (this.fallback) return this.fallback.uploadResource(filename, content, domain);
      throw err;
    }
  }

  async reindexResource(filename: string, domain: ClinicalDomain): Promise<void> {
    try {
      await this.requestJson(
        `/api/v1/resources/${encodeURIComponent(filename)}/index?domain=${encodeURIComponent(domain)}`,
        domain,
        { method: "POST" },
      );
    } catch (err) {
      if (this.fallback) return this.fallback.reindexResource(filename, domain);
      throw err;
    }
  }

  async deleteResource(filename: string, domain: ClinicalDomain): Promise<void> {
    try {
      await this.requestJson(
        `/api/v1/resources/${encodeURIComponent(filename)}?domain=${encodeURIComponent(domain)}`,
        domain,
        { method: "DELETE" },
      );
    } catch (err) {
      if (this.fallback) return this.fallback.deleteResource(filename, domain);
      throw err;
    }
  }

  async getResourcePdfBuffer(
    filename: string,
    domain: ClinicalDomain,
    formFile?: string,
  ): Promise<Buffer | null> {
    try {
      const formParam = formFile ? `&form_file=${encodeURIComponent(formFile)}` : "";
      const url = `${this.baseUrl}/api/v1/resources/${encodeURIComponent(filename)}/file?domain=${encodeURIComponent(domain)}${formParam}`;
      const resp = await this.fetchImpl(url, {
        headers: this.buildHeaders(domain, { Accept: "application/pdf" }),
      });
      if (resp.ok) {
        return Buffer.from(await resp.arrayBuffer());
      }
      // If citation title did not match a resource filename directly, resolve against domain resources
      const available = await this.listResources(domain).catch(() => []);
      if (available.length > 0) {
        const lowerQuery = filename.toLowerCase();
        const best =
          available.find(
            (r) => lowerQuery.includes("pnds") && r.filename.toLowerCase().includes("pnds"),
          ) ??
          available.find(
            (r) =>
              lowerQuery.includes("argumentaire") &&
              r.filename.toLowerCase().includes("argumentaire"),
          ) ??
          available[0];
        if (best && best.filename !== filename) {
          const fallbackUrl = `${this.baseUrl}/api/v1/resources/${encodeURIComponent(best.filename)}/file?domain=${encodeURIComponent(domain)}${formParam}`;
          const fallbackResp = await this.fetchImpl(fallbackUrl, {
            headers: this.buildHeaders(domain, { Accept: "application/pdf" }),
          });
          if (fallbackResp.ok) {
            return Buffer.from(await fallbackResp.arrayBuffer());
          }
        }
      }
      if (this.fallback) return this.fallback.getResourcePdfBuffer(filename, domain, formFile);
      return null;
    } catch (err) {
      if (this.fallback) return this.fallback.getResourcePdfBuffer(filename, domain, formFile);
      throw err;
    }
  }

  async listAgents(domain: ClinicalDomain, language: Language): Promise<AgentModuleInfo[]> {
    try {
      const rows = await this.requestJson<Array<Record<string, unknown>>>(
        `/api/v1/agents?domain=${encodeURIComponent(domain)}`,
        domain,
      );
      return rows.map((r) => {
        const name = String(r.name ?? r.id ?? "");
        const pres = getAgentPresentation(name, language);
        const resourcesList = Array.isArray(r.resources)
          ? (r.resources as string[])
          : Array.isArray(r.guidelines)
            ? (r.guidelines as string[])
            : [];
        return {
          name,
          label: pres.label,
          icon: pres.icon,
          role: String(r.role ?? r.description ?? ""),
          description: String(r.description ?? r.role ?? ""),
          guidelines: resourcesList,
          models: Array.isArray(r.models) ? (r.models as string[]) : [],
          systemPrompt: r.system_prompt ? String(r.system_prompt) : undefined,
          userPrompts: getDomainUserPromptsForAgent(name, domain, language),
        };
      });
    } catch (err) {
      if (this.fallback) return this.fallback.listAgents(domain, language);
      throw err;
    }
  }

  async askGuidelineQuestion(
    question: string,
    domain: ClinicalDomain,
    language: Language,
    filename?: string,
  ): Promise<ChatReply> {
    try {
      const apiLang = language === "en" ? "english" : "french";
      let targetFilename = filename?.trim() || "";
      if (!targetFilename) {
        const resources = await this.listResources(domain);
        targetFilename = resources[0]?.filename ?? "";
      }
      if (!targetFilename) {
        return {
          answer:
            language === "fr"
              ? "Aucun référentiel PDF n'est disponible pour ce domaine."
              : "No guideline PDF is available for this domain.",
          references: [],
        };
      }
      const res = await this.requestJson<Record<string, unknown>>(
        `/api/v1/resources/${encodeURIComponent(targetFilename)}/chat?domain=${encodeURIComponent(domain)}`,
        domain,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message: question, language: apiLang }),
        },
        this.chatTimeoutMs,
      );
      return {
        answer: String(res.answer ?? res.response ?? ""),
        references: Array.isArray(res.references)
          ? (res.references as ChatReply["references"])
          : [{ name: targetFilename }],
      };
    } catch (err) {
      if (this.fallback) {
        return this.fallback.askGuidelineQuestion(question, domain, language, filename);
      }
      throw err;
    }
  }

  async listBugs(domain: ClinicalDomain): Promise<BugReportItem[]> {
    try {
      const rows = await this.requestJson<Array<Record<string, unknown>>>(
        `/api/v1/bug-reports?domain=${encodeURIComponent(domain)}`,
        domain,
      );
      return rows.map((rawRow) => {
        const r = RawBugReportSchema.parse(rawRow);
        return {
          id: String(r.bug_id ?? r.id ?? r._id ?? ""),
          title: String(r.title ?? ""),
          description: String(r.description ?? ""),
          category: String(r.category ?? "other"),
          severity: String(r.severity ?? "medium"),
          status: String(r.status ?? "open"),
          domain: String(r.domain ?? domain),
          patientOrFile: r.patient_or_file
            ? String(r.patient_or_file)
            : r.patient_id
              ? String(r.patient_id)
              : r.rcp_file
                ? String(r.rcp_file)
                : null,
          author: r.author ? String(r.author) : r.reporter ? String(r.reporter) : null,
          createdAt: this.formatIsoDate(r.created_at) ?? String(r.created_at ?? ""),
        };
      });
    } catch (err) {
      if (this.fallback) return this.fallback.listBugs(domain);
      throw err;
    }
  }

  async createBug(
    input: Omit<BugReportItem, "id" | "createdAt" | "status">,
  ): Promise<BugReportItem> {
    const domain = (input.domain === "sma" ? "sma" : "oncology") as ClinicalDomain;
    try {
      const res = await this.requestJson<Record<string, unknown>>(
        `/api/v1/bug-reports?domain=${encodeURIComponent(domain)}`,
        domain,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            title: input.title,
            description: input.description,
            category: input.category,
            severity: input.severity,
            domain: input.domain,
            patient_id: input.patientOrFile,
            rcp_file: input.patientOrFile,
            reporter: input.author,
          }),
        },
      );
      return {
        id: String(res.bug_id ?? res.id ?? res._id ?? "BUG"),
        title: input.title,
        description: input.description,
        category: input.category,
        severity: input.severity,
        status: String(res.status ?? "open"),
        domain: input.domain,
        patientOrFile: input.patientOrFile,
        author: input.author,
        createdAt: this.formatIsoDate(res.created_at) ?? new Date().toISOString().slice(0, 10),
      };
    } catch (err) {
      if (this.fallback) return this.fallback.createBug(input);
      throw err;
    }
  }

  async updateBugStatus(
    id: string,
    status: string,
    domain: ClinicalDomain,
  ): Promise<BugReportItem> {
    try {
      await this.requestJson<Record<string, unknown>>(
        `/api/v1/bug-reports/${encodeURIComponent(id)}/status?domain=${encodeURIComponent(domain)}`,
        domain,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ status }),
        },
      );
      const all = await this.listBugs(domain);
      const found = all.find((b) => b.id === id);
      return (
        found ?? {
          id,
          title: "",
          description: "",
          category: "other",
          severity: "medium",
          status,
          domain,
          patientOrFile: null,
          author: null,
          createdAt: new Date().toISOString().slice(0, 10),
        }
      );
    } catch (err) {
      if (this.fallback) return this.fallback.updateBugStatus(id, status, domain);
      throw err;
    }
  }

  async deleteBug(id: string, domain: ClinicalDomain): Promise<void> {
    try {
      await this.requestJson(
        `/api/v1/bug-reports/${encodeURIComponent(id)}?domain=${encodeURIComponent(domain)}`,
        domain,
        { method: "DELETE" },
      );
    } catch (err) {
      if (this.fallback) return this.fallback.deleteBug(id, domain);
      throw err;
    }
  }

  async getQueueStats(domain: ClinicalDomain, allDomains = true): Promise<QueueStats> {
    try {
      const rawRes = await this.requestJson<Record<string, unknown>>(
        `/api/v1/queue/stats?domain=${encodeURIComponent(domain)}&all_domains=${String(allDomains)}`,
        domain,
      );
      const res = RawQueueStatsSchema.parse(rawRes);
      const pending = res.pending;
      const running = Number(res.processing ?? res.running ?? 0);
      const completed = res.completed;
      const failed = res.failed;
      const cancelled = res.cancelled;
      const total = Number(res.total ?? pending + running + completed + failed + cancelled);

      let activeFormFile = res.active_filename ? String(res.active_filename) : null;
      let activeStep = res.active_step ? String(res.active_step) : null;
      const activeProgressPct = Number(res.active_progress_pct ?? (running > 0 ? 50 : 0));
      let thinkingPreview = res.thinking_preview ? String(res.thinking_preview) : null;

      if (running > 0 && !activeFormFile) {
        try {
          const thinking = await this.requestJson<Record<string, unknown>>(
            `/api/v1/queue/thinking?domain=${encodeURIComponent(domain)}`,
            domain,
          );
          if (thinking.is_thinking) {
            activeFormFile = thinking.filename ? String(thinking.filename) : activeFormFile;
            activeStep = thinking.step ? String(thinking.step) : activeStep;
            thinkingPreview = thinking.content ? String(thinking.content) : thinkingPreview;
          }
        } catch (_e) {
          // Non-blocking enrichment
        }
      }

      return {
        pending,
        running,
        completed,
        failed,
        cancelled,
        total,
        activeFormFile,
        activeStep,
        activeProgressPct,
        thinkingPreview,
        gpuLocksCount: Number(res.active_locks ?? res.gpu_locks_count ?? 0),
      };
    } catch (err) {
      if (this.fallback) return this.fallback.getQueueStats(domain, allDomains);
      throw err;
    }
  }

  async listQueueJobs(domain: ClinicalDomain, allDomains = true): Promise<QueueJobItem[]> {
    try {
      const rows = await this.requestJson<Array<Record<string, unknown>>>(
        `/api/v1/queue/jobs?domain=${encodeURIComponent(domain)}&all_domains=${String(allDomains)}`,
        domain,
      );
      return rows.map((rawRow) => {
        const r = RawQueueJobSchema.parse(rawRow);
        return {
          jobId: String(r.job_id ?? r.id ?? ""),
          jobType: String(r.job_type ?? "FULL_EXTRACTION"),
          status: String(r.status ?? "PENDING"),
          priority: r.priority,
          domain: String(r.domain ?? domain),
          filename: r.filename ? String(r.filename) : null,
          section: r.model_name ? String(r.model_name) : r.section ? String(r.section) : null,
          progressPct: r.progress_pct,
          step: r.current_step ? String(r.current_step) : r.step ? String(r.step) : null,
          createdAt: r.created_at ? String(r.created_at) : null,
          startedAt: r.started_at ? String(r.started_at) : null,
          completedAt: r.completed_at ? String(r.completed_at) : null,
          error: r.error_message ? String(r.error_message) : r.error ? String(r.error) : null,
          preserveManualEdits: Boolean(r.preserve_manual_edits ?? true),
        };
      });
    } catch (err) {
      if (this.fallback) return this.fallback.listQueueJobs(domain, allDomains);
      throw err;
    }
  }

  async retryQueueJob(jobId: string, domain: ClinicalDomain): Promise<void> {
    try {
      await this.requestJson(
        `/api/v1/queue/jobs/${encodeURIComponent(jobId)}/retry?domain=${encodeURIComponent(domain)}`,
        domain,
        { method: "POST" },
      );
    } catch (err) {
      if (this.fallback) return this.fallback.retryQueueJob(jobId, domain);
      throw err;
    }
  }

  async cancelOrDeleteQueueJob(jobId: string, domain: ClinicalDomain): Promise<void> {
    try {
      await this.requestJson(
        `/api/v1/queue/jobs/${encodeURIComponent(jobId)}?domain=${encodeURIComponent(domain)}`,
        domain,
        { method: "DELETE" },
      );
    } catch (err) {
      if (this.fallback) return this.fallback.cancelOrDeleteQueueJob(jobId, domain);
      throw err;
    }
  }

  async cleanQueue(mode: "completed" | "failed" | "all", domain: ClinicalDomain): Promise<number> {
    try {
      const res = await this.requestJson<Record<string, unknown>>(
        `/api/v1/queue/clean?domain=${encodeURIComponent(domain)}`,
        domain,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ mode }),
        },
      );
      return Number(res.affected_jobs ?? res.removed ?? res.cleaned ?? 0);
    } catch (err) {
      if (this.fallback) return this.fallback.cleanQueue(mode, domain);
      throw err;
    }
  }

  async releaseGpuLocks(domain: ClinicalDomain): Promise<{ released: number }> {
    try {
      const res = await this.requestJson<Record<string, unknown>>(
        `/api/v1/queue/locks?domain=${encodeURIComponent(domain)}`,
        domain,
        { method: "DELETE" },
      );
      return { released: Number(res.released_locks ?? res.released ?? 0) };
    } catch (err) {
      if (this.fallback) return this.fallback.releaseGpuLocks(domain);
      throw err;
    }
  }

  private mapRawAgenda(raw: Record<string, unknown>, domain: ClinicalDomain): MdtAgendaView {
    const rawStrategy = String(raw.sort_strategy ?? "hybrid");
    const sortStrategy: MdtAgendaSortStrategy =
      rawStrategy === "urgency_first" ||
      rawStrategy === "expert_grouping" ||
      rawStrategy === "manual"
        ? rawStrategy
        : "hybrid";

    const rawItems = Array.isArray(raw.items) ? (raw.items as Array<Record<string, unknown>>) : [];
    const items = rawItems.map((it, idx) => ({
      position: Number(it.position ?? idx + 1),
      patientId: String(it.patient_id ?? it.filename ?? ""),
      filename: String(it.filename ?? ""),
      patientName: String(it.patient_name ?? it.patient_id ?? ""),
      firstName: String(it.first_name ?? ""),
      lastName: String(it.last_name ?? ""),
      dateBirth: this.formatIsoDate(it.date_birth),
      urgency: String(it.urgency ?? ""),
      urgencyScore: Number(it.urgency_score ?? 0),
      priorityLevel: normalizePriorityLevel(it.priority_level ?? it.urgency),
      isComplete: Boolean(it.is_complete ?? true),
      missingCount: Number(it.missing_count ?? 0),
      missingItems: Array.isArray(it.missing_items)
        ? (it.missing_items as string[]).map(String)
        : [],
      careAdaptationSuggested:
        typeof it.care_adaptation_suggested === "boolean" ? it.care_adaptation_suggested : null,
      proposedCareType: it.proposed_care_type ? String(it.proposed_care_type) : null,
      requiredExperts: Array.isArray(it.required_experts)
        ? (it.required_experts as string[]).map(String)
        : [],
      presentRequiredExperts: Array.isArray(it.present_required_experts)
        ? (it.present_required_experts as string[]).map(String)
        : [],
      absentRequiredExperts: Array.isArray(it.absent_required_experts)
        ? (it.absent_required_experts as string[]).map(String)
        : [],
      quorumMet: Boolean(it.quorum_met ?? true),
      expertCoverageRatio: Number(it.expert_coverage_ratio ?? 1),
      clusterKey: String(it.cluster_key ?? "general"),
      pinned: Boolean(it.pinned ?? false),
      rankReason: String(it.rank_reason ?? ""),
      mdtDate: this.formatIsoDate(it.mdt_date),
    }));

    const rawWindows = Array.isArray(raw.expert_windows)
      ? (raw.expert_windows as Array<Record<string, unknown>>)
      : [];
    const expertWindows = rawWindows.map((w) => ({
      expertName: String(w.expert_name ?? ""),
      isAttending: Boolean(w.is_attending ?? true),
      caseCount: Number(w.case_count ?? 0),
      urgentCaseCount: Number(w.urgent_case_count ?? 0),
      firstPosition:
        w.first_position !== null && w.first_position !== undefined
          ? Number(w.first_position)
          : null,
      lastPosition:
        w.last_position !== null && w.last_position !== undefined ? Number(w.last_position) : null,
      isContiguous: Boolean(w.is_contiguous ?? true),
      patientIds: Array.isArray(w.patient_ids) ? (w.patient_ids as string[]).map(String) : [],
    }));

    const rawCandidates = Array.isArray(raw.candidates)
      ? (raw.candidates as Array<Record<string, unknown>>)
      : [];
    const candidates = rawCandidates.map((c) => ({
      patientId: String(c.patient_id ?? c.filename ?? ""),
      filename: String(c.filename ?? ""),
      patientName: String(c.patient_name ?? c.patient_id ?? ""),
      firstName: String(c.first_name ?? ""),
      lastName: String(c.last_name ?? ""),
      dateBirth: this.formatIsoDate(c.date_birth),
      urgency: String(c.urgency ?? ""),
      urgencyScore: Number(c.urgency_score ?? 0),
      priorityLevel: normalizePriorityLevel(c.priority_level ?? c.urgency),
      isComplete: Boolean(c.is_complete ?? true),
      missingCount: Number(c.missing_count ?? 0),
      missingItems: Array.isArray(c.missing_items) ? (c.missing_items as string[]).map(String) : [],
      careAdaptationSuggested:
        typeof c.care_adaptation_suggested === "boolean" ? c.care_adaptation_suggested : null,
      proposedCareType: c.proposed_care_type ? String(c.proposed_care_type) : null,
      requiredExperts: Array.isArray(c.required_experts)
        ? (c.required_experts as string[]).map(String)
        : [],
      mdtDate: this.formatIsoDate(c.mdt_date),
    }));

    return {
      agendaId: String(raw.agenda_id ?? `next_mdt_${domain}`),
      domain: (raw.domain === "sma" ? "sma" : domain) as ClinicalDomain,
      sessionDate: String(raw.session_date ?? new Date().toISOString().slice(0, 10)),
      sortStrategy,
      deferIncompleteFiles: Boolean(raw.defer_incomplete_files ?? false),
      availableExperts: Array.isArray(raw.available_experts)
        ? (raw.available_experts as string[]).map(String)
        : [],
      attendingExperts: Array.isArray(raw.attending_experts)
        ? (raw.attending_experts as string[]).map(String)
        : [],
      totalEnrolled: Number(raw.total_enrolled ?? items.length),
      urgentCount: Number(raw.urgent_count ?? 0),
      incompleteCount: Number(raw.incomplete_count ?? 0),
      quorumWarningCount: Number(raw.quorum_warning_count ?? 0),
      items,
      expertWindows,
      candidates,
      updatedAt: raw.updated_at ? String(raw.updated_at) : null,
    };
  }

  async getMdtAgenda(domain: ClinicalDomain): Promise<MdtAgendaView> {
    try {
      const res = await this.requestJson<Record<string, unknown>>(
        `/api/v1/mdt-agenda?domain=${encodeURIComponent(domain)}`,
        domain,
      );
      return this.mapRawAgenda(res, domain);
    } catch (err) {
      if (this.fallback) return this.fallback.getMdtAgenda(domain);
      throw err;
    }
  }

  async updateMdtAgenda(
    input: MdtAgendaUpdateInput,
    domain: ClinicalDomain,
  ): Promise<MdtAgendaView> {
    try {
      const payload: Record<string, unknown> = {};
      if (input.sessionDate !== undefined) payload.session_date = input.sessionDate;
      if (input.sortStrategy !== undefined) payload.sort_strategy = input.sortStrategy;
      if (input.deferIncompleteFiles !== undefined) {
        payload.defer_incomplete_files = input.deferIncompleteFiles;
      }
      if (input.attendingExperts !== undefined) {
        payload.attending_experts = input.attendingExperts;
      }
      if (input.toggleExpert !== undefined) payload.toggle_expert = input.toggleExpert;
      if (input.patientIds !== undefined) payload.patient_ids = input.patientIds;
      if (input.resetEnrolledPatients !== undefined) {
        payload.reset_enrolled_patients = input.resetEnrolledPatients;
      }

      const res = await this.requestJson<Record<string, unknown>>(
        `/api/v1/mdt-agenda?domain=${encodeURIComponent(domain)}`,
        domain,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        },
      );
      return this.mapRawAgenda(res, domain);
    } catch (err) {
      if (this.fallback) return this.fallback.updateMdtAgenda(input, domain);
      throw err;
    }
  }

  async addPatientsToMdtAgenda(
    input: MdtAgendaEnrollInput,
    domain: ClinicalDomain,
  ): Promise<MdtAgendaView> {
    try {
      const res = await this.requestJson<Record<string, unknown>>(
        `/api/v1/mdt-agenda/patients?domain=${encodeURIComponent(domain)}`,
        domain,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            patient_ids: input.patientIds,
            patient_id: input.patientId,
            enroll_all_candidates: input.enrollAllCandidates ?? false,
            filter_mode: input.filterMode ?? "all",
          }),
        },
      );
      return this.mapRawAgenda(res, domain);
    } catch (err) {
      if (this.fallback) return this.fallback.addPatientsToMdtAgenda(input, domain);
      throw err;
    }
  }

  async removePatientFromMdtAgenda(
    patientId: string,
    domain: ClinicalDomain,
  ): Promise<MdtAgendaView> {
    try {
      const res = await this.requestJson<Record<string, unknown>>(
        `/api/v1/mdt-agenda/patients/${encodeURIComponent(patientId)}?domain=${encodeURIComponent(domain)}`,
        domain,
        { method: "DELETE" },
      );
      return this.mapRawAgenda(res, domain);
    } catch (err) {
      if (this.fallback) return this.fallback.removePatientFromMdtAgenda(patientId, domain);
      throw err;
    }
  }

  async clearMdtAgenda(domain: ClinicalDomain): Promise<MdtAgendaView> {
    try {
      const res = await this.requestJson<Record<string, unknown>>(
        `/api/v1/mdt-agenda/patients?domain=${encodeURIComponent(domain)}`,
        domain,
        { method: "DELETE" },
      );
      return this.mapRawAgenda(res, domain);
    } catch (err) {
      if (this.fallback) return this.fallback.clearMdtAgenda(domain);
      throw err;
    }
  }

  async movePatientInMdtAgenda(
    patientId: string,
    input: MdtAgendaMoveInput,
    domain: ClinicalDomain,
  ): Promise<MdtAgendaView> {
    try {
      const res = await this.requestJson<Record<string, unknown>>(
        `/api/v1/mdt-agenda/patients/${encodeURIComponent(patientId)}/move?domain=${encodeURIComponent(domain)}`,
        domain,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            direction: input.direction,
            target_position: input.targetPosition,
            pinned: input.pinned,
          }),
        },
      );
      return this.mapRawAgenda(res, domain);
    } catch (err) {
      if (this.fallback) return this.fallback.movePatientInMdtAgenda(patientId, input, domain);
      throw err;
    }
  }
}
