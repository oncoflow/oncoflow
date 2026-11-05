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

export const SMA_METRIC_SPECS: MetricDescriptorSpec[] = [
  {
    metricKey: "MotorFunctionStatus.rulm_score",
    section: "MotorFunctionStatus",
    field: "rulm_score",
    label: "Score RULM (Membre supérieur)",
    unit: "/ 37",
    scaleMin: 0,
    scaleMax: 37,
    polarity: "higher_is_better",
    valueType: "numeric_or_mixed",
  },
  {
    metricKey: "MotorFunctionStatus.hfmse_score",
    section: "MotorFunctionStatus",
    field: "hfmse_score",
    label: "Score HFMSE (Fonction motrice)",
    unit: "/ 66",
    scaleMin: 0,
    scaleMax: 66,
    polarity: "higher_is_better",
    valueType: "numeric_or_mixed",
  },
  {
    metricKey: "MotorFunctionStatus.chop_intend_score",
    section: "MotorFunctionStatus",
    field: "chop_intend_score",
    label: "Score CHOP-INTEND",
    unit: "/ 64",
    scaleMin: 0,
    scaleMax: 64,
    polarity: "higher_is_better",
    valueType: "numeric_or_mixed",
  },
  {
    metricKey: "RespiratoryFunction.forced_vital_capacity_percent",
    section: "RespiratoryFunction",
    field: "forced_vital_capacity_percent",
    label: "Capacité Vitale Forcée (CVF)",
    unit: "%",
    scaleMin: 0,
    scaleMax: 140,
    polarity: "higher_is_better",
    valueType: "numeric_or_mixed",
  },
  {
    metricKey: "RespiratoryFunction.daily_ventilation_hours",
    section: "RespiratoryFunction",
    field: "daily_ventilation_hours",
    label: "Ventilation quotidienne",
    unit: "h/j",
    scaleMin: 0,
    scaleMax: 24,
    polarity: "lower_is_better",
    valueType: "numeric_or_mixed",
  },
  {
    metricKey: "OrthopedicAndSpineStatus.scoliosis_cobb_angle",
    section: "OrthopedicAndSpineStatus",
    field: "scoliosis_cobb_angle",
    label: "Angle de Cobb (Scoliose)",
    unit: "°",
    scaleMin: 0,
    scaleMax: 120,
    polarity: "lower_is_better",
    valueType: "numeric_or_mixed",
  },
  {
    metricKey: "PatientPerformanceStatus.performance_status",
    section: "PatientPerformanceStatus",
    field: "performance_status",
    label: "Statut OMS / WHO",
    unit: "/ 4",
    scaleMin: 0,
    scaleMax: 4,
    polarity: "lower_is_better",
    valueType: "numeric_or_mixed",
  },
  {
    metricKey: "MotorFunctionStatus.motor_milestones",
    section: "MotorFunctionStatus",
    field: "motor_milestones",
    label: "Jalons moteurs acquis",
    unit: "",
    polarity: "neutral",
    valueType: "list",
  },
  {
    metricKey: "RespiratoryFunction.ventilation_type",
    section: "RespiratoryFunction",
    field: "ventilation_type",
    label: "Support ventilatoire",
    unit: "",
    polarity: "neutral",
    valueType: "categorical",
  },
  {
    metricKey: "BulbarAndNutritionalStatus.feeding_mode",
    section: "BulbarAndNutritionalStatus",
    field: "feeding_mode",
    label: "Mode d'alimentation",
    unit: "",
    polarity: "neutral",
    valueType: "categorical",
  },
  {
    metricKey: "BulbarAndNutritionalStatus.nutritional_status",
    section: "BulbarAndNutritionalStatus",
    field: "nutritional_status",
    label: "Statut nutritionnel",
    unit: "",
    polarity: "neutral",
    valueType: "categorical",
  },
];

export const ONCOLOGY_METRIC_SPECS: MetricDescriptorSpec[] = [
  {
    metricKey: "PatientPerformanceStatus.performance_status",
    section: "PatientPerformanceStatus",
    field: "performance_status",
    label: "Statut OMS / WHO",
    unit: "/ 4",
    scaleMin: 0,
    scaleMax: 4,
    polarity: "lower_is_better",
    valueType: "numeric_or_mixed",
  },
  {
    metricKey: "TumorBiology.ca19_9",
    section: "TumorBiology",
    field: "ca19_9",
    label: "Marqueur tumoral CA 19-9",
    unit: "U/mL",
    scaleMin: 0,
    polarity: "lower_is_better",
    valueType: "numeric_or_mixed",
  },
  {
    metricKey: "TumorBiology.ace",
    section: "TumorBiology",
    field: "ace",
    label: "Marqueur tumoral ACE (CEA)",
    unit: "ng/mL",
    scaleMin: 0,
    polarity: "lower_is_better",
    valueType: "numeric_or_mixed",
  },
  {
    metricKey: "TumorBiology.afp",
    section: "TumorBiology",
    field: "afp",
    label: "Alpha-fœtoprotéine (AFP)",
    unit: "ng/mL",
    scaleMin: 0,
    polarity: "lower_is_better",
    valueType: "numeric_or_mixed",
  },
  {
    metricKey: "TumorBiology.dpd_uracilemia",
    section: "TumorBiology",
    field: "dpd_uracilemia",
    label: "Uracilémie pré-thérapeutique (DPD)",
    unit: "ng/mL",
    scaleMin: 0,
    polarity: "lower_is_better",
    valueType: "numeric_or_mixed",
  },
  {
    metricKey: "CancerDescription.target_lesion_size_mm",
    section: "CancerDescription",
    field: "target_lesion_size_mm",
    label: "Taille de la lésion cible",
    unit: "mm",
    scaleMin: 0,
    polarity: "lower_is_better",
    valueType: "numeric_or_mixed",
  },
  {
    metricKey: "NutritionalStatus.weight_kg",
    section: "NutritionalStatus",
    field: "weight_kg",
    label: "Poids corporel",
    unit: "kg",
    scaleMin: 0,
    polarity: "higher_is_better",
    valueType: "numeric_or_mixed",
  },
  {
    metricKey: "NutritionalStatus.weight_loss_percent",
    section: "NutritionalStatus",
    field: "weight_loss_percent",
    label: "Perte de poids",
    unit: "%",
    scaleMin: 0,
    scaleMax: 100,
    polarity: "lower_is_better",
    valueType: "numeric_or_mixed",
  },
  {
    metricKey: "NutritionalStatus.bmi",
    section: "NutritionalStatus",
    field: "bmi",
    label: "Indice de Masse Corporelle (IMC)",
    unit: "kg/m²",
    scaleMin: 10,
    scaleMax: 60,
    polarity: "higher_is_better",
    valueType: "numeric_or_mixed",
  },
  {
    metricKey: "HepaticStatus.bilirubin_umol_l",
    section: "HepaticStatus",
    field: "bilirubin_umol_l",
    label: "Bilirubine totale",
    unit: "µmol/L",
    scaleMin: 0,
    polarity: "lower_is_better",
    valueType: "numeric_or_mixed",
  },
  {
    metricKey: "CancerDescription.tnm_status",
    section: "CancerDescription",
    field: "tnm_status",
    label: "Classification TNM",
    unit: "",
    polarity: "neutral",
    valueType: "categorical",
  },
  {
    metricKey: "CancerDescription.recist_response",
    section: "CancerDescription",
    field: "recist_response",
    label: "Réponse radiologique (RECIST 1.1)",
    unit: "",
    polarity: "neutral",
    valueType: "categorical",
  },
  {
    metricKey: "CancerDescription.figo_stage",
    section: "CancerDescription",
    field: "figo_stage",
    label: "Stade FIGO / UICC",
    unit: "",
    polarity: "neutral",
    valueType: "categorical",
  },
  {
    metricKey: "CancerDescription.histological_grade",
    section: "CancerDescription",
    field: "histological_grade",
    label: "Grade histologique",
    unit: "",
    polarity: "neutral",
    valueType: "categorical",
  },
  {
    metricKey: "CancerDescription.type_of_cancer",
    section: "CancerDescription",
    field: "type_of_cancer",
    label: "Type histologique / tumoral",
    unit: "",
    polarity: "neutral",
    valueType: "categorical",
  },
  {
    metricKey: "CancerDescription.metastatic_sites",
    section: "CancerDescription",
    field: "metastatic_sites",
    label: "Sites métastatiques",
    unit: "",
    polarity: "lower_is_better",
    valueType: "list",
  },
  {
    metricKey: "TumorLocation.tumor_location",
    section: "TumorLocation",
    field: "tumor_location",
    label: "Localisation tumorale",
    unit: "",
    polarity: "neutral",
    valueType: "categorical",
  },
  {
    metricKey: "TumorBiology.msi_state",
    section: "TumorBiology",
    field: "msi_state",
    label: "Statut MSI / MMR",
    unit: "",
    polarity: "neutral",
    valueType: "categorical",
  },
  {
    metricKey: "TumorBiology.ras_braf_status",
    section: "TumorBiology",
    field: "ras_braf_status",
    label: "Statut moléculaire RAS / BRAF",
    unit: "",
    polarity: "neutral",
    valueType: "categorical",
  },
  {
    metricKey: "TumorBiology.her2_status",
    section: "TumorBiology",
    field: "her2_status",
    label: "Statut HER2 / PD-L1",
    unit: "",
    polarity: "neutral",
    valueType: "categorical",
  },
  {
    metricKey: "SurgicalStatus.resectability_status",
    section: "SurgicalStatus",
    field: "resectability_status",
    label: "Statut de résécabilité",
    unit: "",
    polarity: "neutral",
    valueType: "categorical",
  },
  {
    metricKey: "SurgicalStatus.surgery_done",
    section: "SurgicalStatus",
    field: "surgery_done",
    label: "Chirurgie réalisée",
    unit: "",
    polarity: "neutral",
    valueType: "boolean",
  },
  {
    metricKey: "SurgicalStatus.resection_margin",
    section: "SurgicalStatus",
    field: "resection_margin",
    label: "Marges d'exérèse (R0/R1/R2)",
    unit: "",
    polarity: "neutral",
    valueType: "categorical",
  },
  {
    metricKey: "HepaticStatus.child_pugh_score",
    section: "HepaticStatus",
    field: "child_pugh_score",
    label: "Score de Child-Pugh",
    unit: "",
    polarity: "neutral",
    valueType: "categorical",
  },
  {
    metricKey: "HepaticStatus.bclc_stage",
    section: "HepaticStatus",
    field: "bclc_stage",
    label: "Stade BCLC (CHC)",
    unit: "",
    polarity: "neutral",
    valueType: "categorical",
  },
  {
    metricKey: "NutritionalStatus.nutritional_status",
    section: "NutritionalStatus",
    field: "nutritional_status",
    label: "Statut nutritionnel",
    unit: "",
    polarity: "neutral",
    valueType: "categorical",
  },
  {
    metricKey: "Chemotherapy.chemotherapy_name",
    section: "Chemotherapy",
    field: "chemotherapy_name",
    label: "Ligne de chimiothérapie",
    unit: "",
    polarity: "neutral",
    valueType: "categorical",
  },
  {
    metricKey: "Chemotherapy.chemotherapy_tolerance",
    section: "Chemotherapy",
    field: "chemotherapy_tolerance",
    label: "Tolérance du traitement",
    unit: "",
    polarity: "neutral",
    valueType: "categorical",
  },
];

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
