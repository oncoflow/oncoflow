import {
  type SectionPresentationMeta,
  formatFieldLabel,
  getAgentPresentation,
  getSectionPresentation,
} from "../../domain/catalog.js";
import { translateValue } from "../../domain/i18n.js";
import {
  computeLongitudinalDeltas,
  deriveCompletenessInfo,
  deriveOrientationInfo,
  derivePriorityBadgeInfo,
  normalizePriorityLevel,
  priorityRank,
} from "../../domain/triage.js";
import type {
  AgentModuleInfo,
  CitationRef,
  ClinicalDomain,
  ExpertSuggestion,
  Language,
  LongitudinalDelta,
  ManualEditMetadata,
  MdtFormDetail,
  PatientListItem,
  PriorityLevel,
  SpecialtyOpinionItem,
} from "../../domain/types.js";
import type { ChatReply, OncoflowApiPort } from "../ports/oncoflow-api.port.js";

export interface DossierSubCardView {
  title: string;
  badge?: string | null;
  subtitle?: string | null;
  body: string;
}

export interface DossierManualDiffView {
  key: string;
  label: string;
  aiValue: string;
  humanValue: string;
}

export interface DossierFieldView {
  key: string;
  label: string;
  value: string;
  rawValue: unknown;
  isLongText: boolean;
  hiddenInReadView?: boolean;
}

export interface DossierSectionView {
  name: string;
  meta: SectionPresentationMeta;
  summaryText: string;
  fields: DossierFieldView[];
  subCards: DossierSubCardView[];
  references: CitationRef[];
  rawData: Record<string, unknown>;
  isManual: boolean;
  manualMeta: ManualEditMetadata | null;
  manualDiffs: DossierManualDiffView[];
  reasoningThinking: string | null;
  userPrompt: string | null;
  durationSec: number | null;
}

export interface TimelineSessionItem {
  file: string;
  mdtDate: string;
  isCurrent: boolean;
  isLatest: boolean;
  priorityLevel: PriorityLevel;
  priorityLabel: string;
  orientationLabel: string;
}

export interface PatientDossierView {
  patientId: string | null;
  patientName: string;
  firstName: string;
  lastName: string;
  dateBirth: string | null;
  gender: string | null;
  domain: ClinicalDomain;
  rcpCount: number;
  cumulativeDurationSec: number;
  currentForm: MdtFormDetail;
  timeline: TimelineSessionItem[];
  prevSessionFile: string | null;
  nextSessionFile: string | null;
  priorityBadge: ReturnType<typeof derivePriorityBadgeInfo>;
  completenessBadge: ReturnType<typeof deriveCompletenessInfo>;
  orientationBadge: ReturnType<typeof deriveOrientationInfo>;
  specialties: Array<{ name: string; label: string; icon: string }>;
  synopticMarkers: Array<{
    key: string;
    label: string;
    value: string;
    isMissing: boolean;
    delta?: LongitudinalDelta;
  }>;
  deltas: LongitudinalDelta[];
  sections: DossierSectionView[];
  opinions: SpecialtyOpinionItem[];
  careProposal: {
    careAdaptationSuggested: boolean | null;
    proposedCareType: string | null;
    clinicalRationale: string | null;
    reasoningThinking: string | null;
    userPrompt: string | null;
    durationSec: number | null;
  };
  allPatients: PatientListItem[];
  agents: AgentModuleInfo[];
}

const LONG_TEXT_KEYS = new Set([
  "reflection",
  "clinical_rationale",
  "why",
  "why_relevant",
  "exam_result",
  "other_genetic_variants",
  "motor_milestones",
]);

export class PatientDossierUseCase {
  constructor(private readonly api: OncoflowApiPort) {}

  async getDossier(
    target: string,
    domain: ClinicalDomain,
    lang: Language = "fr",
    selectedFile?: string,
  ): Promise<PatientDossierView | null> {
    let forms = await this.api.getPatientForms(target, domain);
    if (forms.length === 0) {
      const single = await this.api.getFormDetail(target, domain);
      if (!single) return null;
      if (single.patientId) {
        const linked = await this.api.getPatientForms(single.patientId, domain);
        forms = linked.length > 0 ? linked : [single];
      } else {
        forms = [single];
      }
    }

    const sorted = [...forms].sort((a, b) => (a.mdtDate ?? "").localeCompare(b.mdtDate ?? ""));
    const currentIndex = selectedFile
      ? Math.max(
          0,
          sorted.findIndex((f) => f.file === selectedFile),
        )
      : sorted.length - 1;
    const currentForm = sorted[currentIndex] ?? sorted[sorted.length - 1]!;
    const previousForm = currentIndex > 0 ? sorted[currentIndex - 1] : null;

    const admin = (currentForm.sections.PatientAdministrative ?? {}) as Record<string, unknown>;
    const firstName =
      admin.first_name && admin.first_name !== "Not_given" ? String(admin.first_name) : "";
    const lastName =
      admin.last_name && admin.last_name !== "Not_given"
        ? String(admin.last_name)
        : currentForm.file;
    const patientName = `${lastName} ${firstName}`.trim();

    const priorityLevel = normalizePriorityLevel(currentForm.metrics.priority_level);
    const priorityBadge = derivePriorityBadgeInfo(priorityLevel, lang);

    const mtdCompletedRaw = (currentForm.sections.MTDCompleted ?? {}) as Record<string, unknown>;
    const mtdNested =
      mtdCompletedRaw.mtd_complete && typeof mtdCompletedRaw.mtd_complete === "object"
        ? (mtdCompletedRaw.mtd_complete as Record<string, unknown>)
        : mtdCompletedRaw;
    const missingItems = Array.isArray(currentForm.metrics.missing_items)
      ? (currentForm.metrics.missing_items as string[])
      : Array.isArray(mtdNested.what_missing)
        ? (mtdNested.what_missing as string[])
        : Array.isArray(mtdCompletedRaw.what_missing)
          ? (mtdCompletedRaw.what_missing as string[])
          : [];
    const completenessBadge = deriveCompletenessInfo(
      {
        is_complete:
          typeof currentForm.metrics.is_complete === "boolean"
            ? currentForm.metrics.is_complete
            : mtdNested.is_mtd_complete !== false && missingItems.length === 0,
        missing_count: missingItems.length,
        missing_items: missingItems,
      },
      lang,
    );

    const careSec = (currentForm.sections.CareOrientationProposal ?? {}) as Record<string, unknown>;
    const careAdaptationSuggested =
      typeof currentForm.metrics.care_adaptation_suggested === "boolean"
        ? currentForm.metrics.care_adaptation_suggested
        : typeof careSec.care_adaptation_suggested === "boolean"
          ? careSec.care_adaptation_suggested
          : null;
    const proposedCareType =
      String(currentForm.metrics.proposed_care_type ?? careSec.proposed_care_type ?? "").trim() ||
      null;

    const orientationBadge = deriveOrientationInfo(
      {
        care_adaptation_suggested: careAdaptationSuggested,
        proposed_care_type: proposedCareType,
      },
      lang,
    );

    const rawSpecs = Array.isArray(currentForm.metrics.specialties)
      ? (currentForm.metrics.specialties as string[])
      : [];
    const specialties = rawSpecs.map((s) => getAgentPresentation(s, lang));

    const deltas = computeLongitudinalDeltas(currentForm, previousForm, lang);
    const synopticMarkers = this.buildSynopticMarkers(currentForm, deltas, lang);
    const sections = this.buildSections(currentForm, lang);
    const opinions = this.buildOpinions(currentForm, lang);

    const timeline: TimelineSessionItem[] = sorted.map((f, idx) => {
      const fPrio = normalizePriorityLevel(f.metrics.priority_level);
      const fPrioInfo = derivePriorityBadgeInfo(fPrio, lang, true);
      const fOrient = deriveOrientationInfo(
        {
          care_adaptation_suggested:
            typeof f.metrics.care_adaptation_suggested === "boolean"
              ? f.metrics.care_adaptation_suggested
              : null,
          proposed_care_type: f.metrics.proposed_care_type
            ? String(f.metrics.proposed_care_type)
            : null,
        },
        lang,
      );
      return {
        file: f.file,
        mdtDate: f.mdtDate ? translateValue(f.mdtDate, lang) : f.file,
        isCurrent: f.file === currentForm.file,
        isLatest: idx === sorted.length - 1,
        priorityLevel: fPrio,
        priorityLabel: fPrioInfo.label,
        orientationLabel: fOrient.label,
      };
    });

    const cumulativeDurationSec = Object.values(currentForm.executionTimes).reduce(
      (acc, v) => acc + (typeof v === "number" ? v : 0),
      0,
    );

    const [allPatients, agents] = await Promise.all([
      this.api.listPatients(domain, false),
      this.api.listAgents(domain, lang),
    ]);

    const careMeta = getSectionPresentation("CareOrientationProposal", currentForm.domain, lang);
    const careReasoning =
      typeof careSec.reasoning_thinking === "string" && careSec.reasoning_thinking.trim()
        ? careSec.reasoning_thinking.trim()
        : null;
    const careDuration =
      currentForm.executionTimes.CareOrientationProposal ??
      (typeof careSec.time_execution === "number"
        ? Math.round(careSec.time_execution * 10) / 10
        : null);

    return {
      patientId: currentForm.patientId,
      patientName,
      firstName,
      lastName,
      dateBirth:
        admin.date_birth && admin.date_birth !== "Not_given"
          ? translateValue(admin.date_birth, lang)
          : null,
      gender:
        admin.gender && admin.gender !== "Not_given" ? translateValue(admin.gender, lang) : null,
      domain: currentForm.domain,
      rcpCount: sorted.length,
      cumulativeDurationSec: Math.round(cumulativeDurationSec * 10) / 10,
      currentForm,
      timeline,
      prevSessionFile: currentIndex > 0 ? sorted[currentIndex - 1]!.file : null,
      nextSessionFile: currentIndex < sorted.length - 1 ? sorted[currentIndex + 1]!.file : null,
      priorityBadge,
      completenessBadge,
      orientationBadge,
      specialties,
      synopticMarkers,
      deltas,
      sections,
      opinions,
      careProposal: {
        careAdaptationSuggested,
        proposedCareType,
        clinicalRationale: careSec.clinical_rationale ? String(careSec.clinical_rationale) : null,
        reasoningThinking: careReasoning,
        userPrompt: careMeta.userPrompt ?? null,
        durationSec: careDuration,
      },
      allPatients,
      agents,
    };
  }

  private buildSynopticMarkers(
    form: MdtFormDetail,
    deltas: LongitudinalDelta[],
    lang: Language,
  ): PatientDossierView["synopticMarkers"] {
    const deltaMap = new Map(deltas.map((d) => [d.key, d]));
    if (form.domain === "sma") {
      const gen = (form.sections.GeneticDiagnosis ?? {}) as Record<string, unknown>;
      const mot = (form.sections.MotorFunctionStatus ?? {}) as Record<string, unknown>;
      const resp = (form.sections.RespiratoryFunction ?? {}) as Record<string, unknown>;
      const ortho = (form.sections.OrthopedicAndSpineStatus ?? {}) as Record<string, unknown>;
      return [
        {
          key: "sma_type",
          label: "Type SMA",
          value: translateValue(mot.sma_type, lang),
          isMissing: !mot.sma_type,
        },
        {
          key: "smn2_copy_count",
          label: "Copies SMN2",
          value: translateValue(gen.smn2_copy_count, lang),
          isMissing: gen.smn2_copy_count === undefined,
        },
        {
          key: "hfmse_score",
          label: "HFMSE",
          value:
            mot.hfmse_score !== undefined ? `${mot.hfmse_score}/66` : translateValue(null, lang),
          isMissing: mot.hfmse_score === undefined,
          delta: deltaMap.get("hfmse_score"),
        },
        {
          key: "rulm_score",
          label: "RULM",
          value: mot.rulm_score !== undefined ? `${mot.rulm_score}/37` : translateValue(null, lang),
          isMissing: mot.rulm_score === undefined,
          delta: deltaMap.get("rulm_score"),
        },
        {
          key: "forced_vital_capacity_percent",
          label: "CVF",
          value:
            resp.forced_vital_capacity_percent !== undefined
              ? `${resp.forced_vital_capacity_percent} %`
              : translateValue(null, lang),
          isMissing: resp.forced_vital_capacity_percent === undefined,
          delta: deltaMap.get("forced_vital_capacity_percent"),
        },
        {
          key: "scoliosis_cobb_angle",
          label: "Rachis / Cobb",
          value:
            ortho.scoliosis_cobb_angle !== undefined
              ? `${ortho.scoliosis_cobb_angle}°`
              : translateValue(ortho.has_scoliosis ?? null, lang),
          isMissing: ortho.scoliosis_cobb_angle === undefined && ortho.has_scoliosis === undefined,
          delta: deltaMap.get("scoliosis_cobb_angle"),
        },
      ];
    }

    const loc = (form.sections.TumorLocation ?? {}) as Record<string, unknown>;
    const bio = (form.sections.TumorBiology ?? {}) as Record<string, unknown>;
    const perf = (form.sections.PatientPerformanceStatus ?? {}) as Record<string, unknown>;
    const chemo = (form.sections.Chemotherapy ??
      form.sections.ChemotherapyTreament ??
      {}) as Record<string, unknown>;
    const chemoList = Array.isArray(chemo.chemotherapy_list)
      ? (chemo.chemotherapy_list as Array<Record<string, unknown>>)
      : [];
    const firstChemoName =
      chemo.chemotherapy_name ?? chemoList[0]?.chemotherapy_name ?? chemo.chemotherapy;

    return [
      {
        key: "tumor_location",
        label: "Organe / Tumeur",
        value: translateValue(loc.tumor_location, lang),
        isMissing: !loc.tumor_location,
      },
      {
        key: "stage",
        label: "Diagnostic & stade",
        value: translateValue(loc.stage ?? loc.tumor_location, lang),
        isMissing: !loc.stage && !loc.tumor_location,
      },
      {
        key: "ca19_9",
        label: "Biologie / MSI",
        value: translateValue(bio.ca19_9 ?? bio.msi_state, lang),
        isMissing: !bio.ca19_9 && !bio.msi_state,
      },
      {
        key: "performance_status",
        label: "OMS / ECOG",
        value: translateValue(perf.performance_status, lang),
        isMissing: perf.performance_status === undefined,
        delta: deltaMap.get("performance_status"),
      },
      {
        key: "chemotherapy_name",
        label: "Traitement systémique",
        value: translateValue(firstChemoName, lang),
        isMissing: !firstChemoName && chemo.chemotherapy === undefined,
      },
    ];
  }

  private extractSectionHeaderSummary(
    sectionName: string,
    rawObj: Record<string, unknown>,
    subCards: DossierSubCardView[],
    fields: DossierFieldView[],
    lang: Language,
  ): string {
    if (sectionName === "TumorLocation") {
      return translateValue(rawObj.tumor_location, lang);
    }
    if (sectionName === "TumorBiology") {
      const parts = [rawObj.msi_state, rawObj.ca19_9]
        .filter((v) => v !== undefined && v !== null && v !== "")
        .map((v) => translateValue(v, lang));
      return parts.join(" · ") || translateValue(null, lang);
    }
    if (sectionName === "PatientPerformanceStatus") {
      const ps = rawObj.performance_status;
      if (ps === undefined || ps === null || ps === "") return translateValue(null, lang);
      return `OMS ${translateValue(ps, lang)}`;
    }
    if (sectionName === "RadiologicExams" || sectionName === "RadiologicalExams") {
      if (subCards.length === 0) return lang === "fr" ? "Aucun examen" : "No exam";
      return lang === "fr"
        ? `${subCards.length} examen${subCards.length > 1 ? "s" : ""}`
        : `${subCards.length} exam(s)`;
    }
    if (sectionName === "PreviousCurativeSurgery" || sectionName === "PreviousSurgery") {
      const has = rawObj.previous_curative_surgery;
      if (has === true) {
        const dt = rawObj.previous_curative_surgery_date;
        return dt && dt !== "Not_given"
          ? `${translateValue(true, lang)} (${translateValue(dt, lang)})`
          : translateValue(true, lang);
      }
      return translateValue(has ?? false, lang);
    }
    if (sectionName === "PlannedCurativeSurgery" || sectionName === "PlannedSurgery") {
      return translateValue(rawObj.planned_curative_surgery ?? false, lang);
    }
    if (sectionName === "ChemotherapyTreament" || sectionName === "Chemotherapy") {
      if (rawObj.chemotherapy === false) return translateValue(false, lang);
      if (rawObj.chemotherapy_name) return String(rawObj.chemotherapy_name);
      if (subCards.length > 0) {
        return `${subCards[0]!.title}${subCards.length > 1 ? ` (+${subCards.length - 1})` : ""}`;
      }
      return translateValue(rawObj.chemotherapy, lang);
    }
    if (sectionName === "MTDCompleted") {
      const missing = Array.isArray(rawObj.what_missing) ? rawObj.what_missing.length : 0;
      if (rawObj.is_mtd_complete === true && missing === 0) {
        return lang === "fr" ? "Dossier complet" : "Complete";
      }
      return lang === "fr"
        ? `${Math.max(1, missing)} élément(s) manquant(s)`
        : `${Math.max(1, missing)} missing item(s)`;
    }
    if (sectionName === "PatientAdministrative") {
      const fn =
        rawObj.first_name && rawObj.first_name !== "Not_given" ? String(rawObj.first_name) : "";
      const ln =
        rawObj.last_name && rawObj.last_name !== "Not_given" ? String(rawObj.last_name) : "";
      const rcpDate =
        rawObj.date_rcp && rawObj.date_rcp !== "Not_given"
          ? translateValue(rawObj.date_rcp, lang)
          : "";
      return (
        [`${ln} ${fn}`.trim(), rcpDate].filter(Boolean).join(" · ") || translateValue(null, lang)
      );
    }

    return (
      fields
        .filter((f) => !f.isLongText && !f.hiddenInReadView)
        .map((f) => f.value)
        .filter((val) => val && val !== "Non renseigné" && val !== "Not documented")
        .slice(0, 2)
        .join(" · ") || translateValue(null, lang)
    );
  }

  private buildSections(form: MdtFormDetail, lang: Language): DossierSectionView[] {
    const skip = new Set(["ExpertAnswer", "CareOrientationProposal"]);
    const internalKeys = new Set([
      "reasoning_thinking",
      "time_execution",
      "value",
      "manual_edits",
      "mtd_complete",
      "references",
    ]);
    const result: DossierSectionView[] = [];

    for (const [sectionName, rawSectionObj] of Object.entries(form.sections)) {
      if (skip.has(sectionName)) continue;
      const meta = getSectionPresentation(sectionName, form.domain, lang);
      const rawObj: Record<string, unknown> = { ...(rawSectionObj ?? {}) };

      // Unpack nested mtd_complete object if present (avoiding raw JSON stringification)
      if (
        sectionName === "MTDCompleted" &&
        rawObj.mtd_complete &&
        typeof rawObj.mtd_complete === "object" &&
        !Array.isArray(rawObj.mtd_complete)
      ) {
        const nested = rawObj.mtd_complete as Record<string, unknown>;
        if (rawObj.is_mtd_complete === undefined && nested.is_mtd_complete !== undefined) {
          rawObj.is_mtd_complete = nested.is_mtd_complete;
        }
        if (rawObj.what_missing === undefined && nested.what_missing !== undefined) {
          rawObj.what_missing = nested.what_missing;
        }
        if (rawObj.reflection === undefined && nested.reflection !== undefined) {
          rawObj.reflection = nested.reflection;
        }
        if (rawObj.references === undefined && nested.references !== undefined) {
          rawObj.references = nested.references;
        }
      }

      const fields: DossierFieldView[] = [];
      const subCards: DossierSubCardView[] = [];
      const references: CitationRef[] = Array.isArray(rawObj.references)
        ? (rawObj.references as Array<Record<string, unknown>>).map((r) => ({
            name: String(r.name ?? ""),
            page: (r.page as string | number | null) ?? null,
            position: r.position ? String(r.position) : null,
            excerpt: r.excerpt ? String(r.excerpt) : null,
          }))
        : [];

      for (const [k, v] of Object.entries(rawObj)) {
        if (internalKeys.has(k)) continue;

        if ((k === "exams_list" || k === "radiological_exams") && Array.isArray(v)) {
          for (const item of v) {
            if (item && typeof item === "object") {
              const ex = item as Record<string, unknown>;
              subCards.push({
                title: String(ex.exam_name ?? formatFieldLabel("exam_name", lang)),
                badge: ex.exam_type ? translateValue(ex.exam_type, lang) : null,
                subtitle:
                  ex.exam_date && ex.exam_date !== "Not_given"
                    ? translateValue(ex.exam_date, lang)
                    : null,
                body: ex.exam_result
                  ? translateValue(ex.exam_result, lang)
                  : translateValue(null, lang),
              });
            }
          }
          const summaryVal =
            subCards.length > 0
              ? subCards
                  .map(
                    (sc) =>
                      `${sc.badge ? `[${sc.badge}] ` : ""}${sc.title}${sc.subtitle ? ` (${sc.subtitle})` : ""} : ${sc.body}`,
                  )
                  .join(" ; ")
              : translateValue(null, lang);
          fields.push({
            key: k,
            label: formatFieldLabel(k, lang),
            value: summaryVal,
            rawValue: v,
            isLongText: true,
            hiddenInReadView: subCards.length > 0,
          });
          continue;
        }

        if (k === "chemotherapy_list" && Array.isArray(v)) {
          for (const item of v) {
            if (item && typeof item === "object") {
              const ch = item as Record<string, unknown>;
              const dates = [ch.chemotherapy_start_date, ch.chemotherapy_end_date]
                .filter((d) => Boolean(d) && d !== "Not_given")
                .map((d) => translateValue(d, lang))
                .join(" → ");
              subCards.push({
                title: String(ch.chemotherapy_name ?? formatFieldLabel("chemotherapy_name", lang)),
                badge: "Chimiothérapie",
                subtitle: dates || null,
                body: ch.chemotherapy_tolerance
                  ? `Tolérance : ${translateValue(ch.chemotherapy_tolerance, lang)}`
                  : translateValue(null, lang),
              });
            }
          }
          const summaryVal =
            subCards.length > 0
              ? subCards
                  .map((sc) => `${sc.title}${sc.subtitle ? ` (${sc.subtitle})` : ""} — ${sc.body}`)
                  .join(" ; ")
              : translateValue(null, lang);
          fields.push({
            key: k,
            label: formatFieldLabel(k, lang),
            value: summaryVal,
            rawValue: v,
            isLongText: true,
            hiddenInReadView: subCards.length > 0,
          });
          continue;
        }

        let formatted: string;
        if (Array.isArray(v)) {
          formatted =
            v.length === 0
              ? lang === "fr"
                ? "Aucun"
                : "None"
              : v
                  .map((item) =>
                    typeof item === "object" && item !== null
                      ? Object.entries(item as Record<string, unknown>)
                          .filter(([sk, sv]) => !internalKeys.has(sk) && Boolean(sv))
                          .map(([, sv]) => translateValue(sv, lang))
                          .join(" · ")
                      : translateValue(item, lang),
                  )
                  .join(" ; ");
        } else if (typeof v === "object" && v !== null) {
          formatted = Object.entries(v as Record<string, unknown>)
            .filter(([sk, sv]) => !internalKeys.has(sk) && sv !== undefined && sv !== null)
            .map(([sk, sv]) => `${formatFieldLabel(sk, lang)} : ${translateValue(sv, lang)}`)
            .join(" · ");
        } else {
          formatted = translateValue(v, lang);
        }

        const finalVal = formatted || translateValue(null, lang);
        const cleanedRaw = typeof v === "string" && /\d{4}-\d{2}-\d{2}T/.test(v) ? finalVal : v;
        fields.push({
          key: k,
          label: formatFieldLabel(k, lang),
          value: finalVal,
          rawValue: cleanedRaw,
          isLongText: LONG_TEXT_KEYS.has(k) || finalVal.length > 90,
        });
      }

      const summaryText = this.extractSectionHeaderSummary(
        sectionName,
        rawObj,
        subCards,
        fields,
        lang,
      );

      const manualMeta = form.manualEdits[sectionName] ?? null;
      const manualDiffs: DossierManualDiffView[] = [];
      if (manualMeta?.modified_fields && typeof manualMeta.modified_fields === "object") {
        for (const [fKey, diff] of Object.entries(manualMeta.modified_fields)) {
          if (diff && typeof diff === "object") {
            manualDiffs.push({
              key: fKey,
              label: formatFieldLabel(fKey, lang),
              aiValue: translateValue(diff.ai_value, lang),
              humanValue: translateValue(diff.human_value, lang),
            });
          }
        }
      }

      const reasoningThinking =
        typeof rawObj.reasoning_thinking === "string" && rawObj.reasoning_thinking.trim()
          ? rawObj.reasoning_thinking.trim()
          : null;
      const durationSec =
        form.executionTimes[sectionName] ??
        (typeof rawObj.time_execution === "number"
          ? Math.round(rawObj.time_execution * 10) / 10
          : null);

      result.push({
        name: sectionName,
        meta,
        summaryText,
        fields,
        subCards,
        references,
        rawData: rawObj,
        isManual: Boolean(manualMeta),
        manualMeta,
        manualDiffs,
        reasoningThinking,
        userPrompt: meta.userPrompt ?? null,
        durationSec,
      });
    }

    return result.sort((a, b) => a.meta.order - b.meta.order);
  }

  private buildOpinions(form: MdtFormDetail, lang: Language): SpecialtyOpinionItem[] {
    const rawExperts = (form.sections.ExpertAnswer ?? {}) as Record<
      string,
      Record<string, unknown>
    >;
    const items: SpecialtyOpinionItem[] = [];

    for (const [agentKey, payload] of Object.entries(rawExperts)) {
      if (!payload || typeof payload !== "object") continue;
      const pres = getAgentPresentation(agentKey, lang);
      const relevant = payload.expert_relevant !== false;
      const priorityLevel = normalizePriorityLevel(payload.patient_priority);
      const whyRelevant = String(payload.why_relevant ?? "");
      const reasoningThinking =
        typeof payload.reasoning_thinking === "string" && payload.reasoning_thinking.trim()
          ? payload.reasoning_thinking.trim()
          : null;
      const executionSeconds =
        typeof payload.time_execution === "number"
          ? Math.round(payload.time_execution * 10) / 10
          : null;
      const rawSuggestions = Array.isArray(payload.suggestions)
        ? (payload.suggestions as Array<Record<string, unknown>>)
        : [];

      const suggestions: ExpertSuggestion[] = rawSuggestions.map((s) => ({
        suggestion: String(s.suggestion ?? ""),
        why: s.why ? String(s.why) : undefined,
        references: Array.isArray(s.references)
          ? (s.references as Array<Record<string, unknown>>).map((r) => ({
              name: String(r.name ?? ""),
              page: (r.page as string | number | null) ?? null,
              position: r.position ? String(r.position) : null,
              excerpt: r.excerpt ? String(r.excerpt) : null,
            }))
          : [],
      }));

      const sources: CitationRef[] = Array.isArray(payload.sources_relevant)
        ? (payload.sources_relevant as Array<Record<string, unknown>>).map((r) => ({
            name: String(r.name ?? ""),
            page: (r.page as string | number | null) ?? null,
            position: r.position ? String(r.position) : null,
            excerpt: r.excerpt ? String(r.excerpt) : null,
          }))
        : [];

      items.push({
        agentKey,
        agentLabel: pres.label,
        agentIcon: pres.icon,
        relevant,
        priorityLevel,
        whyRelevant,
        suggestions,
        sources,
        reasoningThinking,
        executionSeconds,
      });
    }

    return items.sort((a, b) => {
      if (a.relevant !== b.relevant) return a.relevant ? -1 : 1;
      return priorityRank(a.priorityLevel) - priorityRank(b.priorityLevel);
    });
  }

  async updateSection(
    filename: string,
    section: string,
    data: Record<string, unknown>,
    editedBy: string,
    domain: ClinicalDomain,
  ): Promise<MdtFormDetail> {
    return this.api.updateFormSection(filename, section, data, editedBy, domain);
  }

  async rerunSection(
    filename: string,
    section: string,
    preserveManualEdits: boolean,
    domain: ClinicalDomain,
  ): Promise<{ jobId: string; preserveManualEdits: boolean }> {
    return this.api.rerunSection(filename, section, preserveManualEdits, domain);
  }

  async processFullForm(
    filename: string,
    preserveManualEdits: boolean,
    domain: ClinicalDomain,
  ): Promise<{ jobId: string }> {
    return this.api.processFullForm(filename, preserveManualEdits, domain);
  }

  async linkPatient(
    filename: string,
    patientId: string | null,
    domain: ClinicalDomain,
  ): Promise<void> {
    return this.api.linkFormToPatient(filename, patientId, domain);
  }

  async askQuestion(
    target: { filename?: string; patientId?: string },
    question: string,
    domain: ClinicalDomain,
    lang: Language,
    agentName?: string,
  ): Promise<ChatReply> {
    return this.api.askDossierQuestion(target, question, domain, lang, agentName);
  }
}
