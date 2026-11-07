import { describe, expect, it } from "vitest";
import {
  buildDefaultDomainFormSchema,
  buildStrictBackendSectionPayload,
  coerceBooleanValue,
  coerceDateValue,
  coerceNullableBooleanValue,
  coerceNumberValue,
  coerceSectionUpdatePayload,
  coerceSelectValue,
  coerceStringListValue,
  extractNormalizedChemoList,
  extractNormalizedExamsList,
  formatFieldLabel,
  formatRawEditValue,
  getAgentPresentation,
  getSectionFieldSchemas,
  getSectionPresentation,
  isPlaceholderValue,
  parseJsonSchemaToFieldSchemas,
} from "../../src/domain/catalog.js";
import { t, translateValue } from "../../src/domain/i18n.js";
import {
  buildPatientDashboardFromForms,
  evaluatePatientSummaryObsolescence,
  parseRawMetricObservation,
  SMA_METRIC_SPECS,
  synthesizePatientSummaryFromForms,
} from "../../src/domain/patient-dashboard.js";
import {
  computeLongitudinalDeltas,
  computeWorklistKpis,
  deriveCompletenessInfo,
  deriveOrientationInfo,
  filterAndSortCards,
  normalizePriorityLevel,
  priorityRank,
} from "../../src/domain/triage.js";
import type { MdtFormCard, MdtFormDetail } from "../../src/domain/types.js";
import { renderPatientDashboardPanel } from "../../src/ui/components/patient-dashboard.component.js";

describe("Domain Triage & Medico-Legal Rules (ML-1..ML-3)", () => {
  it("normalizes priority strings and ranks high > medium > low > none", () => {
    expect(normalizePriorityLevel("high")).toBe("high");
    expect(normalizePriorityLevel("Urgent, a treatment is needed quickly")).toBe("high");
    expect(normalizePriorityLevel("Patient must be treated urgently")).toBe("high");
    expect(normalizePriorityLevel("medium")).toBe("medium");
    expect(normalizePriorityLevel("Patient must be treated as soon as possible")).toBe("medium");
    expect(normalizePriorityLevel("low")).toBe("low");
    expect(normalizePriorityLevel("Patient is not urgent")).toBe("low");
    expect(normalizePriorityLevel(null)).toBe("none");

    expect(priorityRank("high")).toBeLessThan(priorityRank("medium"));
    expect(priorityRank("medium")).toBeLessThan(priorityRank("low"));
    expect(priorityRank("low")).toBeLessThan(priorityRank("none"));
  });

  it("derives non-prescriptive orientation badge info (ML-1, ML-2)", () => {
    const adapt = deriveOrientationInfo(
      {
        care_adaptation_suggested: true,
        proposed_care_type: "Chimiothérapie 2e ligne",
      },
      "fr",
    );
    expect(adapt.status).toBe("adapt");
    expect(adapt.icon).toBe("ic-compass");
    expect(adapt.badgeClass).toBe("ds-badge--orientation-adapt");
    expect(adapt.label).toBe("Adaptation suggérée");
    expect(adapt.label).not.toMatch(/intervention requise|hors référentiel|décision/i);

    const standard = deriveOrientationInfo(
      {
        care_adaptation_suggested: false,
        proposed_care_type: null,
      },
      "fr",
    );
    expect(standard.status).toBe("standard");
    expect(standard.icon).toBe("ic-check-circle");
    expect(standard.label).toBe("Suivi habituel");

    const pending = deriveOrientationInfo(
      {
        care_adaptation_suggested: null,
        proposed_care_type: null,
      },
      "fr",
    );
    expect(pending.status).toBe("pending");
    expect(pending.icon).toBe("ic-clock");
    expect(pending.label).toBe("À discuter en RCP");
  });

  it("derives completeness status and missing count", () => {
    const incomplete = deriveCompletenessInfo(
      {
        is_complete: false,
        missing_count: 2,
        missing_items: ["TEP-TDM", "CR anapath"],
      },
      "fr",
    );
    expect(incomplete.status).toBe("incomplete");
    expect(incomplete.icon).toBe("ic-warning");
    expect(incomplete.label).toBe("2 manquantes");

    const complete = deriveCompletenessInfo(
      {
        is_complete: true,
        missing_count: 0,
      },
      "fr",
    );
    expect(complete.status).toBe("complete");
    expect(complete.icon).toBe("ic-check-circle");
    expect(complete.label).toBe("Dossier complet");

    const pendingAi = deriveCompletenessInfo(
      {
        is_complete: true,
        missing_count: 0,
        processing_status: "PENDING_CLINICAL",
      },
      "fr",
    );
    expect(pendingAi.status).toBe("incomplete");
    expect(pendingAi.icon).toBe("ic-clock");
    expect(pendingAi.label).toBe("En attente IA");

    const notEvaluated = deriveCompletenessInfo(
      {
        is_complete: false,
        missing_count: 0,
      },
      "fr",
    );
    expect(notEvaluated.status).toBe("incomplete");
    expect(notEvaluated.icon).toBe("ic-clock");
    expect(notEvaluated.label).toBe("En attente IA");
  });

  it("computes the 4 M3 KPIs and filters/sorts worklist cards by priority then date", () => {
    const cards: MdtFormCard[] = [
      {
        id: "S-0007",
        file: "sma_leo.pdf",
        patientId: "S-0007",
        patientName: "EXEMPLE Léo",
        firstName: "Léo",
        lastName: "EXEMPLE",
        domain: "sma",
        mdtDate: "2026-11-12",
        priorityLevel: "low",
        isComplete: true,
        missingCount: 0,
        missingItems: [],
        careAdaptationSuggested: false,
        proposedCareType: null,
        specialties: ["neurologist expert", "pulmonologist expert"],
        processingStatus: "COMPLETED",
        processingStep: null,
        processingProgressPct: 100,
        rcpCount: 2,
        summaryText: "SMA type 2 stable sous nusinersen",
      },
      {
        id: "A-1042",
        file: "fictive_jeanne.pdf",
        patientId: "A-1042",
        patientName: "FICTIVE Jeanne",
        firstName: "Jeanne",
        lastName: "FICTIVE",
        domain: "oncology",
        mdtDate: "2026-11-06",
        priorityLevel: "high",
        isComplete: false,
        missingCount: 2,
        missingItems: ["TEP-TDM", "CR anatomopathologique"],
        careAdaptationSuggested: true,
        proposedCareType: "Chimiothérapie 2e ligne",
        specialties: ["pancreas expert", "Radiotherapy"],
        processingStatus: "COMPLETED",
        processingStep: null,
        processingProgressPct: 100,
        rcpCount: 3,
        summaryText: "Adénocarcinome pancréatique cT3N1M0",
      },
    ];

    const kpis = computeWorklistKpis(cards);
    expect(kpis).toEqual({
      structuredCount: 2,
      highPriorityCount: 1,
      incompleteCount: 1,
      adaptationSuggestedCount: 1,
    });

    const sorted = filterAndSortCards(cards, {});
    expect(sorted.map((c) => c.id)).toEqual(["A-1042", "S-0007"]);

    const incompleteOnly = filterAndSortCards(cards, {
      completeness: "incomplete",
    });
    expect(incompleteOnly).toHaveLength(1);
    expect(incompleteOnly[0]?.id).toBe("A-1042");

    const searched = filterAndSortCards(cards, { query: "nusinersen" });
    expect(searched).toHaveLength(1);
    expect(searched[0]?.id).toBe("S-0007");
  });

  it("computes longitudinal deltas between consecutive RCP forms", () => {
    const prevForm: MdtFormDetail = {
      file: "jeanne_2026_10_14.pdf",
      patientId: "A-1042",
      domain: "oncology",
      mdtDate: "2026-10-14",
      processingStatus: "COMPLETED",
      processingStep: null,
      processingProgressPct: 100,
      sections: {
        PatientPerformanceStatus: { performance_status: 1 },
        TumorLocation: { tumor_location: "Pancreas" },
        TumorBiology: { msi_state: "MSS" },
      },
      manualEdits: {},
      executionTimes: {},
      metrics: {
        priority_level: "medium",
        is_complete: true,
        missing_count: 0,
        care_adaptation_suggested: false,
      },
    };

    const currentForm: MdtFormDetail = {
      file: "jeanne_2026_11_06.pdf",
      patientId: "A-1042",
      domain: "oncology",
      mdtDate: "2026-11-06",
      processingStatus: "COMPLETED",
      processingStep: null,
      processingProgressPct: 100,
      sections: {
        PatientPerformanceStatus: { performance_status: 2 },
        TumorLocation: { tumor_location: "Pancreas" },
        TumorBiology: { msi_state: "MSS" },
      },
      manualEdits: {},
      executionTimes: {},
      metrics: {
        priority_level: "high",
        is_complete: false,
        missing_count: 2,
        care_adaptation_suggested: true,
      },
    };

    const deltas = computeLongitudinalDeltas(currentForm, prevForm, "fr");
    const omsDelta = deltas.find((d) => d.key === "performance_status");
    expect(omsDelta).toBeDefined();
    expect(omsDelta?.direction).toBe("worse");
    expect(omsDelta?.icon).toBe("ic-trend-up");
  });
});

describe("Domain Catalog & i18n (FR / EN)", () => {
  it("maps oncology and SMA sections to Material Design 3 SVG icon IDs and clinical poles", () => {
    const loc = getSectionPresentation("TumorLocation", "oncology", "fr");
    expect(loc.icon).toBe("ic-microscope");
    expect(loc.title).toContain("Localisation");

    const gen = getSectionPresentation("GeneticDiagnosis", "sma", "fr");
    expect(gen.icon).toBe("ic-dna");
    expect(gen.title).toContain("Diagnostic génétique");

    const agent = getAgentPresentation("pancreas expert", "fr");
    expect(agent.icon).toBe("ic-stethoscope");
    expect(agent.label).toBe("Oncologie digestive — Pancréas");

    const adminAgent = getAgentPresentation("Administrative", "fr");
    expect(adminAgent.icon).toBe("ic-folder");
    expect(adminAgent.label).toBe("Extraction administrative & clinique");
  });

  it("translates LLM fallback strings and clinical labels in FR and EN", () => {
    expect(translateValue("Not documented in record", "fr")).toBe("Non renseigné");
    expect(translateValue("Pancreas", "fr")).toBe("Pancréas");
    expect(formatFieldLabel("smn2_copy_count", "fr")).toBe("Nombre de copies SMN2");
    expect(t("nav.worklist", "fr")).toBe("Worklist RCP");
    expect(t("nav.worklist", "en")).toBe("MDT Worklist");
  });

  it("dynamically parses Pydantic v2 JSON schemas distributed by the API and enforces strict field types", () => {
    const smaSchema = buildDefaultDomainFormSchema("sma");
    const motorFields = getSectionFieldSchemas("MotorFunctionStatus", smaSchema);
    const hfmseField = motorFields.find((f) => f.key === "hfmse_score");
    expect(hfmseField?.inputType).toBe("integer");
    expect(hfmseField?.min).toBe(0);
    expect(hfmseField?.max).toBe(66);
    expect(hfmseField?.nullable).toBe(true);

    const parsedFromRawPydantic = parseJsonSchemaToFieldSchemas("RespiratoryFunction", {
      type: "object",
      required: ["non_invasive_ventilation"],
      properties: {
        non_invasive_ventilation: { type: "boolean", default: false },
        daily_ventilation_hours: {
          anyOf: [{ type: "integer", minimum: 0, maximum: 24 }, { type: "null" }],
          default: null,
        },
        forced_vital_capacity_percent: {
          anyOf: [{ type: "number", minimum: 0, maximum: 150 }, { type: "null" }],
          default: null,
        },
        cough_assist_used: { type: "boolean", default: false },
      },
    });
    expect(parsedFromRawPydantic.map((f) => `${f.key}:${f.inputType}`)).toEqual([
      "non_invasive_ventilation:boolean",
      "daily_ventilation_hours:integer",
      "forced_vital_capacity_percent:float",
      "cough_assist_used:boolean",
    ]);

    // Coerce SMA MotorFunctionStatus with strings, numbers, and "Non renseigné"
    const coercedMotor = coerceSectionUpdatePayload(
      "MotorFunctionStatus",
      {
        best_motor_function: "Assis sans appui (Sitter)",
        hfmse_score: "44",
        chop_intend_score: "Non renseigné",
        rulm_score: "999", // clamped to max=37
        motor_milestones: "Station assise autonome\nPropulsion fauteuil",
        physiotherapy_frequency: "3 séances / semaine",
      },
      {},
      smaSchema,
    );
    expect(coercedMotor.hfmse_score).toBe(44);
    expect(coercedMotor.chop_intend_score).toBeNull();
    expect(coercedMotor.rulm_score).toBe(37);
    expect(coercedMotor.motor_milestones).toEqual([
      "Station assise autonome",
      "Propulsion fauteuil",
    ]);

    // Coerce Oncology TumorBiology with nullable boolean msi_state
    const oncoSchema = buildDefaultDomainFormSchema("oncology");
    const coercedBio = coerceSectionUpdatePayload(
      "TumorBiology",
      {
        histology_type: "Adénocarcinome",
        grade: "G2",
        biomarkers: "KRAS G12D",
        msi_state: "false",
      },
      {},
      oncoSchema,
    );
    expect(coercedBio.msi_state).toBe(false);
  });

  it("coerces primitive values, dates, selects, lists, exams, chemo, and strict payloads", () => {
    expect(isPlaceholderValue(null)).toBe(true);
    expect(isPlaceholderValue("Non renseigné")).toBe(true);
    expect(isPlaceholderValue("FOLFIRINOX")).toBe(false);
    expect(isPlaceholderValue(42)).toBe(false);

    expect(coerceBooleanValue(true)).toBe(true);
    expect(coerceBooleanValue(1)).toBe(true);
    expect(coerceBooleanValue(0)).toBe(false);
    expect(coerceBooleanValue("oui")).toBe(true);
    expect(coerceBooleanValue("non")).toBe(false);
    expect(coerceBooleanValue("unknown", true)).toBe(true);

    expect(coerceNullableBooleanValue(null)).toBeNull();
    expect(coerceNullableBooleanValue(true)).toBe(true);
    expect(coerceNullableBooleanValue("MSI")).toBe(true);
    expect(coerceNullableBooleanValue("MSS")).toBe(false);
    expect(coerceNullableBooleanValue("non renseigné")).toBeNull();
    expect(coerceNullableBooleanValue("maybe")).toBeNull();

    expect(coerceNumberValue(null, true)).toBeNull();
    expect(coerceNumberValue(Number.NaN, true)).toBeNull();
    expect(coerceNumberValue(3.7, true, 0, 2)).toBe(2);
    expect(coerceNumberValue(-5, false, 0, 10)).toBe(0);
    expect(coerceNumberValue("72,5 %", false, 0, 100)).toBe(72.5);
    expect(coerceNumberValue("OMS 2", true, 0, 4)).toBe(2);
    expect(coerceNumberValue("abc", true)).toBeNull();

    expect(coerceDateValue(null)).toBeNull();
    expect(coerceDateValue(new Date("2026-05-14T10:00:00Z"))).toBe("2026-05-14");
    expect(coerceDateValue("2026-11-06T08:00:00")).toBe("2026-11-06");
    expect(coerceDateValue("14/05/2026")).toBe("2026-05-14");
    expect(coerceDateValue("May 14, 2026")).toMatch(/^2026-05-1[34]$/);
    expect(coerceDateValue("invalid-date")).toBeNull();

    const options = [
      { value: "NIV_BiPAP", labelFr: "VNI nocturne", labelEn: "Nocturnal NIV" },
      { value: "Gastrostomy", labelFr: "Gastrostomie", labelEn: "G-tube" },
      { value: "Underweight", labelFr: "Maigreur", labelEn: "Underweight" },
    ];
    expect(coerceSelectValue(null, options, "NIV_BiPAP")).toBe("NIV_BiPAP");
    expect(coerceSelectValue("VNI nocturne", options, "None")).toBe("NIV_BiPAP");
    expect(coerceSelectValue("bipap 8h", options, "None")).toBe("NIV_BiPAP");
    expect(coerceSelectValue("pose de gpe", options, "None")).toBe("Gastrostomy");
    expect(coerceSelectValue("cassure pondérale", options, "None")).toBe("Underweight");
    expect(coerceSelectValue("other", options, "Fallback")).toBe("Fallback");

    expect(coerceStringListValue(["A", "Non renseigné", " B "])).toEqual(["A", "B"]);
    expect(coerceStringListValue("TEP-TDM, IRM hépatique; Non renseigné")).toEqual([
      "TEP-TDM",
      "IRM hépatique",
    ]);
    expect(coerceStringListValue(123)).toEqual([]);

    expect(formatRawEditValue(null)).toBe("");
    expect(formatRawEditValue(true, { key: "k", inputType: "boolean", nullable: false })).toBe(
      "true",
    );
    expect(
      formatRawEditValue(null, { key: "k", inputType: "nullable_boolean", nullable: true }),
    ).toBe("");
    expect(
      formatRawEditValue(false, { key: "k", inputType: "nullable_boolean", nullable: true }),
    ).toBe("false");
    expect(
      formatRawEditValue(["A", "B"], { key: "k", inputType: "string_list", nullable: false }),
    ).toBe("A, B");
    expect(
      formatRawEditValue("A, B", { key: "k", inputType: "string_list", nullable: false }),
    ).toBe("A, B");
    expect(formatRawEditValue("14/05/2026", { key: "k", inputType: "date", nullable: true })).toBe(
      "2026-05-14",
    );
    expect(
      formatRawEditValue("invalid", {
        key: "k",
        inputType: "integer",
        nullable: false,
        defaultValue: 0,
      }),
    ).toBe("0");
    expect(
      formatRawEditValue("invalid", {
        key: "k",
        inputType: "float",
        nullable: false,
        defaultValue: 0,
      }),
    ).toBe("0");
    expect(
      formatRawEditValue("12,5", {
        key: "k",
        inputType: "float",
        nullable: true,
      }),
    ).toBe("12.5");
    expect(
      formatRawEditValue("VNI nocturne", {
        key: "k",
        inputType: "select",
        nullable: false,
        options,
        defaultValue: "NIV_BiPAP",
      }),
    ).toBe("NIV_BiPAP");
    expect(formatRawEditValue(42)).toBe("42");

    // Exams & Chemo normalization
    const exams = extractNormalizedExamsList({
      radiological_exams: [
        {
          exam_name: "IRM hépatique",
          exam_type: "IRM",
          exam_date: "14/05/2026",
          exam_result: "RAS",
        },
        { exam_name: "TEP-FDG", exam_type: "TEP", exam_result: "Non renseigné" },
        { exam_name: "Echo-endo", exam_type: "ECHO", exam_result: "T3N1" },
      ],
    });
    expect(exams).toHaveLength(3);
    expect(exams[0]?.exam_type).toBe("MRI");
    expect(exams[1]?.exam_type).toBe("PET");
    expect(exams[2]?.exam_type).toBe("EUS");

    const chemo = extractNormalizedChemoList({
      chemotherapy_name: "FOLFIRINOX",
      chemotherapy_start_date: "2026-01-10",
      chemotherapy_tolerance: "Grade 3 neuropathie",
    });
    expect(chemo).toHaveLength(1);
    expect(chemo[0]?.chemotherapy_tolerance).toBe("Poor");

    // MTDCompleted, RadiologicExams, ChemotherapyTreament, PatientAdministrative
    const mtdCoerced = coerceSectionUpdatePayload(
      "MTDCompleted",
      { what_missing: "TEP-TDM, Bilan hépatique", reflection: "Attente TEP" },
      { mtd_complete: { references: [{ name: "TNCD" }] } },
    );
    expect(mtdCoerced.is_mtd_complete).toBe(false);
    expect(buildStrictBackendSectionPayload("MTDCompleted", mtdCoerced)).toHaveProperty(
      "mtd_complete",
    );

    const radCoerced = coerceSectionUpdatePayload("RadiologicExams", {
      exam_name_0: "TDM TAP",
      exam_type_0: "CT",
      exam_date_0: "2026-10-01",
      exam_result_0: "Stable",
    });
    expect(buildStrictBackendSectionPayload("RadiologicExams", radCoerced)).toEqual({
      exams_list: [
        {
          exam_name: "TDM TAP",
          exam_date: "2026-10-01",
          exam_type: "CT",
          exam_result: "Stable",
        },
      ],
    });

    const chemoCoerced = coerceSectionUpdatePayload("ChemotherapyTreament", {
      chemotherapy_name_0: "Gemcitabine",
      chemotherapy_tolerance_0: "Bonne tolérance",
      chemotherapy_start_date_0: "2026-02-01",
    });
    expect(buildStrictBackendSectionPayload("ChemotherapyTreament", chemoCoerced)).toMatchObject({
      chemotherapy: true,
      chemotherapy_list: [
        expect.objectContaining({
          chemotherapy_name: "Gemcitabine",
          chemotherapy_tolerance: "Good",
        }),
      ],
    });

    const adminCoerced = coerceSectionUpdatePayload("PatientAdministrative", {
      first_name: "Jeanne",
      last_name: "Fictive",
      date_birth: "2027-01-01",
      date_rcp: "2026-11-06",
      extra_field: "extra",
    });
    expect(adminCoerced.date_birth).toBe("2026-11-06");
    expect(adminCoerced.extra_field).toBe("extra");
    const strictAdmin = buildStrictBackendSectionPayload("PatientAdministrative", adminCoerced);
    expect(strictAdmin).not.toHaveProperty("extra_field");
  });

  it("supports raw non-integer RULM/HFMSE observations, multi-year series, and obsolescence detection", () => {
    const smaSchema = buildDefaultDomainFormSchema("sma");
    const coercedRatio = coerceSectionUpdatePayload(
      "MotorFunctionStatus",
      {
        best_motor_function: "Sitter",
        rulm_score: "34/37",
        hfmse_score: "31.5",
        chop_intend_score: "Non testable (fatigue)",
      },
      {},
      smaSchema,
    );
    expect(coercedRatio.rulm_score).toBe("34/37");
    expect(coercedRatio.hfmse_score).toBe(31.5);
    expect(coercedRatio.chop_intend_score).toBe("Non testable (fatigue)");

    const rulmSpec = SMA_METRIC_SPECS[0]!;
    const obsRatio = parseRawMetricObservation("34/37", rulmSpec);
    expect(obsRatio.numericValue).toBe(34);
    expect(obsRatio.displayValue).toBe("34/37");

    const obsBilateral = parseRawMetricObservation("28 (D) / 30 (G)", rulmSpec);
    expect(obsBilateral.numericValue).toBe(29);
    expect(obsBilateral.subValues).toEqual({ D: 28, G: 30 });

    const obsAnnot = parseRawMetricObservation("Non testable (douleur épaule)", rulmSpec);
    expect(obsAnnot.numericValue).toBeNull();
    expect(obsAnnot.isAnnotativeOnly).toBe(true);

    const smaForms: MdtFormDetail[] = [
      {
        file: "sma_2022_03_10.pdf",
        patientId: "S-0007",
        domain: "sma",
        mdtDate: "2022-03-10",
        processingStatus: "COMPLETED",
        processingStep: null,
        processingProgressPct: 100,
        sections: {
          PatientAdministrative: {
            first_name: "Léo",
            last_name: "Test",
            date_rcp: "2022-03-10",
          },
          MotorFunctionStatus: {
            rulm_score: "28 (D) / 30 (G)",
            hfmse_score: 40,
            best_motor_function: "Assis sans appui (Sitter)",
          },
        },
        manualEdits: {},
        executionTimes: {},
        metrics: {},
      },
      {
        file: "sma_2026_11_05.pdf",
        patientId: "S-0007",
        domain: "sma",
        mdtDate: "2026-11-05",
        processingStatus: "COMPLETED",
        processingStep: null,
        processingProgressPct: 100,
        sections: {
          PatientAdministrative: {
            first_name: "Léo",
            last_name: "Test",
            date_rcp: "2026-11-05",
          },
          MotorFunctionStatus: {
            rulm_score: "34/37",
            hfmse_score: 46.5,
            best_motor_function: "Assis sans appui (Sitter)",
          },
        },
        manualEdits: {
          MotorFunctionStatus: { edited_by: "Dr. Martin", edited_at: "2026-11-05T10:00:00Z" },
        },
        executionTimes: {},
        metrics: {},
      },
    ];

    const summary2022 = synthesizePatientSummaryFromForms("Léo Test", smaForms.slice(0, 1), "sma");
    const evaluatedObsolete = evaluatePatientSummaryObsolescence(summary2022, smaForms);
    expect(evaluatedObsolete.isObsolete).toBe(true);
    expect(evaluatedObsolete.newFormsSinceSummary).toEqual(["sma_2026_11_05.pdf"]);

    const dashboard = buildPatientDashboardFromForms(
      "S-0007",
      "Léo Test",
      "sma",
      smaForms,
      summary2022,
    );
    const rulmSeries = dashboard.metrics.find(
      (m) => m.metricKey === "MotorFunctionStatus.rulm_score",
    );
    expect(rulmSeries).toBeDefined();
    expect(rulmSeries?.points).toHaveLength(2);
    expect(rulmSeries?.points[0]?.displayValue).toBe("28 (D) / 30 (G)");
    expect(rulmSeries?.points[1]?.displayValue).toBe("34/37");
    expect(rulmSeries?.points[1]?.isManual).toBe(true);
    expect(rulmSeries?.points[1]?.daysSinceFirstRcp).toBeGreaterThan(1500);
  });

  it("extracts oncology longitudinal metric series across CancerDescription, TumorBiology, SurgicalStatus, NutritionalStatus, and HepaticStatus", () => {
    const oncoForms: MdtFormDetail[] = [
      {
        file: "onco_2026_01_15.pdf",
        patientId: "O-101",
        domain: "oncology",
        mdtDate: "2026-01-15",
        processingStatus: "COMPLETED",
        processingStep: null,
        processingProgressPct: 100,
        sections: {
          PatientAdministrative: {
            first_name: "Jean",
            last_name: "DUPONT",
            date_rcp: "2026-01-15",
          },
          TumorLocation: { tumor_location: "Pancreas" },
          CancerDescription: {
            type_of_cancer: "Adénocarcinome canalaire pancréatique",
            tnm_status: "cT3N1M0",
            target_lesion_size_mm: 36.0,
            recist_response: "Baseline",
          },
          TumorBiology: {
            msi_state: false,
            ca19_9: 1450.0,
            ace: 14.2,
            dpd_uracilemia: 9.5,
          },
          SurgicalStatus: {
            resectability_status: "Borderline",
            surgery_done: false,
          },
          NutritionalStatus: {
            weight_kg: 68.0,
            weight_loss_percent: 11.5,
            bmi: 22.1,
          },
          HepaticStatus: {
            bilirubin_umol_l: 85.0,
            child_pugh_score: "A6",
          },
          PatientPerformanceStatus: { performance_status: 1 },
          ChemotherapyTreament: {
            chemotherapy: true,
            chemotherapy_list: [
              {
                chemotherapy_name: "FOLFIRINOX",
                chemotherapy_tolerance: "Good",
              },
            ],
          },
        },
        manualEdits: {},
        executionTimes: {},
        metrics: {},
      },
      {
        file: "onco_2026_05_15.pdf",
        patientId: "O-101",
        domain: "oncology",
        mdtDate: "2026-05-15",
        processingStatus: "COMPLETED",
        processingStep: null,
        processingProgressPct: 100,
        sections: {
          PatientAdministrative: {
            first_name: "Jean",
            last_name: "DUPONT",
            date_rcp: "2026-05-15",
          },
          TumorLocation: { tumor_location: "Pancreas" },
          CancerDescription: {
            type_of_cancer: "Adénocarcinome canalaire pancréatique",
            tnm_status: "ypT2N0M0",
            target_lesion_size_mm: 21.0,
            recist_response: "PR",
          },
          TumorBiology: {
            msi_state: false,
            ca19_9: 185.0,
            ace: 4.1,
            dpd_uracilemia: 9.5,
          },
          SurgicalStatus: {
            resectability_status: "Resectable",
            surgery_done: true,
            resection_margin: "R0",
          },
          NutritionalStatus: {
            weight_kg: 71.5,
            weight_loss_percent: 3.0,
            bmi: 23.2,
          },
          HepaticStatus: {
            bilirubin_umol_l: 14.0,
            child_pugh_score: "A5",
          },
          PatientPerformanceStatus: { performance_status: 0 },
          ChemotherapyTreament: {
            chemotherapy: true,
            chemotherapy_list: [
              {
                chemotherapy_name: "FOLFIRINOX",
                chemotherapy_tolerance: "Good",
              },
            ],
          },
        },
        manualEdits: {},
        executionTimes: {},
        metrics: {},
      },
    ];

    const dashboard = buildPatientDashboardFromForms(
      "O-101",
      "Jean DUPONT",
      "oncology",
      oncoForms,
      null,
    );
    const byKey = new Map(dashboard.metrics.map((m) => [m.metricKey, m]));

    expect(byKey.get("TumorBiology.ca19_9")?.points.map((p) => p.numericValue)).toEqual([
      1450.0, 185.0,
    ]);
    expect(
      byKey.get("CancerDescription.target_lesion_size_mm")?.points.map((p) => p.numericValue),
    ).toEqual([36.0, 21.0]);
    expect(
      byKey.get("CancerDescription.recist_response")?.points.map((p) => p.displayValue),
    ).toEqual(["Baseline", "PR"]);
    expect(
      byKey.get("SurgicalStatus.resectability_status")?.points.map((p) => p.displayValue),
    ).toEqual(["Borderline (limite)", "Résécable"]);
    expect(byKey.get("SurgicalStatus.resection_margin")?.points.map((p) => p.displayValue)).toEqual(
      ["R0"],
    );
    expect(byKey.get("NutritionalStatus.weight_kg")?.points.map((p) => p.numericValue)).toEqual([
      68.0, 71.5,
    ]);
    expect(byKey.get("HepaticStatus.bilirubin_umol_l")?.points.map((p) => p.numericValue)).toEqual([
      85.0, 14.0,
    ]);
    expect(byKey.get("Chemotherapy.chemotherapy_name")?.points.map((p) => p.displayValue)).toEqual([
      "FOLFIRINOX",
      "FOLFIRINOX",
    ]);
  });

  it("renders patient dashboard panel and ECharts SSR SVG across FR/EN, summary states, bilateral series, and qualitative swimlanes", () => {
    // 1. Empty metrics + queued AI job in English
    const emptyEnHtml = renderPatientDashboardPanel(
      {
        patientId: "P-EMPTY",
        patientName: "Alice Martin",
        domain: "sma",
        latestFile: null,
        rcpCount: 0,
        metrics: [],
        summary: {
          hasSummary: false,
          isObsolete: false,
          obsoleteReasons: [],
          newFormsSinceSummary: [],
          modifiedFormsSinceSummary: [],
          removedFormsSinceSummary: [],
          generatedAt: null,
          coveredFormIds: [],
          latestFormIdAtGeneration: null,
          latestFormDateAtGeneration: null,
          modelUsed: null,
          content: null,
          activeJob: {
            job_id: "J-99",
            status: "RUNNING",
            current_step: null,
          },
        },
      },
      "en",
    );
    expect(emptyEnHtml).toContain("No raw longitudinal metrics found");
    expect(emptyEnHtml).toContain("Queued in AI Worker");
    expect(emptyEnHtml).toContain("Task queued in AI PriorityQueue");
    expect(emptyEnHtml).toContain("Longitudinal synthesis waiting for AI worker");
    expect(emptyEnHtml).toContain("Generating in AI queue");

    // 2. Full dashboard with obsolete summary (new forms + modified forms), bilateral D/G, manual edits, annotative-only points, multi-year span, and qualitative step changes in FR & EN
    const richDashboard = {
      patientId: "P-RICH",
      patientName: "Lucas Bernard",
      domain: "sma" as const,
      latestFile: "f3.pdf",
      rcpCount: 3,
      metrics: [
        {
          metricKey: "OrthopedicStatus.cobb_angle",
          section: "OrthopedicStatus",
          field: "cobb_angle",
          label: "OrthopedicStatus.cobb_angle",
          unit: "°",
          valueType: "numeric_or_mixed" as const,
          polarity: "lower_is_better" as const,
          scaleMin: 0,
          scaleMax: 90,
          points: [
            {
              formId: "f1.pdf",
              formDate: "2024-01-10",
              formDateLabel: "2024-01-10",
              daysSinceFirstRcp: 0,
              xRatio: 0,
              rawValue: "D: 18°, G: 14°",
              displayValue: "D: 18°, G: 14°",
              numericValue: 18,
              subValues: { D: 18, G: 14 },
              isManual: false,
              editedBy: null,
              editedAt: null,
              deltaNumeric: null,
              deltaDisplay: null,
              isAnnotativeOnly: false,
            },
            {
              formId: "f2.pdf",
              formDate: "2025-06-15",
              formDateLabel: "",
              daysSinceFirstRcp: 522,
              xRatio: 0.5,
              rawValue: "D: 22°, G: 19°",
              displayValue: "22",
              numericValue: 22,
              subValues: { D: 22, G: 19 },
              isManual: true,
              editedBy: "Dr. Martin",
              editedAt: "2025-06-16T10:00:00Z",
              deltaNumeric: 4,
              deltaDisplay: "+4",
              isAnnotativeOnly: false,
            },
            {
              formId: "f3.pdf",
              formDate: null,
              formDateLabel: "Date non renseignée",
              daysSinceFirstRcp: 0,
              xRatio: 1,
              rawValue: "Corset Garchois porté",
              displayValue: "Corset Garchois porté",
              numericValue: null,
              subValues: null,
              isManual: false,
              editedBy: null,
              editedAt: null,
              deltaNumeric: null,
              deltaDisplay: null,
              isAnnotativeOnly: true,
            },
          ],
        },
        {
          metricKey: "MotorFunctionStatus.hfmse_score",
          section: "MotorFunctionStatus",
          field: "hfmse_score",
          label: "Score HFMSE",
          unit: "/66",
          valueType: "numeric_or_mixed" as const,
          polarity: "higher_is_better" as const,
          scaleMin: null,
          scaleMax: null,
          points: [
            {
              formId: "f1.pdf",
              formDate: "2026-01-10",
              formDateLabel: "2026-01-10",
              daysSinceFirstRcp: 0,
              xRatio: 0,
              rawValue: 40,
              displayValue: "40/66",
              numericValue: 40,
              subValues: null,
              isManual: false,
              editedBy: null,
              editedAt: null,
              deltaNumeric: null,
              deltaDisplay: null,
              isAnnotativeOnly: false,
            },
            {
              formId: "f2.pdf",
              formDate: "2026-02-10",
              formDateLabel: "2026-02-10",
              daysSinceFirstRcp: 31,
              xRatio: 1,
              rawValue: 42,
              displayValue: "42/66",
              numericValue: 42,
              subValues: null,
              isManual: false,
              editedBy: null,
              editedAt: null,
              deltaNumeric: 2,
              deltaDisplay: "+2",
              isAnnotativeOnly: false,
            },
          ],
        },
        {
          metricKey: "MotorFunctionStatus.current_motor_milestone",
          section: "MotorFunctionStatus",
          field: "current_motor_milestone",
          label: "Statut moteur actuel",
          unit: "",
          valueType: "categorical" as const,
          polarity: "neutral" as const,
          scaleMin: null,
          scaleMax: null,
          points: [
            {
              formId: "f1.pdf",
              formDate: "2024-01-10",
              formDateLabel: "2024-01-10",
              daysSinceFirstRcp: 0,
              xRatio: 0,
              rawValue: ["Sitter", "Assisted standing"],
              displayValue: "Sitter, Assisted standing",
              numericValue: null,
              subValues: null,
              isManual: false,
              editedBy: null,
              editedAt: null,
              deltaNumeric: null,
              deltaDisplay: null,
              isAnnotativeOnly: false,
            },
            {
              formId: "f2.pdf",
              formDate: "2025-06-15",
              formDateLabel: "2025-06-15",
              daysSinceFirstRcp: 522,
              xRatio: 1,
              rawValue: "",
              displayValue: "Non-sitter",
              numericValue: null,
              subValues: null,
              isManual: true,
              editedBy: "Dr. Martin",
              editedAt: "2025-06-16T10:00:00Z",
              deltaNumeric: null,
              deltaDisplay: "Assis sans appui → Non-assis",
              isAnnotativeOnly: false,
            },
          ],
        },
      ],
      summary: {
        hasSummary: true,
        isObsolete: true,
        obsoleteReasons: ["1 nouvelle séance RCP"],
        newFormsSinceSummary: ["f3.pdf"],
        modifiedFormsSinceSummary: ["f2.pdf"],
        removedFormsSinceSummary: [],
        generatedAt: "2026-06-15T14:30:00Z",
        coveredFormIds: ["f1.pdf", "f2.pdf"],
        latestFormIdAtGeneration: "f2.pdf",
        latestFormDateAtGeneration: "2025-06-15",
        modelUsed: "mistral-nemo",
        content: {
          clinicalTrajectoryOverview: "Suivi longitudinal SMA sur 3 séances.",
          diseaseAndTreatmentEvolution: "Stabilisation sous Risdiplam.",
          notableMetricChanges: ["HFMSE : 40 → 42 (+2)"],
          unresolvedVigilancePoints: ["EFR à contrôler"],
          mdtDecisionsRecap: ["2025-06-15 : Poursuite Risdiplam"],
          sourcesUsed: ["f1.pdf", "f2.pdf"],
        },
        activeJob: null,
      },
    };

    const frHtml = renderPatientDashboardPanel(richDashboard, "fr");
    expect(frHtml).toContain("Résumé global obsolète");
    expect(frHtml).toContain("1 nouvelle(s) séance(s) RCP");
    expect(frHtml).toContain("Suivi longitudinal SMA sur 3 séances.");
    expect(frHtml).toContain("HFMSE : 40 → 42 (+2)");
    expect(frHtml).toContain("EFR à contrôler");
    expect(frHtml).toContain("2025-06-15 : Poursuite Risdiplam");
    expect(frHtml).toContain("<svg");
    expect(frHtml).toContain("D: 18°, G: 14°");

    // Test EN rendering with up-to-date summary and modified-only obsolete branch
    const enHtml = renderPatientDashboardPanel(
      {
        ...richDashboard,
        summary: {
          ...richDashboard.summary,
          isObsolete: true,
          newFormsSinceSummary: [],
          generatedAt: "invalid-date-format",
        },
      },
      "en",
    );
    expect(enHtml).toContain("One or more MDT sessions were updated since invalid-date-format.");
    expect(enHtml).toContain("<svg");

    const upToDateEnHtml = renderPatientDashboardPanel(
      {
        ...richDashboard,
        metrics: [
          richDashboard.metrics[0]!.points[0]
            ? { ...richDashboard.metrics[0]!, points: [richDashboard.metrics[0]!.points[0]!] }
            : richDashboard.metrics[0]!,
        ],
        summary: {
          ...richDashboard.summary,
          isObsolete: false,
          generatedAt: "2026-06-15T14:30:00Z",
        },
      },
      "en",
    );
    expect(upToDateEnHtml).toContain("Up to date");
    expect(upToDateEnHtml).toContain("Regenerate global summary");
    expect(upToDateEnHtml).toContain("1 session");
  });
});
