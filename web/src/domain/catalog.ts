import { CLINICAL_TRANSLATIONS_FR, translateValue } from "./i18n.js";
import type {
  AgentUserPromptItem,
  ClinicalDomain,
  DomainFormSchema,
  FormSectionSchema,
  Language,
} from "./types.js";

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
    return [
      {
        section: "PatientAdministrative",
        title: meta.title,
        prompt: meta.userPrompt,
      },
    ];
  }
  if (isCoordinator) {
    const m1 = getSectionPresentation("CareOrientationProposal", domain, lang);
    const m2 = getSectionPresentation("MTDCompleted", domain, lang);
    return [
      {
        section: "CareOrientationProposal",
        title: m1.title,
        prompt: m1.userPrompt,
      },
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

const AGENT_SHORT_LABELS_FR: Record<string, string> = {
  administrative: "Administratif",
  "mdt coordinator": "Coordinateur RCP",
  "ressource assistant": "Référentiels",
  "pancreas expert": "Pancréas",
  "oesophagus expert": "Œsophage",
  "hepatocellular expert": "Foie & CHC",
  "neurologist expert": "Neurologie",
  "geneticist expert": "Génétique",
  "pulmonologist expert": "Pneumologie",
  "physiotherapy expert": "MPR",
  "orthopedist expert": "Orthopédie",
};

const AGENT_SHORT_LABELS_EN: Record<string, string> = {
  administrative: "Administrative",
  "mdt coordinator": "MDT Coordinator",
  "ressource assistant": "Guidelines",
  "pancreas expert": "Pancreas",
  "oesophagus expert": "Oesophagus",
  "hepatocellular expert": "Liver & HCC",
  "neurologist expert": "Neurology",
  "geneticist expert": "Genetics",
  "pulmonologist expert": "Pulmonology",
  "physiotherapy expert": "Physiotherapy",
  "orthopedist expert": "Orthopedics",
};

export function getAgentPresentation(
  agentName: string,
  lang: Language = "fr",
): { name: string; label: string; shortLabel: string; icon: string } {
  const clean = (agentName || "").trim().toLowerCase();
  const icon = AGENT_ICONS_SVG[clean] ?? "ic-stethoscope";
  const label = translateValue(agentName, lang);
  const shortMap = lang === "fr" ? AGENT_SHORT_LABELS_FR : AGENT_SHORT_LABELS_EN;
  const shortLabel =
    shortMap[clean] ?? (label.includes(" — ") ? (label.split(" — ").pop() ?? label).trim() : label);
  return { name: agentName, label, shortLabel, icon };
}

export function formatFieldLabel(fieldKey: string, lang: Language = "fr"): string {
  if (lang === "fr" && CLINICAL_TRANSLATIONS_FR[fieldKey]) {
    return CLINICAL_TRANSLATIONS_FR[fieldKey]!;
  }
  return fieldKey.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

export type FieldInputKind =
  | "text"
  | "textarea"
  | "integer"
  | "float"
  | "boolean"
  | "nullable_boolean"
  | "date"
  | "select"
  | "integer_select"
  | "string_list"
  | "exams_list"
  | "chemotherapy_list";

export interface FieldSelectOption {
  value: string;
  labelFr: string;
  labelEn: string;
}

export interface SectionFieldSchema {
  key: string;
  inputType: FieldInputKind;
  nullable: boolean;
  defaultValue?: unknown;
  min?: number;
  max?: number;
  step?: number;
  unit?: string;
  placeholderFr?: string;
  placeholderEn?: string;
  options?: FieldSelectOption[];
}

const CANONICAL_SECTION_ALIASES: Record<string, string> = {
  RadiologicalExams: "RadiologicExams",
  PreviousSurgery: "PreviousCurativeSurgery",
  PlannedSurgery: "PlannedCurativeSurgery",
  Chemotherapy: "ChemotherapyTreament",
};

export function resolveCanonicalSectionName(sectionName: string): string {
  return CANONICAL_SECTION_ALIASES[sectionName] ?? sectionName;
}

const BOOLEAN_SELECT_OPTIONS: FieldSelectOption[] = [
  { value: "true", labelFr: "Oui", labelEn: "Yes" },
  { value: "false", labelFr: "Non", labelEn: "No" },
];

const SECTION_FIELD_SCHEMAS: Record<string, SectionFieldSchema[]> = {
  PatientAdministrative: [
    { key: "last_name", inputType: "text", nullable: false, defaultValue: "" },
    { key: "first_name", inputType: "text", nullable: false, defaultValue: "" },
    { key: "born_name", inputType: "text", nullable: true, defaultValue: null },
    {
      key: "age",
      inputType: "integer",
      nullable: false,
      defaultValue: 0,
      min: 0,
      max: 150,
      step: 1,
      unit: "ans",
    },
    {
      key: "date_birth",
      inputType: "date",
      nullable: true,
      defaultValue: null,
    },
    { key: "date_rcp", inputType: "date", nullable: true, defaultValue: null },
    {
      key: "gender",
      inputType: "select",
      nullable: false,
      defaultValue: "Not_given",
      options: [
        { value: "Male", labelFr: "Homme", labelEn: "Male" },
        { value: "Female", labelFr: "Femme", labelEn: "Female" },
        { value: "Other", labelFr: "Autre", labelEn: "Other" },
        {
          value: "Not_given",
          labelFr: "Non spécifié",
          labelEn: "Not specified",
        },
      ],
    },
  ],
  PatientPerformanceStatus: [
    {
      key: "performance_status",
      inputType: "integer_select",
      nullable: false,
      defaultValue: 0,
      options: [
        {
          value: "0",
          labelFr: "OMS 0 — Activité normale sans restriction",
          labelEn: "WHO 0 — Fully active",
        },
        {
          value: "1",
          labelFr: "OMS 1 — Restreint pour les efforts intenses, ambulatoire",
          labelEn: "WHO 1 — Restricted in strenuous activity",
        },
        {
          value: "2",
          labelFr: "OMS 2 — Ambulatoire, autonome (> 50 % du temps éveillé debout)",
          labelEn: "WHO 2 — Ambulatory and capable of all selfcare",
        },
        {
          value: "3",
          labelFr: "OMS 3 — Autonomie limitée (alité ou fauteuil > 50 % du temps)",
          labelEn: "WHO 3 — Capable of only limited selfcare",
        },
        {
          value: "4",
          labelFr: "OMS 4 — Grabataire, totalement dépendant",
          labelEn: "WHO 4 — Completely disabled",
        },
      ],
    },
  ],
  TumorLocation: [
    {
      key: "tumor_location",
      inputType: "select",
      nullable: false,
      defaultValue: "unknown",
      options: [
        { value: "Pancreas", labelFr: "Pancréas", labelEn: "Pancreas" },
        { value: "Colon", labelFr: "Côlon", labelEn: "Colon" },
        { value: "Liver", labelFr: "Foie", labelEn: "Liver" },
        { value: "Stomach", labelFr: "Estomac", labelEn: "Stomach" },
        { value: "Oesophagus", labelFr: "Œsophage", labelEn: "Oesophagus" },
        { value: "Rectum", labelFr: "Rectum", labelEn: "Rectum" },
        {
          value: "Intra-hepatic bile duct",
          labelFr: "Voies biliaires intra-hépatiques",
          labelEn: "Intra-hepatic bile duct",
        },
        {
          value: "Extra-hepatic bile duct",
          labelFr: "Voies biliaires extra-hépatiques",
          labelEn: "Extra-hepatic bile duct",
        },
        { value: "unknown", labelFr: "Inconnu", labelEn: "Unknown" },
      ],
    },
  ],
  TumorBiology: [
    {
      key: "msi_state",
      inputType: "nullable_boolean",
      nullable: true,
      defaultValue: null,
      options: [
        { value: "", labelFr: "Non renseigné", labelEn: "Not documented" },
        {
          value: "false",
          labelFr: "MSS — Microsatellite stable",
          labelEn: "MSS — Microsatellite Stable",
        },
        {
          value: "true",
          labelFr: "MSI — Instabilité microsatellitaire",
          labelEn: "MSI — Microsatellite Instability",
        },
      ],
    },
  ],
  PreviousCurativeSurgery: [
    {
      key: "previous_curative_surgery",
      inputType: "boolean",
      nullable: false,
      defaultValue: false,
      options: BOOLEAN_SELECT_OPTIONS,
    },
    {
      key: "previous_curative_surgery_date",
      inputType: "date",
      nullable: true,
      defaultValue: null,
    },
  ],
  PlannedCurativeSurgery: [
    {
      key: "planned_curative_surgery",
      inputType: "boolean",
      nullable: false,
      defaultValue: false,
      options: BOOLEAN_SELECT_OPTIONS,
    },
  ],
  ChemotherapyTreament: [
    {
      key: "chemotherapy",
      inputType: "boolean",
      nullable: false,
      defaultValue: false,
      options: BOOLEAN_SELECT_OPTIONS,
    },
    {
      key: "chemotherapy_list",
      inputType: "chemotherapy_list",
      nullable: false,
      defaultValue: [],
    },
  ],
  RadiologicExams: [
    {
      key: "exams_list",
      inputType: "exams_list",
      nullable: false,
      defaultValue: [],
    },
  ],
  GeneticDiagnosis: [
    {
      key: "smn1_deletion_confirmed",
      inputType: "boolean",
      nullable: false,
      defaultValue: false,
      options: BOOLEAN_SELECT_OPTIONS,
    },
    {
      key: "smn2_copy_count",
      inputType: "integer",
      nullable: false,
      defaultValue: 2,
      min: 0,
      max: 10,
      step: 1,
    },
    {
      key: "other_genetic_variants",
      inputType: "textarea",
      nullable: true,
      defaultValue: null,
      placeholderFr: "Ex : Variant c.859G>C sur SMN2 (laisser vide si aucun)",
      placeholderEn: "E.g. SMN2 c.859G>C modifier variant (leave blank if none)",
    },
  ],
  MotorFunctionStatus: [
    {
      key: "sma_type",
      inputType: "select",
      nullable: false,
      defaultValue: "Type 2",
      options: [
        { value: "Type 1", labelFr: "Type 1", labelEn: "Type 1" },
        { value: "Type 2", labelFr: "Type 2", labelEn: "Type 2" },
        { value: "Type 3", labelFr: "Type 3", labelEn: "Type 3" },
        { value: "Type 4", labelFr: "Type 4", labelEn: "Type 4" },
        {
          value: "Pré-symptomatique",
          labelFr: "Pré-symptomatique",
          labelEn: "Pre-symptomatic",
        },
      ],
    },
    {
      key: "motor_milestones",
      inputType: "string_list",
      nullable: false,
      defaultValue: [],
      placeholderFr: "Ex : Tenue de tête, Station assise autonome (séparer par des virgules)",
      placeholderEn: "E.g. Head control, Sitting unsupported (comma-separated)",
    },
    {
      key: "hfmse_score",
      inputType: "integer",
      nullable: true,
      defaultValue: null,
      min: 0,
      max: 66,
      step: 1,
      unit: "/ 66",
    },
    {
      key: "chop_intend_score",
      inputType: "integer",
      nullable: true,
      defaultValue: null,
      min: 0,
      max: 64,
      step: 1,
      unit: "/ 64",
    },
    {
      key: "rulm_score",
      inputType: "integer",
      nullable: true,
      defaultValue: null,
      min: 0,
      max: 37,
      step: 1,
      unit: "/ 37",
    },
  ],
  RespiratoryFunction: [
    {
      key: "requires_ventilation_support",
      inputType: "boolean",
      nullable: false,
      defaultValue: false,
      options: BOOLEAN_SELECT_OPTIONS,
    },
    {
      key: "ventilation_type",
      inputType: "select",
      nullable: false,
      defaultValue: "None",
      options: [
        { value: "None", labelFr: "Aucune", labelEn: "None" },
        {
          value: "Non-invasive ventilation (NIV/BiPAP)",
          labelFr: "VNI (BiPAP)",
          labelEn: "Non-invasive ventilation (NIV/BiPAP)",
        },
        {
          value: "Tracheostomy",
          labelFr: "Trachéotomie",
          labelEn: "Tracheostomy",
        },
      ],
    },
    {
      key: "daily_ventilation_hours",
      inputType: "float",
      nullable: true,
      defaultValue: null,
      min: 0,
      max: 24,
      step: 0.5,
      unit: "h/j",
    },
    {
      key: "uses_cough_assist",
      inputType: "boolean",
      nullable: false,
      defaultValue: false,
      options: BOOLEAN_SELECT_OPTIONS,
    },
    {
      key: "forced_vital_capacity_percent",
      inputType: "float",
      nullable: true,
      defaultValue: null,
      min: 0,
      max: 150,
      step: 0.5,
      unit: "%",
    },
  ],
  OrthopedicAndSpineStatus: [
    {
      key: "has_scoliosis",
      inputType: "boolean",
      nullable: false,
      defaultValue: false,
      options: BOOLEAN_SELECT_OPTIONS,
    },
    {
      key: "scoliosis_cobb_angle",
      inputType: "float",
      nullable: true,
      defaultValue: null,
      min: 0,
      max: 180,
      step: 0.5,
      unit: "°",
    },
    {
      key: "spine_surgery_history",
      inputType: "boolean",
      nullable: false,
      defaultValue: false,
      options: BOOLEAN_SELECT_OPTIONS,
    },
    {
      key: "joint_contractures",
      inputType: "string_list",
      nullable: false,
      defaultValue: [],
      placeholderFr: "Ex : Genoux, Chevilles (séparer par des virgules)",
      placeholderEn: "E.g. Knees, Ankles (comma-separated)",
    },
    {
      key: "wheelchair_user",
      inputType: "boolean",
      nullable: false,
      defaultValue: false,
      options: BOOLEAN_SELECT_OPTIONS,
    },
  ],
  BulbarAndNutritionalStatus: [
    {
      key: "has_dysphagia",
      inputType: "boolean",
      nullable: false,
      defaultValue: false,
      options: BOOLEAN_SELECT_OPTIONS,
    },
    {
      key: "feeding_mode",
      inputType: "select",
      nullable: false,
      defaultValue: "Oral",
      options: [
        { value: "Oral", labelFr: "Voie orale", labelEn: "Oral" },
        {
          value: "Oral with thickening",
          labelFr: "Voie orale épaissie",
          labelEn: "Oral with thickening",
        },
        {
          value: "Gastrostomy tube (G-tube / GPE)",
          labelFr: "Gastrostomie (GPE)",
          labelEn: "Gastrostomy tube (G-tube / GPE)",
        },
        {
          value: "Nasogastric tube",
          labelFr: "Sonde nasogastrique",
          labelEn: "Nasogastric tube",
        },
      ],
    },
    {
      key: "history_aspiration_pneumonia",
      inputType: "boolean",
      nullable: false,
      defaultValue: false,
      options: BOOLEAN_SELECT_OPTIONS,
    },
    {
      key: "nutritional_status",
      inputType: "select",
      nullable: false,
      defaultValue: "Normal",
      options: [
        { value: "Normal", labelFr: "Normal", labelEn: "Normal" },
        {
          value: "Failure to thrive / Underweight",
          labelFr: "Cassure staturo-pondérale / Maigreur",
          labelEn: "Failure to thrive / Underweight",
        },
        { value: "Overweight", labelFr: "Surpoids", labelEn: "Overweight" },
      ],
    },
  ],
  MTDCompleted: [
    {
      key: "is_mtd_complete",
      inputType: "boolean",
      nullable: false,
      defaultValue: false,
      options: BOOLEAN_SELECT_OPTIONS,
    },
    {
      key: "what_missing",
      inputType: "string_list",
      nullable: false,
      defaultValue: [],
      placeholderFr: "Éléments manquants séparés par des virgules ou points-virgules",
      placeholderEn: "Missing items separated by commas or semicolons",
    },
    {
      key: "reflection",
      inputType: "textarea",
      nullable: true,
      defaultValue: null,
    },
  ],
};

export function getSectionFieldSchemas(
  sectionName: string,
  domainSchema?: DomainFormSchema | null,
): SectionFieldSchema[] {
  const canonical = resolveCanonicalSectionName(sectionName);
  if (domainSchema && Array.isArray(domainSchema.sections)) {
    const matched = domainSchema.sections.find(
      (s) =>
        s.name === sectionName ||
        s.name === canonical ||
        resolveCanonicalSectionName(s.name) === canonical,
    );
    if (matched?.json_schema && typeof matched.json_schema === "object") {
      const parsed = parseJsonSchemaToFieldSchemas(
        canonical,
        matched.json_schema,
        domainSchema.enums,
      );
      if (parsed.length > 0) {
        return parsed;
      }
    }
  }
  if (domainSchema && Array.isArray(domainSchema.sections)) {
    const matched = domainSchema.sections.find(
      (s) => s.name === sectionName || s.name === canonical || resolveCanonicalSectionName(s.name) === canonical,
    );
    if (matched?.json_schema && typeof matched.json_schema === "object") {
      const parsed = parseJsonSchemaToFieldSchemas(
        canonical,
        matched.json_schema,
        domainSchema.enums,
      );
      if (parsed.length > 0) {
        return parsed;
      }
    }
  }
  return SECTION_FIELD_SCHEMAS[canonical] ?? [];
}

/**
 * Dynamically converts a Pydantic v2 JSON Schema (`model_cls.model_json_schema()`)
 * distributed by `GET /api/v1/patientmdtform/schema` into typed `SectionFieldSchema[]`
 * descriptors understood by the Web UI and form coercion engine.
 */
export function parseJsonSchemaToFieldSchemas(
  sectionName: string,
  jsonSchema: Record<string, unknown>,
  _domainEnums?: Record<string, Array<string | number>>,
): SectionFieldSchema[] {
  const canonical = resolveCanonicalSectionName(sectionName);
  const fallbackList = SECTION_FIELD_SCHEMAS[canonical] ?? [];
  const fallbackByKey = new Map(fallbackList.map((f) => [f.key, f]));

  const defs =
    jsonSchema.$defs && typeof jsonSchema.$defs === "object"
      ? (jsonSchema.$defs as Record<string, Record<string, unknown>>)
      : {};

  const resolveRef = (node: Record<string, unknown>): Record<string, unknown> => {
    if (typeof node.$ref === "string" && node.$ref.startsWith("#/$defs/")) {
      const refName = node.$ref.slice("#/$defs/".length);
      return defs[refName] ? { ...defs[refName], ...node, $ref: undefined } : node;
    }
    return node;
  };

  let targetRoot = resolveRef(jsonSchema);
  let rawProps =
    targetRoot.properties && typeof targetRoot.properties === "object"
      ? (targetRoot.properties as Record<string, Record<string, unknown>>)
      : {};
  let requiredSet = new Set<string>(
    Array.isArray(targetRoot.required) ? (targetRoot.required as string[]) : [],
  );

  // Unwrap single nested object wrapper like MTDCompleted.properties.mtd_complete -> $defs.MTDComplete
  if (rawProps.mtd_complete && Object.keys(rawProps).length === 1) {
    const inner = resolveRef(rawProps.mtd_complete);
    if (inner.properties && typeof inner.properties === "object") {
      targetRoot = inner;
      rawProps = inner.properties as Record<string, Record<string, unknown>>;
      requiredSet = new Set<string>(
        Array.isArray(inner.required) ? (inner.required as string[]) : [],
      );
    }
  }

  const results: SectionFieldSchema[] = [];

  for (const [propKey, propRaw] of Object.entries(rawProps)) {
    if (
      propKey === "references" ||
      propKey === "reasoning_thinking" ||
      propKey === "time_execution"
    ) {
      continue;
    }
    const fb = fallbackByKey.get(propKey);
    let node = resolveRef(propRaw ?? {});
    let nullable = !requiredSet.has(propKey);

    if (Array.isArray(node.anyOf)) {
      const variants = node.anyOf as Array<Record<string, unknown>>;
      if (variants.some((v) => v?.type === "null")) {
        nullable = true;
      }
      const nonNull = variants.find((v) => v?.type !== "null");
      if (nonNull) {
        node = { ...node, ...resolveRef(nonNull) };
      }
    }

    const propType = typeof node.type === "string" ? node.type : "";
    const propFormat = typeof node.format === "string" ? node.format : "";
    const rawEnum = Array.isArray(node.enum)
      ? node.enum
      : Array.isArray(node.options)
        ? node.options
        : Array.isArray(propRaw?.options)
          ? (propRaw.options as unknown[])
          : null;

    if (propKey === "exams_list" || fb?.inputType === "exams_list") {
      results.push({
        key: propKey,
        inputType: "exams_list",
        nullable: false,
        defaultValue: [],
      });
      continue;
    }

    if (propKey === "chemotherapy_list" || fb?.inputType === "chemotherapy_list") {
      results.push({
        key: propKey,
        inputType: "chemotherapy_list",
        nullable: false,
        defaultValue: [],
      });
      continue;
    }

    if (rawEnum && rawEnum.length > 0) {
      const isIntEnum = propType === "integer" || rawEnum.every((v) => typeof v === "number");
      const options: FieldSelectOption[] =
        fb?.options ??
        rawEnum.map((val) => {
          const strVal = String(val);
          return {
            value: strVal,
            labelFr: translateValue(val, "fr"),
            labelEn: translateValue(val, "en"),
          };
        });
      results.push({
        key: propKey,
        inputType: isIntEnum ? "integer_select" : "select",
        nullable: false,
        defaultValue: node.default ?? fb?.defaultValue ?? String(rawEnum[0] ?? ""),
        options,
      });
      continue;
    }

    if (propType === "boolean") {
      const isNullableBool =
        fb?.inputType === "nullable_boolean" ||
        (nullable && node.default === undefined && propKey === "msi_state");
      results.push({
        key: propKey,
        inputType: isNullableBool ? "nullable_boolean" : "boolean",
        nullable: isNullableBool,
        defaultValue: isNullableBool ? null : Boolean(node.default ?? fb?.defaultValue ?? false),
        options: fb?.options ?? BOOLEAN_SELECT_OPTIONS,
      });
      continue;
    }

    if (propType === "integer") {
      results.push({
        key: propKey,
        inputType: "integer",
        nullable,
        defaultValue: nullable ? null : Number(node.default ?? fb?.defaultValue ?? 0),
        min: typeof node.minimum === "number" ? node.minimum : (fb?.min ?? 0),
        max: typeof node.maximum === "number" ? node.maximum : fb?.max,
        step: 1,
        unit: fb?.unit,
      });
      continue;
    }

    if (propType === "number") {
      results.push({
        key: propKey,
        inputType: "float",
        nullable,
        defaultValue: nullable ? null : Number(node.default ?? fb?.defaultValue ?? 0),
        min: typeof node.minimum === "number" ? node.minimum : (fb?.min ?? 0),
        max: typeof node.maximum === "number" ? node.maximum : fb?.max,
        step: fb?.step ?? 0.5,
        unit: fb?.unit,
      });
      continue;
    }

    if (propFormat === "date" || propFormat === "date-time" || fb?.inputType === "date") {
      results.push({
        key: propKey,
        inputType: "date",
        nullable: true,
        defaultValue: null,
      });
      continue;
    }

    if (propType === "array") {
      results.push({
        key: propKey,
        inputType: "string_list",
        nullable: false,
        defaultValue: [],
        placeholderFr: fb?.placeholderFr,
        placeholderEn: fb?.placeholderEn,
      });
      continue;
    }

    const isTextarea =
      fb?.inputType === "textarea" ||
      propKey === "reflection" ||
      propKey === "other_genetic_variants";
    results.push({
      key: propKey,
      inputType: isTextarea ? "textarea" : "text",
      nullable,
      defaultValue: nullable ? null : String(node.default ?? fb?.defaultValue ?? ""),
      placeholderFr: fb?.placeholderFr,
      placeholderEn: fb?.placeholderEn,
    });
  }

  return results;
}

/**
 * Generates a complete `DomainFormSchema` matching FastAPI's `GET /api/v1/patientmdtform/schema`
 * response structure (`sections[].json_schema` + `enums`).
 */
export function buildDefaultDomainFormSchema(domain: ClinicalDomain): DomainFormSchema {
  const sectionNames =
    domain === "sma"
      ? [
          "PatientAdministrative",
          "GeneticDiagnosis",
          "MotorFunctionStatus",
          "RespiratoryFunction",
          "OrthopedicAndSpineStatus",
          "BulbarAndNutritionalStatus",
          "PatientPerformanceStatus",
          "RadiologicExams",
          "MTDCompleted",
          "ExpertAnswer",
          "CareOrientationProposal",
        ]
      : [
          "PatientAdministrative",
          "TumorLocation",
          "TumorBiology",
          "PatientPerformanceStatus",
          "RadiologicExams",
          "PreviousCurativeSurgery",
          "ChemotherapyTreament",
          "PlannedCurativeSurgery",
          "MTDCompleted",
          "ExpertAnswer",
          "CareOrientationProposal",
        ];

  const sections: FormSectionSchema[] = sectionNames.map((name) => {
    const meta = getSectionPresentation(name, domain, "fr");
    const fieldSchemas = SECTION_FIELD_SCHEMAS[name] ?? [];
    const properties: Record<string, unknown> = {};
    const required: string[] = [];

    for (const fs of fieldSchemas) {
      if (!fs.nullable) required.push(fs.key);
      if (fs.inputType === "boolean") {
        properties[fs.key] = {
          type: "boolean",
          default: fs.defaultValue ?? false,
        };
      } else if (fs.inputType === "nullable_boolean") {
        properties[fs.key] = {
          anyOf: [{ type: "boolean" }, { type: "null" }],
          default: null,
        };
      } else if (fs.inputType === "integer") {
        const base = {
          type: "integer",
          ...(fs.min !== undefined ? { minimum: fs.min } : {}),
          ...(fs.max !== undefined ? { maximum: fs.max } : {}),
        };
        properties[fs.key] = fs.nullable
          ? { anyOf: [base, { type: "null" }], default: null }
          : base;
      } else if (fs.inputType === "integer_select") {
        properties[fs.key] = {
          type: "integer",
          enum: (fs.options ?? []).map((o) => Number(o.value)),
        };
      } else if (fs.inputType === "float") {
        const base = {
          type: "number",
          ...(fs.min !== undefined ? { minimum: fs.min } : {}),
          ...(fs.max !== undefined ? { maximum: fs.max } : {}),
        };
        properties[fs.key] = fs.nullable
          ? { anyOf: [base, { type: "null" }], default: null }
          : base;
      } else if (fs.inputType === "date") {
        properties[fs.key] = {
          anyOf: [{ type: "string", format: "date-time" }, { type: "null" }],
          default: null,
        };
      } else if (fs.inputType === "select") {
        properties[fs.key] = {
          type: "string",
          enum: (fs.options ?? []).map((o) => o.value),
          options: (fs.options ?? []).map((o) => o.value),
        };
      } else if (fs.inputType === "string_list") {
        properties[fs.key] = {
          type: "array",
          items: { type: "string" },
        };
      } else if (fs.inputType === "exams_list") {
        properties[fs.key] = {
          type: "array",
          items: { $ref: "#/$defs/RadiologicalExamination" },
        };
      } else if (fs.inputType === "chemotherapy_list") {
        properties[fs.key] = {
          anyOf: [{ type: "array", items: { $ref: "#/$defs/ChemotherapyData" } }, { type: "null" }],
        };
      } else {
        properties[fs.key] = fs.nullable
          ? { anyOf: [{ type: "string" }, { type: "null" }], default: null }
          : { type: "string" };
      }
    }

    return {
      name,
      description: meta.title,
      question: meta.userPrompt,
      multi_agent: name === "ExpertAnswer",
      collaborative: name === "CareOrientationProposal" || name === "MTDCompleted",
      agents: [],
      editable: meta.editable,
      json_schema: {
        title: name,
        type: "object",
        properties,
        required,
      },
    };
  });

  return {
    domain,
    sections,
    enums: {
      Gender: ["Male", "Female", "Other", "Not_given"],
      WHOPerformanceStatus: [0, 1, 2, 3, 4],
      RadiologicExamType: ["CT", "MRI", "PET", "EUS"],
      TreatmentToleranceEnum: ["Good", "Medium", "Poor"],
      PrimaryOrganEnum: [
        "Pancreas",
        "Colon",
        "Liver",
        "Stomach",
        "Oesophagus",
        "Rectum",
        "Intra-hepatic bile duct",
        "Extra-hepatic bile duct",
        "unknown",
      ],
    },
  };
}

/**
 * Dynamically converts a Pydantic v2 JSON Schema (`model_cls.model_json_schema()`)
 * distributed by `GET /api/v1/patientmdtform/schema` into typed `SectionFieldSchema[]`
 * descriptors understood by the Web UI and form coercion engine.
 */
export function parseJsonSchemaToFieldSchemas(
  sectionName: string,
  jsonSchema: Record<string, unknown>,
  _domainEnums?: Record<string, Array<string | number>>,
): SectionFieldSchema[] {
  const canonical = resolveCanonicalSectionName(sectionName);
  const fallbackList = SECTION_FIELD_SCHEMAS[canonical] ?? [];
  const fallbackByKey = new Map(fallbackList.map((f) => [f.key, f]));

  const defs =
    jsonSchema.$defs && typeof jsonSchema.$defs === "object"
      ? (jsonSchema.$defs as Record<string, Record<string, unknown>>)
      : {};

  const resolveRef = (node: Record<string, unknown>): Record<string, unknown> => {
    if (typeof node.$ref === "string" && node.$ref.startsWith("#/$defs/")) {
      const refName = node.$ref.slice("#/$defs/".length);
      return defs[refName] ? { ...defs[refName], ...node, $ref: undefined } : node;
    }
    return node;
  };

  let targetRoot = resolveRef(jsonSchema);
  let rawProps =
    targetRoot.properties && typeof targetRoot.properties === "object"
      ? (targetRoot.properties as Record<string, Record<string, unknown>>)
      : {};
  let requiredSet = new Set<string>(
    Array.isArray(targetRoot.required) ? (targetRoot.required as string[]) : [],
  );

  // Unwrap single nested object wrapper like MTDCompleted.properties.mtd_complete -> $defs.MTDComplete
  if (rawProps.mtd_complete && Object.keys(rawProps).length === 1) {
    const inner = resolveRef(rawProps.mtd_complete);
    if (inner.properties && typeof inner.properties === "object") {
      targetRoot = inner;
      rawProps = inner.properties as Record<string, Record<string, unknown>>;
      requiredSet = new Set<string>(
        Array.isArray(inner.required) ? (inner.required as string[]) : [],
      );
    }
  }

  const results: SectionFieldSchema[] = [];

  for (const [propKey, propRaw] of Object.entries(rawProps)) {
    if (propKey === "references" || propKey === "reasoning_thinking" || propKey === "time_execution") {
      continue;
    }
    const fb = fallbackByKey.get(propKey);
    let node = resolveRef(propRaw ?? {});
    let nullable = !requiredSet.has(propKey);

    if (Array.isArray(node.anyOf)) {
      const variants = node.anyOf as Array<Record<string, unknown>>;
      if (variants.some((v) => v?.type === "null")) {
        nullable = true;
      }
      const nonNull = variants.find((v) => v?.type !== "null");
      if (nonNull) {
        node = { ...node, ...resolveRef(nonNull) };
      }
    }

    const propType = typeof node.type === "string" ? node.type : "";
    const propFormat = typeof node.format === "string" ? node.format : "";
    const rawEnum = Array.isArray(node.enum)
      ? node.enum
      : Array.isArray(node.options)
        ? node.options
        : Array.isArray(propRaw?.options)
          ? (propRaw.options as unknown[])
          : null;

    if (propKey === "exams_list" || fb?.inputType === "exams_list") {
      results.push({
        key: propKey,
        inputType: "exams_list",
        nullable: false,
        defaultValue: [],
      });
      continue;
    }

    if (propKey === "chemotherapy_list" || fb?.inputType === "chemotherapy_list") {
      results.push({
        key: propKey,
        inputType: "chemotherapy_list",
        nullable: false,
        defaultValue: [],
      });
      continue;
    }

    if (rawEnum && rawEnum.length > 0) {
      const isIntEnum = propType === "integer" || rawEnum.every((v) => typeof v === "number");
      const options: FieldSelectOption[] =
        fb?.options ??
        rawEnum.map((val) => {
          const strVal = String(val);
          return {
            value: strVal,
            labelFr: translateValue(val, "fr"),
            labelEn: translateValue(val, "en"),
          };
        });
      results.push({
        key: propKey,
        inputType: isIntEnum ? "integer_select" : "select",
        nullable: false,
        defaultValue: node.default ?? fb?.defaultValue ?? String(rawEnum[0] ?? ""),
        options,
      });
      continue;
    }

    if (propType === "boolean") {
      const isNullableBool =
        fb?.inputType === "nullable_boolean" ||
        (nullable && node.default === undefined && propKey === "msi_state");
      results.push({
        key: propKey,
        inputType: isNullableBool ? "nullable_boolean" : "boolean",
        nullable: isNullableBool,
        defaultValue: isNullableBool ? null : Boolean(node.default ?? fb?.defaultValue ?? false),
        options: fb?.options ?? BOOLEAN_SELECT_OPTIONS,
      });
      continue;
    }

    if (propType === "integer") {
      results.push({
        key: propKey,
        inputType: "integer",
        nullable,
        defaultValue: nullable ? null : Number(node.default ?? fb?.defaultValue ?? 0),
        min: typeof node.minimum === "number" ? node.minimum : fb?.min ?? 0,
        max: typeof node.maximum === "number" ? node.maximum : fb?.max,
        step: 1,
        unit: fb?.unit,
      });
      continue;
    }

    if (propType === "number") {
      results.push({
        key: propKey,
        inputType: "float",
        nullable,
        defaultValue: nullable ? null : Number(node.default ?? fb?.defaultValue ?? 0),
        min: typeof node.minimum === "number" ? node.minimum : fb?.min ?? 0,
        max: typeof node.maximum === "number" ? node.maximum : fb?.max,
        step: fb?.step ?? 0.5,
        unit: fb?.unit,
      });
      continue;
    }

    if (propFormat === "date" || propFormat === "date-time" || fb?.inputType === "date") {
      results.push({
        key: propKey,
        inputType: "date",
        nullable: true,
        defaultValue: null,
      });
      continue;
    }

    if (propType === "array") {
      results.push({
        key: propKey,
        inputType: "string_list",
        nullable: false,
        defaultValue: [],
        placeholderFr: fb?.placeholderFr,
        placeholderEn: fb?.placeholderEn,
      });
      continue;
    }

    const isTextarea =
      fb?.inputType === "textarea" ||
      propKey === "reflection" ||
      propKey === "other_genetic_variants";
    results.push({
      key: propKey,
      inputType: isTextarea ? "textarea" : "text",
      nullable,
      defaultValue: nullable ? null : String(node.default ?? fb?.defaultValue ?? ""),
      placeholderFr: fb?.placeholderFr,
      placeholderEn: fb?.placeholderEn,
    });
  }

  return results;
}

/**
 * Generates a complete `DomainFormSchema` matching FastAPI's `GET /api/v1/patientmdtform/schema`
 * response structure (`sections[].json_schema` + `enums`).
 */
export function buildDefaultDomainFormSchema(domain: ClinicalDomain): DomainFormSchema {
  const sectionNames =
    domain === "sma"
      ? [
          "PatientAdministrative",
          "GeneticDiagnosis",
          "MotorFunctionStatus",
          "RespiratoryFunction",
          "OrthopedicAndSpineStatus",
          "BulbarAndNutritionalStatus",
          "PatientPerformanceStatus",
          "RadiologicExams",
          "MTDCompleted",
          "ExpertAnswer",
          "CareOrientationProposal",
        ]
      : [
          "PatientAdministrative",
          "TumorLocation",
          "TumorBiology",
          "PatientPerformanceStatus",
          "RadiologicExams",
          "PreviousCurativeSurgery",
          "ChemotherapyTreament",
          "PlannedCurativeSurgery",
          "MTDCompleted",
          "ExpertAnswer",
          "CareOrientationProposal",
        ];

  const sections: FormSectionSchema[] = sectionNames.map((name) => {
    const meta = getSectionPresentation(name, domain, "fr");
    const fieldSchemas = SECTION_FIELD_SCHEMAS[name] ?? [];
    const properties: Record<string, unknown> = {};
    const required: string[] = [];

    for (const fs of fieldSchemas) {
      if (!fs.nullable) required.push(fs.key);
      if (fs.inputType === "boolean") {
        properties[fs.key] = { type: "boolean", default: fs.defaultValue ?? false };
      } else if (fs.inputType === "nullable_boolean") {
        properties[fs.key] = {
          anyOf: [{ type: "boolean" }, { type: "null" }],
          default: null,
        };
      } else if (fs.inputType === "integer") {
        const base = {
          type: "integer",
          ...(fs.min !== undefined ? { minimum: fs.min } : {}),
          ...(fs.max !== undefined ? { maximum: fs.max } : {}),
        };
        properties[fs.key] = fs.nullable
          ? { anyOf: [base, { type: "null" }], default: null }
          : base;
      } else if (fs.inputType === "integer_select") {
        properties[fs.key] = {
          type: "integer",
          enum: (fs.options ?? []).map((o) => Number(o.value)),
        };
      } else if (fs.inputType === "float") {
        const base = {
          type: "number",
          ...(fs.min !== undefined ? { minimum: fs.min } : {}),
          ...(fs.max !== undefined ? { maximum: fs.max } : {}),
        };
        properties[fs.key] = fs.nullable
          ? { anyOf: [base, { type: "null" }], default: null }
          : base;
      } else if (fs.inputType === "date") {
        properties[fs.key] = {
          anyOf: [{ type: "string", format: "date-time" }, { type: "null" }],
          default: null,
        };
      } else if (fs.inputType === "select") {
        properties[fs.key] = {
          type: "string",
          enum: (fs.options ?? []).map((o) => o.value),
          options: (fs.options ?? []).map((o) => o.value),
        };
      } else if (fs.inputType === "string_list") {
        properties[fs.key] = {
          type: "array",
          items: { type: "string" },
        };
      } else if (fs.inputType === "exams_list") {
        properties[fs.key] = {
          type: "array",
          items: { $ref: "#/$defs/RadiologicalExamination" },
        };
      } else if (fs.inputType === "chemotherapy_list") {
        properties[fs.key] = {
          anyOf: [
            { type: "array", items: { $ref: "#/$defs/ChemotherapyData" } },
            { type: "null" },
          ],
        };
      } else {
        properties[fs.key] = fs.nullable
          ? { anyOf: [{ type: "string" }, { type: "null" }], default: null }
          : { type: "string" };
      }
    }

    return {
      name,
      description: meta.title,
      question: meta.userPrompt,
      multi_agent: name === "ExpertAnswer",
      collaborative: name === "CareOrientationProposal" || name === "MTDCompleted",
      agents: [],
      editable: meta.editable,
      json_schema: {
        title: name,
        type: "object",
        properties,
        required,
      },
    };
  });

  return {
    domain,
    sections,
    enums: {
      Gender: ["Male", "Female", "Other", "Not_given"],
      WHOPerformanceStatus: [0, 1, 2, 3, 4],
      RadiologicExamType: ["CT", "MRI", "PET", "EUS"],
      TreatmentToleranceEnum: ["Good", "Medium", "Poor"],
      PrimaryOrganEnum: [
        "Pancreas",
        "Colon",
        "Liver",
        "Stomach",
        "Oesophagus",
        "Rectum",
        "Intra-hepatic bile duct",
        "Extra-hepatic bile duct",
        "unknown",
      ],
    },
  };
}

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
    // Check if indexed form fields exam_name_0, exam_type_0, ... were submitted
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
      // Ensure date_birth is never after date_rcp
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
