import { describe, expect, it } from "vitest";
import {
  formatFieldLabel,
  getAgentPresentation,
  getSectionPresentation,
} from "../../src/domain/catalog.js";
import { t, translateValue } from "../../src/domain/i18n.js";
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

    const incompleteOnly = filterAndSortCards(cards, { completeness: "incomplete" });
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
    expect(agent.label).toBe("Pancréas");
  });

  it("translates LLM fallback strings and clinical labels in FR and EN", () => {
    expect(translateValue("Not documented in record", "fr")).toBe("Non renseigné");
    expect(translateValue("Pancreas", "fr")).toBe("Pancréas");
    expect(formatFieldLabel("smn2_copy_count", "fr")).toBe("Nombre de copies SMN2");
    expect(t("nav.worklist", "fr")).toBe("Worklist RCP");
    expect(t("nav.worklist", "en")).toBe("MDT Worklist");
  });
});
