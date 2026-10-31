import type { Language } from "./types.js";

/**
 * Bilingual clinical & UI dictionary (FR / EN)
 * Synchronized with application/src/ui/patient_mdt/translations.py + Web M3 UI strings.
 */
export const CLINICAL_TRANSLATIONS_FR: Record<string, string> = {
  // Model Class Titles
  "Patient administrative informations": "Informations administratives du patient",
  "Patient WHO performance status": "Statut de performance OMS du patient",
  "Location of the tumor": "Localisation de la tumeur",
  "Biology of the tumor": "Biologie de la tumeur",
  "List of radiological exams": "Liste des examens radiologiques",
  "Previous curative surgery": "Chirurgie curative antérieure",
  "Planned curative surgery": "Chirurgie curative prévue",
  "Chemotherapy treatments": "Traitements par chimiothérapie",
  ExpertAnswer: "Avis par spécialité",
  MTDCompleted: "Contrôle de complétude pré-RCP",
  CareOrientationProposal: "Proposition d'orientation pré-RCP",
  GeneticDiagnosis: "Diagnostic génétique",
  MotorFunctionStatus: "Statut moteur (HFMSE / RULM / CHOP-INTEND)",
  RespiratoryFunction: "Fonction respiratoire",
  OrthopedicAndSpineStatus: "Statut orthopédique et rachidien",
  BulbarAndNutritionalStatus: "Statut bulbaire et nutritionnel",
  PatientAdministrative: "Identité & séance RCP",
  PatientPerformanceStatus: "Statut de performance OMS",
  TumorLocation: "Localisation & stade tumoral",
  TumorBiology: "Biologie & biomarqueurs",
  RadiologicalExams: "Examens radiologiques",
  RadiologicExams: "Examens radiologiques",
  PreviousSurgery: "Chirurgie curative antérieure",
  PreviousCurativeSurgery: "Chirurgie curative antérieure",
  PlannedSurgery: "Chirurgie curative prévue",
  PlannedCurativeSurgery: "Chirurgie curative prévue",
  Chemotherapy: "Traitements systémiques / Chimiothérapie",
  ChemotherapyTreament: "Traitements systémiques / Chimiothérapie",
  mtd_complete: "Synthèse de complétude",
  // Field names
  first_name: "Prénom",
  last_name: "Nom",
  born_name: "Nom de naissance",
  age: "Âge",
  date_birth: "Date de naissance",
  date_rcp: "Date de la RCP",
  gender: "Genre",
  performance_status: "Statut de performance (OMS)",
  tumor_location: "Localisation tumorale",
  msi_state: "Statut MSI / MSS",
  exams_list: "Liste des examens",
  exam_name: "Nom de l'examen",
  exam_date: "Date de l'examen",
  exam_type: "Type d'examen",
  exam_result: "Résultat de l'examen",
  previous_curative_surgery: "Chirurgie curative antérieure",
  previous_curative_surgery_date: "Date de la chirurgie",
  planned_curative_surgery: "Chirurgie curative prévue",
  chemotherapy: "Chimiothérapie",
  chemotherapy_list: "Liste des chimiothérapies",
  chemotherapy_name: "Nom du protocole",
  chemotherapy_start_date: "Date de début",
  chemotherapy_end_date: "Date de fin",
  chemotherapy_tolerance: "Tolérance",
  expert_relevant: "Expertise pertinente",
  patient_priority: "Priorité",
  why_relevant: "Raison de la pertinence",
  sources_relevant: "Sources & Références",
  suggestions: "Suggestions",
  suggestion: "Proposition",
  why: "Justification clinique",
  references: "Références",
  name: "Nom",
  page: "Page",
  position: "Section / Position",
  excerpt: "Extrait",
  is_mtd_complete: "Dossier complet ?",
  what_missing: "Éléments manquants",
  reflection: "Réflexion / Synthèse du débat",
  care_adaptation_suggested: "Adaptation de prise en charge suggérée",
  suggested_priority: "Priorité suggérée",
  proposed_care_type: "Modalité / Axe de prise en charge proposé",
  clinical_rationale: "Argumentaire clinique pré-RCP",
  // SMA fields
  smn1_deletion_confirmed: "Délétion SMN1 confirmée",
  smn2_copy_count: "Nombre de copies SMN2",
  other_genetic_variants: "Autres variantes génétiques",
  sma_type: "Type de SMA",
  motor_milestones: "Acquisitions motrices",
  hfmse_score: "Score HFMSE",
  chop_intend_score: "Score CHOP INTEND",
  rulm_score: "Score RULM",
  requires_ventilation_support: "Assistance respiratoire requise",
  ventilation_type: "Type de ventilation",
  daily_ventilation_hours: "Heures de ventilation/jour",
  uses_cough_assist: "Utilise un assistant à la toux",
  forced_vital_capacity_percent: "Capacité vitale forcée (CVF %)",
  has_scoliosis: "Présence de scoliose",
  scoliosis_cobb_angle: "Angle de Cobb",
  spine_surgery_history: "Antécédent de chirurgie du rachis",
  joint_contractures: "Rétractions articulaires",
  wheelchair_user: "Utilisateur de fauteuil roulant",
  has_dysphagia: "Présence de dysphagie",
  feeding_mode: "Mode d'alimentation",
  history_aspiration_pneumonia: "Antécédents de fausses routes",
  nutritional_status: "Statut nutritionnel",
  // Enums & Clinical values
  Male: "Homme",
  Female: "Femme",
  Other: "Autre",
  Not_given: "Non spécifié",
  not_given: "Non spécifié",
  male: "Homme",
  female: "Femme",
  other: "Autre",
  urgent: "Priorité haute",
  medium: "Priorité modérée",
  low: "Priorité standard",
  "no answer": "Non évaluée",
  Pancreas: "Pancréas",
  Colon: "Côlon",
  Liver: "Foie",
  Stomach: "Estomac",
  Oesophagus: "Œsophage",
  Rectum: "Rectum",
  "Intra-hepatic bile duct": "Voies biliaires intra-hépatiques",
  "Extra-hepatic bile duct": "Voies biliaires extra-hépatiques",
  unknown: "Inconnu",
  Surgery: "Chirurgie",
  Radiotherapy: "Radiothérapie",
  Immunotherapy: "Immunothérapie",
  Curative: "Curatif",
  Palliative: "Palliatif",
  Adjuvant: "Adjuvant",
  "Neo-adjuvant": "Néo-adjuvant",
  Good: "Bonne",
  Medium: "Moyenne",
  Poor: "Mauvaise",
  oncology: "Oncologie",
  sma: "Amyotrophie spinale",
  // Agents
  Administrative: "Extraction administrative & clinique",
  "MDT Coordinator": "Coordinateur RCP",
  "Ressource Assistant": "Assistant référentiels",
  "pancreas expert": "Oncologie digestive — Pancréas",
  "oesophagus expert": "Oncologie digestive — Œsophage",
  "hepatocellular expert": "Hépatologie — Foie & CHC",
  "neurologist expert": "Neurologie — Référent SMA",
  "geneticist expert": "Génétique moléculaire — SMN1/SMN2",
  "pulmonologist expert": "Pneumologie — Fonction respiratoire",
  "physiotherapy expert": "MPR — Rééducation fonctionnelle",
  "orthopedist expert": "Chirurgie orthopédique & Rachis",
  // LLM fallbacks
  "Not documented in record": "Non renseigné",
  "Not documented": "Non renseigné",
  "Not mentioned in record": "Non renseigné",
  "Not mentioned": "Non mentionné",
  None: "Aucun",
  Normal: "Normal",
  Oral: "Voie orale",
  "Oral with thickening": "Voie orale épaissie",
  "Gastrostomy tube": "Gastrostomie (GPE)",
  "Gastrostomy tube (G-tube / GPE)": "Gastrostomie (GPE)",
  "Nasogastric tube": "Sonde nasogastrique",
  "Non-invasive ventilation": "VNI (BiPAP)",
  "Non-invasive ventilation (NIV/BiPAP)": "VNI (BiPAP)",
  Tracheostomy: "Trachéotomie",
  Underweight: "Insuffisance pondérale",
  "Failure to thrive / Underweight": "Cassure staturo-pondérale / Maigreur",
  Overweight: "Surpoids",
};

export const UI_CATALOG: Record<Language, Record<string, string>> = {
  fr: {
    "app.title": "DataSyntis — Préparation collégiale RCP",
    "nav.worklist": "Worklist RCP",
    "nav.ingest": "Importer des PDF",
    "nav.guidelines": "Référentiels scientifiques",
    "nav.agents": "Modules d'expertise",
    "nav.feedback": "Retours & Bugs",
    "nav.queue": "File d'analyse",
    "nav.styleguide": "Styleguide M3",
    "topbar.theme.light": "Clair",
    "topbar.theme.dark": "Sombre",
    "topbar.expert": "Mode expert",
    "queue.banner.idle": "Aucune analyse en cours",
    "queue.banner.running": "analyses en cours",
    "queue.banner.open": "Voir la file",
    "kpi.structured": "Dossiers structurés",
    "kpi.structured.meta": "Prêts pour la séance RCP",
    "kpi.priorityHigh": "Priorité haute",
    "kpi.priorityHigh.meta": "À présenter en premier",
    "kpi.completeness": "Contrôle de complétude",
    "kpi.completeness.meta": "Dossiers incomplets",
    "kpi.orientation": "Orientations pré-RCP",
    "kpi.orientation.meta": "Adaptations suggérées",
    "priority.high": "Priorité haute",
    "priority.high.short": "Haute",
    "priority.medium": "Priorité modérée",
    "priority.medium.short": "Modérée",
    "priority.low": "Priorité standard",
    "priority.low.short": "Standard",
    "priority.none": "Non évaluée",
    "priority.none.short": "Non évaluée",
    "completeness.complete": "Dossier complet",
    "completeness.complete.short": "Complet",
    "completeness.incomplete": "pièces manquantes",
    "completeness.incomplete.short": "manquantes",
    "orientation.adapt": "Adaptation suggérée",
    "orientation.standard": "Suivi habituel",
    "orientation.pending": "À discuter en RCP",
    "manual.badge": "Modifié manuellement",
    "disclaimer.ml":
      "Proposition d'aide à la préparation de la RCP générée localement. La décision thérapeutique appartient exclusivement au collège médical de la RCP.",
    "empty.value": "Non renseigné",
  },
  en: {
    "app.title": "DataSyntis — MDT Clinical Preparation",
    "nav.worklist": "MDT Worklist",
    "nav.ingest": "Upload PDFs",
    "nav.guidelines": "Scientific Guidelines",
    "nav.agents": "Specialty Agents",
    "nav.feedback": "Feedback & Bugs",
    "nav.queue": "Analysis Queue",
    "nav.styleguide": "M3 Styleguide",
    "topbar.theme.light": "Light",
    "topbar.theme.dark": "Dark",
    "topbar.expert": "Expert mode",
    "queue.banner.idle": "No active analysis",
    "queue.banner.running": "analyses running",
    "queue.banner.open": "View queue",
    "kpi.structured": "Structured records",
    "kpi.structured.meta": "Ready for MDT session",
    "kpi.priorityHigh": "High priority",
    "kpi.priorityHigh.meta": "Present first",
    "kpi.completeness": "Completeness check",
    "kpi.completeness.meta": "Incomplete records",
    "kpi.orientation": "Pre-MDT orientations",
    "kpi.orientation.meta": "Suggested adaptations",
    "priority.high": "High priority",
    "priority.high.short": "High",
    "priority.medium": "Moderate priority",
    "priority.medium.short": "Moderate",
    "priority.low": "Standard priority",
    "priority.low.short": "Standard",
    "priority.none": "Not assessed",
    "priority.none.short": "Not assessed",
    "completeness.complete": "Complete record",
    "completeness.complete.short": "Complete",
    "completeness.incomplete": "missing items",
    "completeness.incomplete.short": "missing",
    "orientation.adapt": "Suggested adaptation",
    "orientation.standard": "Routine follow-up",
    "orientation.pending": "To discuss in MDT",
    "manual.badge": "Manually edited",
    "disclaimer.ml":
      "Pre-MDT decision-support proposal generated locally. Therapeutic decisions belong exclusively to the MDT medical board.",
    "empty.value": "Not documented",
  },
};

export function t(key: string, lang: Language = "fr"): string {
  return UI_CATALOG[lang]?.[key] ?? UI_CATALOG.fr[key] ?? key;
}

export function formatCleanDateString(input: string, lang: Language = "fr"): string {
  return input.replace(
    /\b(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2}):(\d{2})(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)?\b/g,
    (_match, yyyy: string, mm: string, dd: string, hh?: string, min?: string) => {
      const datePart = lang === "fr" ? `${dd}/${mm}/${yyyy}` : `${yyyy}-${mm}-${dd}`;
      if (hh && min && !(hh === "00" && min === "00")) {
        return `${datePart} ${hh}:${min}`;
      }
      return datePart;
    },
  );
}

export function translateValue(value: unknown, lang: Language = "fr"): string {
  if (value === null || value === undefined || value === "") {
    return t("empty.value", lang);
  }
  if (typeof value === "boolean") {
    if (lang === "fr") return value ? "Oui" : "Non";
    return value ? "Yes" : "No";
  }
  const str = String(value).trim();
  if (!str) return t("empty.value", lang);
  if (lang === "fr") {
    const translated = CLINICAL_TRANSLATIONS_FR[str] ?? str;
    return formatCleanDateString(translated, "fr");
  }
  if (
    str === "Not documented in record" ||
    str === "Not documented" ||
    str === "Not mentioned in record"
  ) {
    return "Not documented";
  }
  return formatCleanDateString(str, "en");
}
