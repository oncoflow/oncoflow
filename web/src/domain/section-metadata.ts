import { CLINICAL_TRANSLATIONS_FR } from "./i18n.js";
import type { ClinicalDomain, Language } from "./types.js";

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
  CancerDescription: {
    icon: "ic-microscope",
    pole: "clinical",
    tab: "clinical",
    editable: true,
    order: 42,
    titleFr: "Caractérisation tumorale, TNM & Réponse RECIST",
    titleEn: "Tumor Characterization, TNM Staging & RECIST Response",
    defaultUserPrompt:
      "Extract the histological type and differentiation grade of the tumor, the TNM staging (cTNM or ypTNM), whether distant metastases are present and their sites, the size of the primary/target lesion in mm, and the RECIST 1.1 radiological evolution if mentioned.",
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
      "Extract tumor biology and biomarkers: MSI/MSS (MMR) status, serum tumor markers (CA 19-9 in U/mL, ACE/CEA in ng/mL, AFP in ng/mL), pre-therapeutic DPD / uracilemia (ng/mL), and molecular alterations (KRAS, NRAS, BRAF, HER2, PD-L1 CPS). Set missing items to null.",
    domains: ["oncology"],
  },
  HepaticStatus: {
    icon: "ic-flask",
    pole: "clinical",
    tab: "clinical",
    editable: true,
    order: 55,
    titleFr: "Bilan hépatique, Child-Pugh & BCLC",
    titleEn: "Hepatic Function, Child-Pugh & BCLC Stage",
    defaultUserPrompt:
      "Extract hepatic function indicators: total bilirubin level (µmol/L), Child-Pugh score/class (A5 to C15), and BCLC stage if applicable.",
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
  NutritionalStatus: {
    icon: "ic-activity",
    pole: "clinical",
    tab: "clinical",
    editable: true,
    order: 62,
    titleFr: "Statut nutritionnel & évolution pondérale",
    titleEn: "Nutritional Status & Weight Evolution",
    defaultUserPrompt:
      "Extract the patient's nutritional parameters: current weight (kg), weight loss percentage (%), BMI (IMC in kg/m²), and overall nutritional status.",
    domains: ["oncology"],
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
  SurgicalStatus: {
    icon: "ic-pill",
    pole: "treatments",
    tab: "clinical",
    editable: true,
    order: 95,
    titleFr: "Statut chirurgical & résécabilité",
    titleEn: "Surgical Status & Resectability",
    defaultUserPrompt:
      "Assess the tumor resectability status (Resectable, Borderline, Locally advanced, Unresectable, or Metastatic), whether curative surgery was performed, and the surgical resection margin (R0, R1, or R2) if operated.",
    domains: ["oncology"],
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

export function formatFieldLabel(fieldKey: string, lang: Language = "fr"): string {
  if (lang === "fr" && CLINICAL_TRANSLATIONS_FR[fieldKey]) {
    return CLINICAL_TRANSLATIONS_FR[fieldKey]!;
  }
  return fieldKey.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}
