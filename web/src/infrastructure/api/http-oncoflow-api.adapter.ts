import type {
  ChatReply,
  OncoflowApiPort,
  UploadFileInput,
} from "../../application/ports/oncoflow-api.port.js";
import { getAgentPresentation, getDomainUserPromptsForAgent } from "../../domain/catalog.js";
import { normalizePriorityLevel } from "../../domain/triage.js";
import type {
  AgentModuleInfo,
  BatchStatus,
  BugReportItem,
  ClinicalDomain,
  Language,
  MdtFormCard,
  MdtFormDetail,
  PatientListItem,
  QueueJobItem,
  QueueStats,
  ResourceDocument,
} from "../../domain/types.js";

export interface HttpOncoflowApiAdapterOptions {
  baseUrl: string;
  apiToken?: string;
  proxySecret?: string;
  fetchImpl?: typeof fetch;
  fallbackPort?: OncoflowApiPort;
}

export class HttpOncoflowApiAdapter implements OncoflowApiPort {
  private readonly baseUrl: string;
  private readonly apiToken: string;
  private readonly proxySecret: string;
  private readonly fetchImpl: typeof fetch;
  private readonly fallback?: OncoflowApiPort;

  constructor(options: HttpOncoflowApiAdapterOptions) {
    this.baseUrl = options.baseUrl.replace(/\/$/, "");
    this.apiToken = options.apiToken ?? "";
    this.proxySecret = options.proxySecret ?? "";
    this.fetchImpl = options.fetchImpl ?? fetch;
    this.fallback = options.fallbackPort;
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
  ): Promise<T> {
    const url = `${this.baseUrl}${path}`;
    const headers = this.buildHeaders(
      domain,
      (init.headers as Record<string, string> | undefined) ?? {},
    );
    const resp = await this.fetchImpl(url, {
      ...init,
      headers,
    });
    if (!resp.ok) {
      throw new Error(`HTTP ${resp.status} on ${path}`);
    }
    return (await resp.json()) as T;
  }

  private formatIsoDate(rawVal: unknown): string | null {
    if (!rawVal) return null;
    const str = String(rawVal).trim();
    if (
      !str ||
      str === "Not_given" ||
      str === "not_given" ||
      str === "Non spécifié" ||
      str === "None" ||
      str === "null"
    ) {
      return null;
    }
    if (str.includes("T") && str.length >= 10) {
      return str.slice(0, 10);
    }
    return str;
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
    const isComplete = typeof raw.is_complete === "boolean" ? raw.is_complete : missingCount === 0;
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
      processingStatus: String(raw.processing_status ?? "COMPLETED"),
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

    const missingItems = Array.isArray(rawMetrics.missing_items)
      ? (rawMetrics.missing_items as string[])
      : Array.isArray(rawMetrics.missing)
        ? (rawMetrics.missing as string[])
        : derivedMissing;
    const missingCount =
      typeof rawMetrics.missing_count === "number" ? rawMetrics.missing_count : missingItems.length;
    const isComplete =
      typeof rawMetrics.is_complete === "boolean" ? rawMetrics.is_complete : derivedIsComplete;
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

    const manualEdits =
      ((raw.manual_edits ?? raw.manually_edited_sections) as MdtFormDetail["manualEdits"]) ?? {};

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

  async resolveTarget(
    target: string,
    domain: ClinicalDomain,
  ): Promise<{ kind: "patient" | "form"; patientId?: string | null; filename?: string | null }> {
    try {
      const isPdf = target.toLowerCase().endsWith(".pdf");
      const query = isPdf
        ? `file=${encodeURIComponent(target)}`
        : `patient_id=${encodeURIComponent(target)}&file=${encodeURIComponent(target)}`;
      const res = await this.requestJson<Record<string, unknown>>(
        `/api/v1/patientmdtform/resolve?${query}&domain=${encodeURIComponent(domain)}`,
        domain,
      );
      if (res.resolved_type === "rcp" || res.kind === "form") {
        return {
          kind: "form",
          patientId: res.patient_id ? String(res.patient_id) : null,
          filename: String(res.filename ?? res.latest_file ?? res.resolved_id ?? target),
        };
      }
      return {
        kind: "patient",
        patientId: String(res.patient_id ?? res.resolved_id ?? target),
        filename: res.latest_file
          ? String(res.latest_file)
          : res.filename
            ? String(res.filename)
            : null,
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
      throw err;
    }
  }

  async getPatientForms(patientId: string, domain: ClinicalDomain): Promise<MdtFormDetail[]> {
    try {
      const res = await this.requestJson<Record<string, unknown> | Array<Record<string, unknown>>>(
        `/api/v1/patientmdtform/patients/${encodeURIComponent(patientId)}?domain=${encodeURIComponent(domain)}`,
        domain,
      );
      const list = Array.isArray(res)
        ? res
        : Array.isArray(res.enriched_rcps)
          ? (res.enriched_rcps as Array<Record<string, unknown>>)
          : Array.isArray(res.forms)
            ? (res.forms as Array<Record<string, unknown>>)
            : Array.isArray(res.rcps)
              ? (res.rcps as Array<Record<string, unknown>>)
              : [res];
      return list.map((item) => this.mapRawDetail(item, domain));
    } catch (err) {
      if (this.fallback) return this.fallback.getPatientForms(patientId, domain);
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
      await this.requestJson<Record<string, unknown>>(
        `/api/v1/patientmdtform/${encodeURIComponent(filename)}/sections/${encodeURIComponent(section)}?domain=${encodeURIComponent(domain)}`,
        domain,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            section_data: data,
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

  async rerunSection(
    filename: string,
    section: string,
    preserveManualEdits: boolean,
    domain: ClinicalDomain,
  ): Promise<{ jobId: string; preserveManualEdits: boolean }> {
    try {
      const res = await this.requestJson<Record<string, unknown>>(
        `/api/v1/queue/rerun?domain=${encodeURIComponent(domain)}`,
        domain,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            filename,
            model_name: section,
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
        `/api/v1/patientmdtform/process?domain=${encodeURIComponent(domain)}`,
        domain,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify([filename]),
        },
      );
      return { jobId: String(res.job_id ?? filename) };
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
      const defaultAgent = domain === "sma" ? "neurologist expert" : "pancreas expert";
      const trimmedAgent = agentName?.trim();
      const resolvedAgent =
        trimmedAgent && trimmedAgent !== "coordinator" ? trimmedAgent : defaultAgent;

      const path = target.patientId
        ? `/api/v1/patientmdtform/patients/${encodeURIComponent(target.patientId)}/chat?domain=${encodeURIComponent(domain)}`
        : `/api/v1/patientmdtform/${encodeURIComponent(target.filename ?? "")}/chat?domain=${encodeURIComponent(domain)}`;
      const res = await this.requestJson<Record<string, unknown>>(path, domain, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          agent_name: resolvedAgent,
          message: question,
          language: apiLang,
        }),
      });
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
        const blob = new Blob([new Uint8Array(f.content)], { type: "application/pdf" });
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
      return {
        batchId: String(res.batch_id ?? batchId),
        total: Number(res.total ?? rawFiles.length),
        completed: Number(res.completed ?? 0),
        running: Number(res.running ?? 0),
        pending: Number(res.pending ?? 0),
        failed: Number(res.failed ?? 0),
        progressPct: Number(res.progress_pct ?? 100),
        files: rawFiles.map((f) => ({
          filename: String(f.filename ?? ""),
          status: String(f.status ?? "COMPLETED"),
          step: f.step ? String(f.step) : null,
          progressPct: Number(f.progress_pct ?? 100),
          error: f.error ? String(f.error) : null,
          patientId: f.patient_id ? String(f.patient_id) : null,
        })),
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
      return rows.map((r) => ({
        filename: String(r.filename ?? r.name ?? ""),
        sizeBytes: Number(r.size_bytes ?? r.size ?? 0),
        indexed: Boolean(r.is_indexed ?? r.indexed ?? false),
        chunkCount: Number(r.chunk_count ?? r.chunks ?? 0),
        updatedAt: r.updated_at ? String(r.updated_at) : null,
      }));
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

  async getResourcePdfBuffer(filename: string, domain: ClinicalDomain): Promise<Buffer | null> {
    try {
      const url = `${this.baseUrl}/api/v1/resources/${encodeURIComponent(filename)}/file?domain=${encodeURIComponent(domain)}`;
      const resp = await this.fetchImpl(url, {
        headers: this.buildHeaders(domain, { Accept: "application/pdf" }),
      });
      if (!resp.ok) {
        if (this.fallback) return this.fallback.getResourcePdfBuffer(filename, domain);
        return null;
      }
      return Buffer.from(await resp.arrayBuffer());
    } catch (err) {
      if (this.fallback) return this.fallback.getResourcePdfBuffer(filename, domain);
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
      return rows.map((r) => ({
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
      }));
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
      const res = await this.requestJson<Record<string, unknown>>(
        `/api/v1/queue/stats?domain=${encodeURIComponent(domain)}&all_domains=${String(allDomains)}`,
        domain,
      );
      const pending = Number(res.pending ?? 0);
      const running = Number(res.processing ?? res.running ?? 0);
      const completed = Number(res.completed ?? 0);
      const failed = Number(res.failed ?? 0);
      const cancelled = Number(res.cancelled ?? 0);
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
      return rows.map((r) => ({
        jobId: String(r.job_id ?? r.id ?? ""),
        jobType: String(r.job_type ?? "FULL_EXTRACTION"),
        status: String(r.status ?? "PENDING"),
        priority: Number(r.priority ?? 2),
        domain: String(r.domain ?? domain),
        filename: r.filename ? String(r.filename) : null,
        section: r.model_name ? String(r.model_name) : r.section ? String(r.section) : null,
        progressPct: Number(r.progress_pct ?? 0),
        step: r.current_step ? String(r.current_step) : r.step ? String(r.step) : null,
        createdAt: r.created_at ? String(r.created_at) : null,
        startedAt: r.started_at ? String(r.started_at) : null,
        completedAt: r.completed_at ? String(r.completed_at) : null,
        error: r.error_message ? String(r.error_message) : r.error ? String(r.error) : null,
        preserveManualEdits: Boolean(r.preserve_manual_edits ?? true),
      }));
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
}
