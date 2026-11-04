import { translateValue } from "./i18n.js";
import { getSectionPresentation } from "./section-metadata.js";
import type { AgentUserPromptItem, ClinicalDomain, Language } from "./types.js";

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
