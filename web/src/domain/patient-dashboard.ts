import { translateValue } from "./i18n.js";
import type {
  ClinicalDomain,
  MdtFormDetail,
  PatientDashboardView,
  PatientMetricPointView,
  PatientMetricSeriesView,
  PatientRecordSummaryContentView,
  PatientRecordSummaryView,
} from "./types.js";

export interface MetricDescriptorSpec {
  metricKey: string;
  section: string;
  field: string;
  label: string;
  unit: string;
  scaleMin?: number | null;
  scaleMax?: number | null;
  polarity: "higher_is_better" | "lower_is_better" | "neutral";
  valueType: "numeric_or_mixed" | "categorical" | "boolean" | "list";
}

function parseMetricCatalog(entries: readonly string[]): MetricDescriptorSpec[] {
  return entries.map((entry) => {
    const [
      metricKey = "",
      label = "",
      unit = "",
      rawPolarity = "neutral",
      rawType = "categorical",
      rawMin = "",
      rawMax = "",
    ] = entry.split("|");
    const [section = "", field = ""] = metricKey.split(".");
    const polarity = (
      rawPolarity === "higher_is_better" || rawPolarity === "lower_is_better"
        ? rawPolarity
        : "neutral"
    ) as MetricDescriptorSpec["polarity"];
    const valueType = (
      rawType === "numeric_or_mixed" || rawType === "boolean" || rawType === "list"
        ? rawType
        : "categorical"
    ) as MetricDescriptorSpec["valueType"];
    const spec: MetricDescriptorSpec = {
      metricKey,
      section,
      field,
      label,
      unit,
      polarity,
      valueType,
    };
    if (rawMin !== "") spec.scaleMin = Number(rawMin);
    if (rawMax !== "") spec.scaleMax = Number(rawMax);
    return spec;
  });
}

export const SMA_METRIC_SPECS: MetricDescriptorSpec[] = parseMetricCatalog([
  "MotorFunctionStatus.rulm_score|Score RULM (Membre supérieur)|/ 37|higher_is_better|numeric_or_mixed|0|37",
  "MotorFunctionStatus.hfmse_score|Score HFMSE (Fonction motrice)|/ 66|higher_is_better|numeric_or_mixed|0|66",
  "MotorFunctionStatus.chop_intend_score|Score CHOP-INTEND|/ 64|higher_is_better|numeric_or_mixed|0|64",
  "RespiratoryFunction.forced_vital_capacity_percent|Capacité Vitale Forcée (CVF)|%|higher_is_better|numeric_or_mixed|0|140",
  "RespiratoryFunction.daily_ventilation_hours|Ventilation quotidienne|h/j|lower_is_better|numeric_or_mixed|0|24",
  "OrthopedicAndSpineStatus.scoliosis_cobb_angle|Angle de Cobb (Scoliose)|°|lower_is_better|numeric_or_mixed|0|120",
  "PatientPerformanceStatus.performance_status|Statut OMS / WHO|/ 4|lower_is_better|numeric_or_mixed|0|4",
  "MotorFunctionStatus.motor_milestones|Jalons moteurs acquis||neutral|list",
  "RespiratoryFunction.ventilation_type|Support ventilatoire||neutral|categorical",
  "BulbarAndNutritionalStatus.feeding_mode|Mode d'alimentation||neutral|categorical",
  "BulbarAndNutritionalStatus.nutritional_status|Statut nutritionnel||neutral|categorical",
]);

export const ONCOLOGY_METRIC_SPECS: MetricDescriptorSpec[] = parseMetricCatalog([
  "PatientPerformanceStatus.performance_status|Statut OMS / WHO|/ 4|lower_is_better|numeric_or_mixed|0|4",
  "TumorBiology.ca19_9|Marqueur tumoral CA 19-9|U/mL|lower_is_better|numeric_or_mixed|0|",
  "TumorBiology.ace|Marqueur tumoral ACE (CEA)|ng/mL|lower_is_better|numeric_or_mixed|0|",
  "TumorBiology.afp|Alpha-fœtoprotéine (AFP)|ng/mL|lower_is_better|numeric_or_mixed|0|",
  "TumorBiology.dpd_uracilemia|Uracilémie pré-thérapeutique (DPD)|ng/mL|lower_is_better|numeric_or_mixed|0|",
  "CancerDescription.target_lesion_size_mm|Taille de la lésion cible|mm|lower_is_better|numeric_or_mixed|0|",
  "NutritionalStatus.weight_kg|Poids corporel|kg|higher_is_better|numeric_or_mixed|0|",
  "NutritionalStatus.weight_loss_percent|Perte de poids|%|lower_is_better|numeric_or_mixed|0|100",
  "NutritionalStatus.bmi|Indice de Masse Corporelle (IMC)|kg/m²|higher_is_better|numeric_or_mixed|10|60",
  "HepaticStatus.bilirubin_umol_l|Bilirubine totale|µmol/L|lower_is_better|numeric_or_mixed|0|",
  "CancerDescription.tnm_status|Classification TNM||neutral|categorical",
  "CancerDescription.recist_response|Réponse radiologique (RECIST 1.1)||neutral|categorical",
  "CancerDescription.figo_stage|Stade FIGO / UICC||neutral|categorical",
  "CancerDescription.histological_grade|Grade histologique||neutral|categorical",
  "CancerDescription.type_of_cancer|Type histologique / tumoral||neutral|categorical",
  "CancerDescription.metastatic_sites|Sites métastatiques||lower_is_better|list",
  "TumorLocation.tumor_location|Localisation tumorale||neutral|categorical",
  "TumorBiology.msi_state|Statut MSI / MMR||neutral|categorical",
  "TumorBiology.ras_braf_status|Statut moléculaire RAS / BRAF||neutral|categorical",
  "TumorBiology.her2_status|Statut HER2 / PD-L1||neutral|categorical",
  "SurgicalStatus.resectability_status|Statut de résécabilité||neutral|categorical",
  "SurgicalStatus.surgery_done|Chirurgie réalisée||neutral|boolean",
  "SurgicalStatus.resection_margin|Marges d'exérèse (R0/R1/R2)||neutral|categorical",
  "HepaticStatus.child_pugh_score|Score de Child-Pugh||neutral|categorical",
  "HepaticStatus.bclc_stage|Stade BCLC (CHC)||neutral|categorical",
  "NutritionalStatus.nutritional_status|Statut nutritionnel||neutral|categorical",
  "Chemotherapy.chemotherapy_name|Ligne de chimiothérapie||neutral|categorical",
  "Chemotherapy.chemotherapy_tolerance|Tolérance du traitement||neutral|categorical",
]);

export function getDomainMetricSpecs(domain: ClinicalDomain): MetricDescriptorSpec[] {
  return domain === "sma" ? SMA_METRIC_SPECS : ONCOLOGY_METRIC_SPECS;
}

const BILATERAL_RE =
  /(\d+(?:[.,]\d+)?)\s*\(\s*([DGdgRrLl])\s*\)\s*[/|,-]\s*(\d+(?:[.,]\d+)?)\s*\(\s*([DGdgRrLl])\s*\)/;
const LEADING_NUM_RE = /^\s*([-+]?\d+(?:[.,]\d+)?)(?:\s*\/\s*(\d+(?:[.,]\d+)?))?/;

export function parseRawMetricObservation(
  rawValue: unknown,
  spec?: MetricDescriptorSpec,
): {
  rawValue: unknown;
  displayValue: string;
  numericValue: number | null;
  subValues: Record<string, number> | null;
  isAnnotativeOnly: boolean;
} {
  const valueType = spec?.valueType ?? "numeric_or_mixed";
  if (typeof rawValue === "boolean") {
    return {
      rawValue,
      displayValue: rawValue ? "Oui" : "Non",
      numericValue: rawValue ? 1 : 0,
      subValues: null,
      isAnnotativeOnly: false,
    };
  }
  if (typeof rawValue === "number" && Number.isFinite(rawValue)) {
    return {
      rawValue,
      displayValue: String(rawValue),
      numericValue: rawValue,
      subValues: null,
      isAnnotativeOnly: false,
    };
  }
  if (Array.isArray(rawValue)) {
    const items = rawValue
      .map((x) => translateValue(String(x ?? "").trim(), "fr"))
      .filter((x) => Boolean(x) && x !== "—");
    return {
      rawValue,
      displayValue: items.length > 0 ? items.join(", ") : "—",
      numericValue: valueType === "list" ? items.length : null,
      subValues: null,
      isAnnotativeOnly: valueType === "numeric_or_mixed",
    };
  }

  const text = rawValue !== null && rawValue !== undefined ? String(rawValue).trim() : "";
  if (!text) {
    return {
      rawValue,
      displayValue: "—",
      numericValue: null,
      subValues: null,
      isAnnotativeOnly: true,
    };
  }

  if (valueType !== "numeric_or_mixed") {
    return {
      rawValue,
      displayValue: translateValue(text, "fr"),
      numericValue: null,
      subValues: null,
      isAnnotativeOnly: false,
    };
  }

  const bilat = text.match(BILATERAL_RE);
  if (bilat) {
    const v1 = Number(bilat[1]?.replace(",", "."));
    const k1 = (bilat[2] ?? "D").toUpperCase();
    const v2 = Number(bilat[3]?.replace(",", "."));
    const k2 = (bilat[4] ?? "G").toUpperCase();
    return {
      rawValue,
      displayValue: text,
      numericValue: (v1 + v2) / 2,
      subValues: { [k1]: v1, [k2]: v2 },
      isAnnotativeOnly: false,
    };
  }

  const numMatch = text.match(LEADING_NUM_RE);
  if (numMatch?.[1]) {
    const num = Number(numMatch[1].replace(",", "."));
    if (Number.isFinite(num)) {
      return {
        rawValue,
        displayValue: text,
        numericValue: num,
        subValues: null,
        isAnnotativeOnly: false,
      };
    }
  }

  return {
    rawValue,
    displayValue: text,
    numericValue: null,
    subValues: null,
    isAnnotativeOnly: true,
  };
}

function formatFrDate(isoDate: string | null): string {
  if (!isoDate) return "Date non renseignée";
  const m = isoDate.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (m) return `${m[3]}/${m[2]}/${m[1]}`;
  return isoDate;
}

export function buildPatientMetricSeriesFromForms(
  forms: MdtFormDetail[],
  domain: ClinicalDomain,
): PatientMetricSeriesView[] {
  const specs = getDomainMetricSpecs(domain);
  const chronological = [...forms].sort((a, b) =>
    (a.mdtDate ?? "0000-00-00").localeCompare(b.mdtDate ?? "0000-00-00"),
  );
  if (chronological.length === 0) return [];

  const validTimestamps = chronological
    .map((f) => (f.mdtDate ? Date.parse(f.mdtDate) : Number.NaN))
    .filter((t) => Number.isFinite(t));
  const minTs = validTimestamps.length > 0 ? Math.min(...validTimestamps) : 0;
  const maxTs = validTimestamps.length > 0 ? Math.max(...validTimestamps) : 0;
  const totalSpanDays =
    minTs > 0 && maxTs > minTs ? Math.round((maxTs - minTs) / (1000 * 60 * 60 * 24)) : 0;

  const seriesOut: PatientMetricSeriesView[] = [];

  for (const spec of specs) {
    const points: PatientMetricPointView[] = [];
    let prevNumeric: number | null = null;

    chronological.forEach((form, idx) => {
      let sec = form.sections[spec.section];
      if (!sec && spec.section === "Chemotherapy") {
        sec = form.sections.ChemotherapyTreament;
      }
      if (!sec) return;
      let rawVal = sec[spec.field];
      if (
        (rawVal === undefined || rawVal === null || rawVal === "") &&
        spec.section === "Chemotherapy" &&
        Array.isArray(sec.chemotherapy_list) &&
        sec.chemotherapy_list.length > 0
      ) {
        const firstLine = sec.chemotherapy_list[0];
        if (firstLine && typeof firstLine === "object") {
          rawVal = (firstLine as Record<string, unknown>)[spec.field];
        }
      }
      if (rawVal === undefined || rawVal === null || rawVal === "") return;
      if (Array.isArray(rawVal) && rawVal.length === 0) return;

      const obs = parseRawMetricObservation(rawVal, spec);
      if (obs.displayValue === "—") return;

      const ts = form.mdtDate ? Date.parse(form.mdtDate) : Number.NaN;
      const daysSinceFirst =
        Number.isFinite(ts) && minTs > 0
          ? Math.max(0, Math.round((ts - minTs) / (1000 * 60 * 60 * 24)))
          : idx * 30;
      const xRatio =
        chronological.length <= 1
          ? 0.5
          : totalSpanDays > 0 && Number.isFinite(ts)
            ? Math.min(1, Math.max(0, daysSinceFirst / totalSpanDays))
            : idx / (chronological.length - 1);

      const manualMeta = form.manualEdits?.[spec.section];
      const isManual = Boolean(manualMeta);

      let deltaNumeric: number | null = null;
      let deltaDisplay: string | null = null;
      if (obs.numericValue !== null && prevNumeric !== null) {
        deltaNumeric = Math.round((obs.numericValue - prevNumeric) * 100) / 100;
        const sign = deltaNumeric > 0 ? "+" : "";
        deltaDisplay = `${sign}${deltaNumeric}`;
      }
      if (obs.numericValue !== null) {
        prevNumeric = obs.numericValue;
      }

      points.push({
        formId: form.file,
        formDate: form.mdtDate,
        formDateLabel: formatFrDate(form.mdtDate),
        daysSinceFirstRcp: daysSinceFirst,
        xRatio: Math.round(xRatio * 10000) / 10000,
        rawValue: obs.rawValue,
        displayValue: obs.displayValue,
        numericValue: obs.numericValue,
        subValues: obs.subValues,
        isAnnotativeOnly: obs.isAnnotativeOnly,
        isManual,
        editedBy: manualMeta?.edited_by ?? null,
        editedAt: manualMeta?.edited_at ?? null,
        deltaNumeric,
        deltaDisplay,
      });
    });

    if (points.length > 0) {
      seriesOut.push({
        metricKey: spec.metricKey,
        section: spec.section,
        field: spec.field,
        label: spec.label,
        unit: spec.unit,
        scaleMin: spec.scaleMin ?? null,
        scaleMax: spec.scaleMax ?? null,
        polarity: spec.polarity,
        valueType: spec.valueType,
        points,
      });
    }
  }

  return seriesOut;
}

export function synthesizePatientSummaryFromForms(
  patientName: string,
  forms: MdtFormDetail[],
  domain: ClinicalDomain,
  modelUsed = "mistral-nemo",
): PatientRecordSummaryView {
  const chronological = [...forms].sort((a, b) =>
    (a.mdtDate ?? "0000-00-00").localeCompare(b.mdtDate ?? "0000-00-00"),
  );
  const series = buildPatientMetricSeriesFromForms(chronological, domain);
  const coveredIds = chronological.map((f) => f.file);
  const firstDate = formatFrDate(chronological[0]?.mdtDate ?? null);
  const lastForm = chronological[chronological.length - 1];
  const lastDate = formatFrDate(lastForm?.mdtDate ?? null);
  const domainLabel = domain === "sma" ? "Amyotrophie Spinale (SMA)" : "Oncologie";

  const notableChanges: string[] = [];
  for (const s of series) {
    if (s.points.length >= 2) {
      const firstPt = s.points[0]!;
      const lastPt = s.points[s.points.length - 1]!;
      const unitStr = s.unit ? ` ${s.unit}` : "";
      const deltaStr = lastPt.deltaDisplay ? ` (Δ ${lastPt.deltaDisplay})` : "";
      notableChanges.push(
        `${s.label} : ${firstPt.displayValue}${unitStr} (${firstPt.formDateLabel}) → ${lastPt.displayValue}${unitStr} (${lastPt.formDateLabel})${deltaStr}`,
      );
    } else if (s.points.length === 1) {
      const pt = s.points[0]!;
      const unitStr = s.unit ? ` ${s.unit}` : "";
      notableChanges.push(`${s.label} : ${pt.displayValue}${unitStr} (${pt.formDateLabel})`);
    }
  }

  const mdtDecisionsRecap: string[] = [];
  const rationales: string[] = [];
  const unresolvedVigilancePoints: string[] = [];

  for (const f of chronological) {
    const dLabel = formatFrDate(f.mdtDate);
    const care = f.sections.CareOrientationProposal;
    if (care) {
      if (care.proposed_care_type) {
        mdtDecisionsRecap.push(`[${dLabel}] ${String(care.proposed_care_type)}`);
      }
      if (care.clinical_rationale) {
        rationales.push(`[${dLabel}] ${String(care.clinical_rationale)}`);
      }
    }
    for (const m of f.metrics.missing_items ?? []) {
      const clean = String(m).trim();
      if (clean && !unresolvedVigilancePoints.includes(clean)) {
        unresolvedVigilancePoints.push(clean);
      }
    }
  }

  const content: PatientRecordSummaryContentView = {
    clinicalTrajectoryOverview: `Dossier longitudinal (${domainLabel}) de ${patientName} consolidant ${coveredIds.length} fiche(s) RCP du ${firstDate} au ${lastDate}.`,
    diseaseAndTreatmentEvolution:
      rationales.slice(-2).join(" ") ||
      "Évolution clinique et thérapeutique documentée sur l'historique des séances RCP.",
    notableMetricChanges: notableChanges.slice(0, 8),
    unresolvedVigilancePoints: unresolvedVigilancePoints.slice(0, 6),
    mdtDecisionsRecap,
    sourcesUsed: coveredIds,
  };

  return {
    hasSummary: true,
    generatedAt: new Date().toISOString(),
    coveredFormIds: coveredIds,
    latestFormIdAtGeneration: lastForm?.file ?? null,
    latestFormDateAtGeneration: lastForm?.mdtDate ?? null,
    modelUsed,
    isObsolete: false,
    obsoleteReasons: [],
    newFormsSinceSummary: [],
    removedFormsSinceSummary: [],
    modifiedFormsSinceSummary: [],
    content,
    activeJob: null,
  };
}

export function evaluatePatientSummaryObsolescence(
  summary: PatientRecordSummaryView | null,
  forms: MdtFormDetail[],
): PatientRecordSummaryView {
  if (!summary?.hasSummary) {
    return {
      hasSummary: false,
      generatedAt: null,
      coveredFormIds: [],
      latestFormIdAtGeneration: null,
      latestFormDateAtGeneration: null,
      modelUsed: null,
      isObsolete: false,
      obsoleteReasons: [],
      newFormsSinceSummary: [],
      removedFormsSinceSummary: [],
      modifiedFormsSinceSummary: [],
      content: null,
      activeJob: summary?.activeJob ?? null,
    };
  }

  const coveredSet = new Set(summary.coveredFormIds);
  const currentIds = forms.map((f) => f.file);
  const currentSet = new Set(currentIds);

  const newForms = currentIds.filter((id) => !coveredSet.has(id));
  const removedForms = summary.coveredFormIds.filter((id) => !currentSet.has(id));

  const genTime = summary.generatedAt ? Date.parse(summary.generatedAt) : Number.NaN;
  const modifiedForms: string[] = [];
  if (Number.isFinite(genTime)) {
    for (const f of forms) {
      if (!coveredSet.has(f.file)) continue;
      for (const meta of Object.values(f.manualEdits ?? {})) {
        const editTs = meta?.edited_at ? Date.parse(meta.edited_at) : Number.NaN;
        if (Number.isFinite(editTs) && editTs > genTime && !modifiedForms.includes(f.file)) {
          modifiedForms.push(f.file);
        }
      }
    }
  }

  const reasons: string[] = [];
  if (newForms.length > 0) reasons.push("NEW_FORM_ADDED");
  if (removedForms.length > 0) reasons.push("FORM_REMOVED");
  if (modifiedForms.length > 0) reasons.push("EXISTING_FORM_UPDATED");

  return {
    ...summary,
    isObsolete: reasons.length > 0,
    obsoleteReasons: reasons,
    newFormsSinceSummary: newForms,
    removedFormsSinceSummary: removedForms,
    modifiedFormsSinceSummary: modifiedForms,
  };
}

export function buildPatientDashboardFromForms(
  patientId: string,
  patientName: string,
  domain: ClinicalDomain,
  forms: MdtFormDetail[],
  summary: PatientRecordSummaryView | null,
): PatientDashboardView {
  const chronological = [...forms].sort((a, b) =>
    (b.mdtDate ?? "0000-00-00").localeCompare(a.mdtDate ?? "0000-00-00"),
  );
  return {
    patientId,
    patientName,
    domain,
    latestFile: chronological[0]?.file ?? null,
    rcpCount: forms.length,
    metrics: buildPatientMetricSeriesFromForms(forms, domain),
    summary: evaluatePatientSummaryObsolescence(summary, forms),
  };
}
