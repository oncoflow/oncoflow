import { CLINICAL_TRANSLATIONS_FR, translateValue } from "./i18n.js";
import type { AgentUserPromptItem, ClinicalDomain, Language } from "./types.js";

export interface SectionPresentationMeta {
  name: string;
  title: string;
  icon: string;
  pole: "identity" | "clinical" | "paraclinical" | "treatments" | "synthesis";
  poleLabel: string;
  tab: "clinical" | "opinions";
  editable: boolean;
  order: number;
  userPrompt: string;
}

interface CatalogEntry {
  icon: string;
  pole: SectionPresentationMeta["pole"];
  tab: SectionPresentationMeta["tab"];
  editable: boolean;
  order: number;
  titleFr: string;
  titleEn: string;
  userPromptOncology?: string;
  userPromptSma?: string;
  defaultUserPrompt: string;
  domains?: ClinicalDomain[];
}

const SECTION_CATALOG: Record<string, CatalogEntry> = {
  CareOrientationProposal: {
    icon: "ic-compass",
    pole: "synthesis",
    tab: "opinions",
    editable: false,
    order: 10,
    titleFr: "Proposition d'orientation pré-RCP",
    titleEn: "Pre-MDT Care Orientation Proposal",
    defaultUserPrompt:
      "Based on the multidisciplinary expert debate, synthesize a pre-MDT orientation proposal to assist the medical board (do not replace the physicians' final decision): Determine if an initiation or adaptation of care should be discussed for this patient, specify the suggested priority level (suggested_priority), proposed care modality (proposed_care_type), and provide a clear clinical_rationale detailing expert positions and guideline references.",
    userPromptOncology:
      "Based on the multidisciplinary oncology expert debate, synthesize a pre-MDT orientation proposal to assist the medical board (do not replace the physicians' final decision): Determine if an initiation or adaptation of medical, surgical, or radiological care should be discussed for this patient. Specify suggested_priority, proposed_care_type, and clinical_rationale with TNCD references.",
    userPromptSma:
      "Based on the multidisciplinary SMA expert debate (neurologist, geneticist, pulmonologist, orthopedist, physiotherapist), synthesize a pre-MDT orientation proposal to assist the medical board: Determine if an initiation or adaptation of therapeutic, respiratory, nutritional, orthopedic, or rehabilitative care should be discussed for this SMA patient with PNDS references.",
  },
  MTDCompleted: {
    icon: "ic-warning",
    pole: "synthesis",
    tab: "opinions",
    editable: true,
    order: 20,
    titleFr: "Contrôle de complétude du dossier",
    titleEn: "Pre-MDT Completeness Check",
    defaultUserPrompt:
      "Analyze the expert opinions and clinical record to identify any missing examinations, biological markers, imaging, or administrative elements required before or during the MDT discussion.",
  },
  ExpertAnswer: {
    icon: "ic-scale",
    pole: "synthesis",
    tab: "opinions",
    editable: false,
    order: 30,
    titleFr: "Avis des experts & Référentiels",
    titleEn: "Specialty Expert Opinions & Guidelines",
    defaultUserPrompt:
      "As an expert in your field, determine if the patient requires urgent treatment. Assess if your expertise is relevant to this case, explain your reasoning, and provide therapeutic/diagnostic suggestions grounded in scientific guidelines.",
  },
  TumorLocation: {
    icon: "ic-microscope",
    pole: "clinical",
    tab: "clinical",
    editable: true,
    order: 40,
    titleFr: "Localisation de la tumeur primitive",
    titleEn: "Primary Tumor Location & Staging",
    defaultUserPrompt:
      "Identify the primary organ where the tumor is located. Search for the principal diagnosis or the primary tumor site.",
    domains: ["oncology"],
  },
  GeneticDiagnosis: {
    icon: "ic-dna",
    pole: "clinical",
    tab: "clinical",
    editable: true,
    order: 45,
    titleFr: "Diagnostic génétique (SMN1 / SMN2)",
    titleEn: "Genetic Diagnosis (SMN1 / SMN2)",
    defaultUserPrompt:
      "Extract molecular genetic testing results. Confirm if the SMN1 homozygous deletion is present and find the exact number of SMN2 copies (typically 1 to 5 copies).",
    domains: ["sma"],
  },
  TumorBiology: {
    icon: "ic-flask",
    pole: "clinical",
    tab: "clinical",
    editable: true,
    order: 50,
    titleFr: "Biologie tumorale (Statut MSI / MSS & Biomarqueurs)",
    titleEn: "Tumor Biology (MSI / MSS Status & Biomarkers)",
    defaultUserPrompt:
      "Is the tumor classified as MSI (Microsatellite Instability) or MSS (Microsatellite Stable)? Search for 'MSI', 'MSS', 'instabilité microsatellitaire', or 'statut MMR'. If not mentioned, state it.",
    domains: ["oncology"],
  },
  PatientPerformanceStatus: {
    icon: "ic-stethoscope",
    pole: "clinical",
    tab: "clinical",
    editable: true,
    order: 60,
    titleFr: "Statut de performance OMS / ECOG",
    titleEn: "WHO / ECOG Performance Status",
    defaultUserPrompt:
      "Determine the WHO performance status of the patient (0-4). Look for 'OMS', 'WHO', or 'Performance Status' in the document. If not found, indicate it.",
  },
  MotorFunctionStatus: {
    icon: "ic-brain",
    pole: "clinical",
    tab: "clinical",
    editable: true,
    order: 65,
    titleFr: "Classification clinique & scores moteurs (HFMSE / RULM / CHOP-INTEND)",
    titleEn: "Motor Function Status (HFMSE / RULM / CHOP-INTEND)",
    defaultUserPrompt:
      "Determine the SMA clinical type (1, 2, 3, or 4), list the patient's current motor milestones, and extract any standardized motor scale scores found in the clinical records (HFMSE, CHOP INTEND, RULM).",
    domains: ["sma"],
  },
  RespiratoryFunction: {
    icon: "ic-lungs",
    pole: "clinical",
    tab: "clinical",
    editable: true,
    order: 70,
    titleFr: "Fonction respiratoire & ventilation",
    titleEn: "Respiratory Function & Ventilation",
    defaultUserPrompt:
      "Extract respiratory evaluations: check if the patient uses ventilation support (NIV, tracheostomy) or a cough assist machine, and look for pulmonary function test values like FVC (CVF) percentage.",
    domains: ["sma"],
  },
  OrthopedicAndSpineStatus: {
    icon: "ic-stethoscope",
    pole: "clinical",
    tab: "clinical",
    editable: true,
    order: 75,
    titleFr: "Statut orthopédique & rachidien",
    titleEn: "Orthopedic & Spine Status",
    defaultUserPrompt:
      "Search for spine and orthopedic assessments. Check for scoliosis presence, the Cobb angle, history of spinal surgery, joints affected by contractures, and whether the patient is wheelchair-dependent.",
    domains: ["sma"],
  },
  BulbarAndNutritionalStatus: {
    icon: "ic-flask",
    pole: "clinical",
    tab: "clinical",
    editable: true,
    order: 80,
    titleFr: "Statut bulbaire & nutritionnel",
    titleEn: "Bulbar & Nutritional Status",
    defaultUserPrompt:
      "Extract information regarding bulbar function: presence of dysphagia, history of aspiration pneumonia, current feeding method (oral or tube feeding), and overall nutritional/weight monitoring.",
    domains: ["sma"],
  },
  RadiologicExams: {
    icon: "ic-radiation",
    pole: "paraclinical",
    tab: "clinical",
    editable: true,
    order: 90,
    titleFr: "Examens radiologiques & imagerie",
    titleEn: "Radiological Examinations",
    defaultUserPrompt:
      "List all radiological exams found in the documents. Include date, name, type, and a summary of results for each.",
  },
  RadiologicalExams: {
    icon: "ic-radiation",
    pole: "paraclinical",
    tab: "clinical",
    editable: true,
    order: 90,
    titleFr: "Examens radiologiques & imagerie",
    titleEn: "Radiological Examinations",
    defaultUserPrompt:
      "List all radiological exams found in the documents. Include date, name, type, and a summary of results for each.",
  },
  PreviousCurativeSurgery: {
    icon: "ic-pill",
    pole: "treatments",
    tab: "clinical",
    editable: true,
    order: 100,
    titleFr: "Chirurgie curative antérieure",
    titleEn: "Previous Curative Surgery",
    defaultUserPrompt:
      "Has a curative surgery already been performed for this tumor? If yes, provide the date.",
    domains: ["oncology"],
  },
  PreviousSurgery: {
    icon: "ic-pill",
    pole: "treatments",
    tab: "clinical",
    editable: true,
    order: 100,
    titleFr: "Chirurgie curative antérieure",
    titleEn: "Previous Curative Surgery",
    defaultUserPrompt:
      "Has a curative surgery already been performed for this tumor? If yes, provide the date.",
    domains: ["oncology"],
  },
  ChemotherapyTreament: {
    icon: "ic-pill",
    pole: "treatments",
    tab: "clinical",
    editable: true,
    order: 110,
    titleFr: "Traitements par chimiothérapie",
    titleEn: "Chemotherapy Treatments",
    defaultUserPrompt:
      "Has the patient received any chemotherapy for this tumor? If yes, provide details of the treatments.",
    domains: ["oncology"],
  },
  Chemotherapy: {
    icon: "ic-pill",
    pole: "treatments",
    tab: "clinical",
    editable: true,
    order: 110,
    titleFr: "Traitements systémiques & chimiothérapie",
    titleEn: "Chemotherapy & Systemic Treatments",
    defaultUserPrompt:
      "Has the patient received any chemotherapy for this tumor? If yes, provide details of the treatments.",
    domains: ["oncology"],
  },
  PlannedCurativeSurgery: {
    icon: "ic-calendar",
    pole: "treatments",
    tab: "clinical",
    editable: true,
    order: 120,
    titleFr: "Chirurgie curative prévue",
    titleEn: "Planned Curative Surgery",
    defaultUserPrompt: "Is a curative surgery planned for this tumor?",
    domains: ["oncology"],
  },
  PlannedSurgery: {
    icon: "ic-calendar",
    pole: "treatments",
    tab: "clinical",
    editable: true,
    order: 120,
    titleFr: "Chirurgie curative prévue",
    titleEn: "Planned Curative Surgery",
    defaultUserPrompt: "Is a curative surgery planned for this tumor?",
    domains: ["oncology"],
  },
  PatientAdministrative: {
    icon: "ic-folder",
    pole: "identity",
    tab: "clinical",
    editable: true,
    order: 200,
    titleFr: "Informations administratives du patient",
    titleEn: "Patient Administrative Information",
    defaultUserPrompt:
      "Extract patient identity and administrative metadata: first name, last name, birth name, date of birth, gender, and MDT meeting date.",
  },
};

const POLE_LABELS: Record<Language, Record<SectionPresentationMeta["pole"], string>> = {
  fr: {
    identity: "Données administratives extraites",
    clinical: "Caractérisation clinique & biologique",
    paraclinical: "Bilan paraclinique & Imagerie",
    treatments: "Historique thérapeutique & Chirurgie",
    synthesis: "Synthèse Collégiale & Complétude",
  },
  en: {
    identity: "Extracted Administrative Data",
    clinical: "Clinical & Biological Characterization",
    paraclinical: "Paraclinical & Imaging Assessment",
    treatments: "Therapeutic & Surgical History",
    synthesis: "MDT Board Synthesis & Completeness",
  },
};

const AGENT_ICONS_SVG: Record<string, string> = {
  administrative: "ic-folder",
  "mdt coordinator": "ic-scale",
  "ressource assistant": "ic-book",
  "pancreas expert": "ic-stethoscope",
  "oesophagus expert": "ic-activity",
  "hepatocellular expert": "ic-microscope",
  "neurologist expert": "ic-brain",
  "geneticist expert": "ic-dna",
  "pulmonologist expert": "ic-lungs",
  "physiotherapy expert": "ic-activity",
  "orthopedist expert": "ic-scale",
  radiotherapy: "ic-radiation",
  anatomopathologie: "ic-microscope",
};

export function getSectionPresentation(
  sectionName: string,
  domain: ClinicalDomain = "oncology",
  lang: Language = "fr",
): SectionPresentationMeta {
  const entry = SECTION_CATALOG[sectionName];
  if (entry) {
    const userPrompt =
      domain === "sma"
        ? (entry.userPromptSma ?? entry.defaultUserPrompt)
        : (entry.userPromptOncology ?? entry.defaultUserPrompt);
    return {
      name: sectionName,
      title: lang === "fr" ? entry.titleFr : entry.titleEn,
      icon: entry.icon,
      pole: entry.pole,
      poleLabel: POLE_LABELS[lang][entry.pole],
      tab: entry.tab,
      editable: entry.editable,
      order: entry.order,
      userPrompt,
    };
  }
  const fallbackTitle =
    lang === "fr" ? (CLINICAL_TRANSLATIONS_FR[sectionName] ?? sectionName) : sectionName;
  return {
    name: sectionName,
    title: fallbackTitle,
    icon: "ic-stethoscope",
    pole: "clinical",
    poleLabel: POLE_LABELS[lang].clinical,
    tab: "clinical",
    editable: true,
    order: 150,
    userPrompt: `Extract structured clinical data for section ${sectionName}.`,
  };
}

export function getDomainUserPromptsForAgent(
  agentName: string,
  domain: ClinicalDomain,
  lang: Language = "fr",
): AgentUserPromptItem[] {
  const clean = (agentName || "").trim().toLowerCase();
  const isCoordinator = clean.includes("coordinator");
  const isAdmin = clean.includes("admin");
  const isResource = clean.includes("ressource") || clean.includes("resource");

  if (isAdmin) {
    const meta = getSectionPresentation("PatientAdministrative", domain, lang);
    return [{ section: "PatientAdministrative", title: meta.title, prompt: meta.userPrompt }];
  }
  if (isCoordinator) {
    const m1 = getSectionPresentation("CareOrientationProposal", domain, lang);
    const m2 = getSectionPresentation("MTDCompleted", domain, lang);
    return [
      { section: "CareOrientationProposal", title: m1.title, prompt: m1.userPrompt },
      { section: "MTDCompleted", title: m2.title, prompt: m2.userPrompt },
    ];
  }
  if (isResource) {
    return [
      {
        section: "RAG",
        title:
          lang === "fr"
            ? "Recherche documentaire dans les référentiels (RAG)"
            : "Guideline RAG Search",
        prompt:
          "Use the `search_on_ressources` tool to retrieve exact scientific recommendations and cite document name, page, and excerpt.",
      },
    ];
  }

  // Specialist clinical agents run factual section extractions + ExpertAnswer + collaborative debate
  const canonicalKeys =
    domain === "sma"
      ? [
          "GeneticDiagnosis",
          "MotorFunctionStatus",
          "RespiratoryFunction",
          "OrthopedicAndSpineStatus",
          "BulbarAndNutritionalStatus",
          "PatientPerformanceStatus",
          "RadiologicExams",
          "ExpertAnswer",
          "CareOrientationProposal",
        ]
      : [
          "TumorLocation",
          "TumorBiology",
          "PatientPerformanceStatus",
          "RadiologicExams",
          "PreviousCurativeSurgery",
          "ChemotherapyTreament",
          "PlannedCurativeSurgery",
          "ExpertAnswer",
          "CareOrientationProposal",
        ];

  return canonicalKeys.map((key) => {
    const meta = getSectionPresentation(key, domain, lang);
    return {
      section: key,
      title: meta.title,
      prompt: meta.userPrompt,
    };
  });
}

export function getDomainQuickPrompts(
  domain: ClinicalDomain,
  scope: "dossier" | "guidelines",
  lang: Language = "fr",
): string[] {
  if (scope === "guidelines") {
    if (domain === "sma") {
      return lang === "fr"
        ? [
            "Quels sont les critères PNDS d'adaptation thérapeutique (nusinersen / risdiplam) ?",
            "Quel bilan respiratoire (CVF, VNI, Cough Assist) est requis avant la RCP ?",
            "Quelles échelles motrices standardisées (HFMSE, RULM, CHOP-INTEND) utiliser ?",
          ]
        : [
            "What are the PNDS criteria for SMN therapy adaptation?",
            "Which respiratory assessments (FVC, NIV) are required before MDT?",
            "Which motor scales (HFMSE, RULM, CHOP-INTEND) are recommended?",
          ];
    }
    return lang === "fr"
      ? [
          "Quel schéma de 2e ligne est recommandé par le TNCD après FOLFIRINOX ?",
          "Quels sont les examens obligatoires du bilan d'extension pré-RCP ?",
          "Quelles sont les indications de drainage biliaire ou de radiochimiothérapie ?",
        ]
      : [
          "Which 2nd-line regimen is recommended by TNCD after FOLFIRINOX?",
          "Which staging exams are mandatory before the MDT meeting?",
          "What are the indications for biliary drainage or chemoradiotherapy?",
        ];
  }

  if (domain === "sma") {
    return lang === "fr"
      ? [
          "Quelle est l'évolution des scores moteurs (HFMSE / RULM) et de la CVF ?",
          "Quels examens ou bilans manquent pour statuer en RCP ?",
          "Résumer les propositions des experts (neurologie, pneumologie, orthopédie).",
        ]
      : [
          "What is the evolution of motor scores (HFMSE / RULM) and FVC?",
          "Which exams are missing before the MDT board decision?",
          "Summarize the specialist opinions (neurology, pulmonology, orthopedics).",
        ];
  }

  return lang === "fr"
    ? [
        "Quelle est l'évolution du CA 19-9, de l'imagerie et de l'état général OMS ?",
        "Quels éléments manquent au dossier avant la décision collégiale en RCP ?",
        "Synthétiser les propositions thérapeutiques et les références TNCD citées.",
      ]
    : [
        "What is the evolution of CA 19-9, imaging, and WHO performance status?",
        "Which items are missing before the MDT board decision?",
        "Summarize the therapeutic proposals and cited TNCD references.",
      ];
}

export function getAgentPresentation(
  agentName: string,
  lang: Language = "fr",
): { name: string; label: string; icon: string } {
  const clean = (agentName || "").trim().toLowerCase();
  const icon = AGENT_ICONS_SVG[clean] ?? "ic-stethoscope";
  const label = translateValue(agentName, lang);
  return { name: agentName, label, icon };
}

export function formatFieldLabel(fieldKey: string, lang: Language = "fr"): string {
  if (lang === "fr" && CLINICAL_TRANSLATIONS_FR[fieldKey]) {
    return CLINICAL_TRANSLATIONS_FR[fieldKey]!;
  }
  return fieldKey.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}
