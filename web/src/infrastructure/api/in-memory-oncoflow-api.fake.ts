import type {
  ChatReply,
  MissingItemsUpdateInput,
  OncoflowApiPort,
  UploadFileInput,
} from "../../application/ports/oncoflow-api.port.js";
import {
  buildDefaultDomainFormSchema,
  coerceSectionUpdatePayload,
  getAgentPresentation,
  getDomainUserPromptsForAgent,
  resolveCanonicalSectionName,
} from "../../domain/catalog.js";
import { normalizePriorityLevel } from "../../domain/triage.js";
import type {
  AgentModuleInfo,
  BatchStatus,
  BugReportItem,
  ClinicalDomain,
  DomainFormSchema,
  Language,
  MdtAgendaCandidate,
  MdtAgendaEnrollInput,
  MdtAgendaItem,
  MdtAgendaMoveInput,
  MdtAgendaSortStrategy,
  MdtAgendaUpdateInput,
  MdtAgendaView,
  MdtExpertWindow,
  MdtFormCard,
  MdtFormDetail,
  PatientListItem,
  PractitionerNoteItem,
  QueueJobItem,
  QueueStats,
  ResourceDocument,
} from "../../domain/types.js";

function escapePdfLiteral(str: string): string {
  return String(str || "")
    .replace(/\\/g, "\\\\")
    .replace(/\(/g, "\\(")
    .replace(/\)/g, "\\)")
    .replace(/[\u2018\u2019]/g, "'")
    .replace(/[\u201C\u201D]/g, '"')
    .replace(/[\u2013\u2014]/g, "-")
    .replace(/\u2026/g, "...")
    .replace(/[^\x20-\x7E\xA0-\xFF]/g, " ");
}

function wrapPdfLines(rawText: string, maxChars = 88): string[] {
  const result: string[] = [];
  for (const rawLine of String(rawText || "").split(/\r?\n/)) {
    const cleaned = rawLine
      .replace(/^#+\s*/, "")
      .replace(/\*\*/g, "")
      .trim();
    if (!cleaned) {
      if (result.length > 0 && result[result.length - 1] !== "") {
        result.push("");
      }
      continue;
    }
    let rest = cleaned;
    while (rest.length > maxChars) {
      let cut = rest.lastIndexOf(" ", maxChars);
      if (cut < 30) cut = maxChars;
      result.push(rest.slice(0, cut).trim());
      rest = rest.slice(cut).trim();
    }
    if (rest) result.push(rest);
  }
  return result;
}

function buildClinicalPdfBuffer(title: string, subtitle: string, bodyLines: string[]): Buffer {
  const ops: string[] = [
    "q",
    "0.22 0.42 0.40 rg",
    "36 724 540 38 re f",
    "Q",
    "BT",
    "/F2 12.5 Tf",
    "1 1 1 rg",
    "48 738 Td",
    `(${escapePdfLiteral(title)}) Tj`,
    "ET",
    "BT",
    "/F2 10 Tf",
    "0.15 0.16 0.18 rg",
    "36 702 Td",
    `(${escapePdfLiteral(subtitle)}) Tj`,
    "ET",
    "0.82 0.84 0.86 RG",
    "1 w",
    "36 692 m 576 692 l S",
    "BT",
    "/F1 9.5 Tf",
    "0.11 0.11 0.13 rg",
    "14 TL",
    "36 674 Td",
  ];
  for (const line of bodyLines.slice(0, 44)) {
    ops.push(`(${escapePdfLiteral(line)}) Tj T*`);
  }
  ops.push("ET");
  const stream = ops.join("\n");
  const objs = [
    "1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
    "2 0 obj\n<< /Type /Pages /Count 1 /Kids [3 0 R] >>\nendobj\n",
    "3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R /F2 5 0 R >> >> /Contents 6 0 R >>\nendobj\n",
    "4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>\nendobj\n",
    "5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>\nendobj\n",
    `6 0 obj\n<< /Length ${Buffer.byteLength(stream, "latin1")} >>\nstream\n${stream}\nendstream\nendobj\n`,
  ];
  let pdf = "%PDF-1.4\n";
  const offsets = [0];
  for (const obj of objs) {
    offsets.push(Buffer.byteLength(pdf, "latin1"));
    pdf += obj;
  }
  const xrefStart = Buffer.byteLength(pdf, "latin1");
  pdf += `xref\n0 ${objs.length + 1}\n`;
  pdf += "0000000000 65535 f \n";
  for (let i = 1; i < offsets.length; i++) {
    pdf += `${String(offsets[i]).padStart(10, "0")} 00000 n \n`;
  }
  pdf += `trailer\n<< /Size ${objs.length + 1} /Root 1 0 R >>\nstartxref\n${xrefStart}\n%%EOF\n`;
  return Buffer.from(pdf, "latin1");
}

const MINIMAL_PDF_BUFFER = buildClinicalPdfBuffer(
  "DataSyntis — Compte Rendu Medical RCP",
  "Document clinique source (mode demonstration local)",
  [
    "Compte rendu medical numerise pour preparation collegiale de seance RCP.",
    "Donnees extraites localement sans transfert vers un service cloud externe.",
  ],
);

export class InMemoryOncoflowApiFake implements OncoflowApiPort {
  private forms = new Map<string, MdtFormDetail>();
  private patientNotes = new Map<string, PractitionerNoteItem[]>();
  private batches = new Map<string, BatchStatus>();
  private resources = new Map<string, ResourceDocument>();
  private bugs = new Map<string, BugReportItem>();
  private jobs = new Map<string, QueueJobItem>();
  private gpuLocksCount = 1;
  private agendas = new Map<
    ClinicalDomain,
    {
      sessionDate: string;
      sortStrategy: MdtAgendaSortStrategy;
      deferIncompleteFiles: boolean;
      attendingExperts: string[];
      enrolledPatientIds: string[];
      pinnedMap: Map<string, boolean>;
      updatedAt: string;
    }
  >();

  constructor() {
    this.seed();
  }

  private seed(): void {
    // 1. Oncology: Mme Jeanne FICTIVE (#A-1042) — 3 longitudinal sessions
    const jeanne1: MdtFormDetail = {
      file: "jeanne_fictive_2026_06_03.pdf",
      patientId: "A-1042",
      domain: "oncology",
      mdtDate: "2026-06-03",
      processingStatus: "COMPLETED",
      processingStep: null,
      processingProgressPct: 100,
      sections: {
        PatientAdministrative: {
          first_name: "Jeanne",
          last_name: "FICTIVE",
          date_birth: "1958-03-02",
          date_rcp: "2026-06-03",
          gender: "Female",
        },
        PatientPerformanceStatus: { performance_status: 0 },
        TumorLocation: { tumor_location: "Pancreas" },
        TumorBiology: { msi_state: "MSS", ca19_9: "180 U/mL" },
        RadiologicalExams: {
          exams_list: [
            {
              exam_name: "TDM TAP initial",
              exam_date: "2026-05-25",
              exam_type: "CT",
              exam_result: "Masse céphalique pancréatique 26 mm, cT2 N0 M0.",
            },
          ],
        },
        Chemotherapy: {
          chemotherapy: true,
          chemotherapy_name: "FOLFIRINOX néo-adjuvant (initiation)",
          chemotherapy_start_date: "2026-06-10",
          chemotherapy_tolerance: "Good",
        },
        MTDCompleted: { is_mtd_complete: true, what_missing: [] },
        CareOrientationProposal: {
          care_adaptation_suggested: false,
          suggested_priority: "low",
          proposed_care_type: "Poursuite FOLFIRINOX",
          clinical_rationale: "Bilan complet, induction par FOLFIRINOX selon TNCD Pancréas.",
        },
      },
      manualEdits: {},
      executionTimes: { TumorLocation: 6.2, Chemotherapy: 8.1 },
      metrics: {
        priority_level: "low",
        is_complete: true,
        missing_count: 0,
        missing_items: [],
        care_adaptation_suggested: false,
        proposed_care_type: "Poursuite FOLFIRINOX",
        specialties: ["pancreas expert"],
      },
      markdownText: "# Compte rendu RCP du 03/06/2026\nPatient : Mme Jeanne FICTIVE...",
    };

    const jeanne2: MdtFormDetail = {
      file: "jeanne_fictive_2026_10_14.pdf",
      patientId: "A-1042",
      domain: "oncology",
      mdtDate: "2026-10-14",
      processingStatus: "COMPLETED",
      processingStep: null,
      processingProgressPct: 100,
      sections: {
        PatientAdministrative: {
          first_name: "Jeanne",
          last_name: "FICTIVE",
          date_birth: "1958-03-02",
          date_rcp: "2026-10-14",
          gender: "Female",
        },
        PatientPerformanceStatus: { performance_status: 1 },
        TumorLocation: { tumor_location: "Pancreas" },
        TumorBiology: { msi_state: "MSS", ca19_9: "298 U/mL" },
        RadiologicalExams: {
          exams_list: [
            {
              exam_name: "TDM TAP réévaluation",
              exam_date: "2026-10-02",
              exam_type: "CT",
              exam_result: "Stabilité lésionnelle céphalique, contact VMS < 180°.",
            },
          ],
        },
        Chemotherapy: {
          chemotherapy: true,
          chemotherapy_name: "FOLFIRINOX (4 cures)",
          chemotherapy_start_date: "2026-06-10",
          chemotherapy_tolerance: "Medium",
        },
        MTDCompleted: { is_mtd_complete: true, what_missing: [] },
        CareOrientationProposal: {
          care_adaptation_suggested: false,
          suggested_priority: "medium",
          proposed_care_type: "Réévaluation après 6 cures",
          clinical_rationale: "Élévation modérée du CA 19-9 à 298 U/mL.",
        },
      },
      manualEdits: {},
      executionTimes: { TumorLocation: 7.4, Chemotherapy: 9.0 },
      metrics: {
        priority_level: "medium",
        is_complete: true,
        missing_count: 0,
        missing_items: [],
        care_adaptation_suggested: false,
        proposed_care_type: "Réévaluation après 6 cures",
        specialties: ["pancreas expert"],
      },
      markdownText: "# Compte rendu RCP du 14/10/2026\nPatient : Mme Jeanne FICTIVE...",
    };

    const jeanne3: MdtFormDetail = {
      file: "jeanne_fictive_2026_11_06.pdf",
      patientId: "A-1042",
      domain: "oncology",
      mdtDate: "2026-11-06",
      processingStatus: "COMPLETED",
      processingStep: null,
      processingProgressPct: 100,
      sections: {
        PatientAdministrative: {
          first_name: "Jeanne",
          last_name: "FICTIVE",
          date_birth: "1958-03-02",
          date_rcp: "2026-11-06",
          gender: "Female",
        },
        PatientPerformanceStatus: { performance_status: 1 },
        TumorLocation: {
          tumor_location: "Pancreas",
          stage: "Adénocarcinome tête du pancréas, cT3 N1 M0",
          reasoning_thinking:
            "Le compte rendu du scanner du 28/10/2026 et la synthèse d'oncologie digestive confirment un adénocarcinome canalaire céphalique pancréatique classé cT3 N1 M0 (contact VMS < 180°).",
        },
        TumorBiology: {
          msi_state: "MSS",
          ca19_9: "412 U/mL (+38 % vs 14/10/2026)",
          reasoning_thinking:
            "Statut microsatellite stable (MSS) vérifié sur biopsie initiale. Dosage du marqueur CA 19-9 du 04/11/2026 à 412 U/mL contre 298 U/mL le 14/10/2026 (+38 %).",
        },
        RadiologicalExams: {
          exams_list: [
            {
              exam_name: "TDM TAP de contrôle",
              exam_date: "2026-10-28",
              exam_type: "CT",
              exam_result:
                "Contact veineux mésentérique supérieur < 180° sans thrombose, absence de métastase hépatique.",
            },
          ],
          reasoning_thinking:
            "Extraction structurée de l'examen TDM thoraco-abdomino-pelvien du 28/10/2026 montrant la persistance d'un contact VMS < 180° sans lésion secondaire hépatique.",
        },
        PreviousSurgery: {
          previous_curative_surgery: false,
          reasoning_thinking: "Aucun antécédent de chirurgie d'exérèse pancréatique mentionné.",
        },
        PlannedSurgery: {
          planned_curative_surgery: false,
          reasoning_thinking:
            "Réévaluation chirurgicale différée dans l'attente du contrôle biologique et d'un TEP-TDM.",
        },
        Chemotherapy: {
          chemotherapy: true,
          chemotherapy_name: "FOLFIRINOX modifié, 6 cures (juillet -> octobre 2026)",
          chemotherapy_tolerance: "Neuropathie périphérique grade 1",
          reasoning_thinking:
            "Six cycles de FOLFIRINOX modifié administrés entre juillet et octobre 2026 avec une neuropathie sensitive distale de grade 1.",
        },
        MTDCompleted: {
          is_mtd_complete: false,
          what_missing: [
            "TEP-TDM d'extension (< 4 semaines)",
            "Compte rendu anatomopathologique définitif",
          ],
          mtd_complete: {
            is_mtd_complete: false,
            what_missing: [
              "TEP-TDM d'extension (< 4 semaines)",
              "Compte rendu anatomopathologique définitif",
            ],
            reflection:
              "Le dossier comporte le scanner TAP récent et la biologie CA 19-9, mais le TEP-TDM demandé devant l'ascension du marqueur et la relecture histologique complète manquent avant décision chirurgicale.",
            references: [
              {
                name: "TNCD Pancréas 2026 §3.1",
                page: 9,
                excerpt:
                  "Bilan pré-thérapeutique complet incluant imagerie métabolique si suspicion de progression.",
              },
            ],
          },
          reasoning_thinking:
            "Confrontation des pièces présentes aux prérequis du référentiel TNCD Pancréas : 2 pièces complémentaires sont recommandées avant discussion d'exérèse.",
        },
        ExpertAnswer: {
          "pancreas expert": {
            expert_relevant: true,
            patient_priority: "Patient must be treated urgently",
            why_relevant:
              "Progression biologique sous FOLFIRINOX (CA 19-9 à 412 U/mL) d'un adénocarcinome céphalique borderline.",
            reasoning_thinking:
              "Analyse par l'agent expert Pancréas : l'ascension rapide du CA 19-9 (+38 % en 3 semaines) malgré 6 cures de FOLFIRINOX justifie une discussion prioritaire de changement de ligne (gemcitabine + nab-paclitaxel selon TNCD §4.2) et un TEP-TDM pour exclure des micrométastases.",
            suggestions: [
              {
                suggestion:
                  "Discuter une chimiothérapie de 2e ligne par gemcitabine + nab-paclitaxel, compte tenu de la progression biologique.",
                why: "Schéma recommandé chez les patients OMS 0-1 après 1re ligne par FOLFIRINOX.",
                references: [
                  {
                    name: "TNCD Pancréas §4.2",
                    page: 18,
                    excerpt:
                      "En 2e ligne après FOLFIRINOX, gemcitabine + nab-paclitaxel est proposé chez les patients OMS 0-1.",
                  },
                ],
              },
              {
                suggestion:
                  "Compléter le bilan d'extension par TEP-TDM avant décision chirurgicale.",
                why: "Éliminer une dissémination occulte devant l'ascension du CA 19-9.",
                references: [
                  {
                    name: "CR scanner 28/10/2026",
                    page: 2,
                    excerpt: "Absence de lésion secondaire hépatique visible en TDM.",
                  },
                ],
              },
            ],
            sources_relevant: [
              {
                name: "TNCD Pancréas 2026",
                page: 18,
                excerpt: "Stratégie de 2e ligne après FOLFIRINOX.",
              },
            ],
          },
          Radiotherapy: {
            expert_relevant: true,
            patient_priority: "Patient is not urgent",
            why_relevant: "Évaluation d'une chimioradiothérapie de clôture éventuelle.",
            suggestions: [
              {
                suggestion:
                  "Pas d'indication de radiothérapie immédiate avant réévaluation systémique.",
                why: "Priorité au contrôle systémique devant l'élévation du CA 19-9.",
                references: [],
              },
            ],
            sources_relevant: [],
          },
        },
        CareOrientationProposal: {
          care_adaptation_suggested: true,
          suggested_priority: "high",
          proposed_care_type: "Chimiothérapie 2e ligne (gemcitabine + nab-paclitaxel)",
          clinical_rationale:
            "Progression biologique sous FOLFIRINOX (CA 19-9 +38 %) chez une patiente OMS 1 ; discussion collégiale d'un relais de 2e ligne et compléments d'imagerie (TEP-TDM).",
        },
      },
      manualEdits: {},
      executionTimes: {
        PatientAdministrative: 3.2,
        TumorLocation: 12.4,
        Chemotherapy: 9.8,
        ExpertAnswer: 18.5,
      },
      metrics: {
        priority_level: "high",
        is_complete: false,
        missing_count: 2,
        missing_items: [
          "TEP-TDM d'extension (< 4 semaines)",
          "Compte rendu anatomopathologique définitif",
        ],
        care_adaptation_suggested: true,
        proposed_care_type: "Chimiothérapie 2e ligne (gemcitabine + nab-paclitaxel)",
        specialties: ["pancreas expert", "Radiotherapy"],
      },
      markdownText:
        "# Synthèse RCP du 06/11/2026 — Mme Jeanne FICTIVE (#A-1042)\n\n- **Diagnostic** : Adénocarcinome canalaire céphalique pancréatique cT3 N1 M0\n- **Biologie** : CA 19-9 à 412 U/mL (+38 %)\n- **Traitement reçu** : FOLFIRINOX 6 cures\n",
      chunks: [
        {
          index: 1,
          content:
            "RCP Oncologie Digestive du 06/11/2026 — Patiente : Mme Jeanne FICTIVE, née le 02/03/1958 (#A-1042). OMS 1. Adénocarcinome canalaire de la tête du pancréas cT3 N1 M0.",
          metadata: { page: 1, source: "jeanne_fictive_2026_11_06.pdf" },
        },
        {
          index: 2,
          content:
            "Biologie du 04/11/2026 : CA 19-9 = 412 U/mL (contre 298 U/mL le 14/10/2026, +38 %). Statut MSS. TDM TAP du 28/10/2026 : contact VMS < 180° sans thrombose, pas de métastase hépatique visible.",
          metadata: { page: 1, source: "jeanne_fictive_2026_11_06.pdf" },
        },
        {
          index: 3,
          content:
            "Chimiothérapie reçue : FOLFIRINOX modifié (6 cures de juillet à octobre 2026), tolérance marquée par une neuropathie sensitive grade 1. Discussion collégiale d'une 2e ligne par gemcitabine + nab-paclitaxel et TEP-TDM.",
          metadata: { page: 2, source: "jeanne_fictive_2026_11_06.pdf" },
        },
      ],
    };

    // 2. Oncology: M. Paul MODÈLE (#A-1037)
    const paul: MdtFormDetail = {
      file: "paul_modele_2026_11_06.pdf",
      patientId: "A-1037",
      domain: "oncology",
      mdtDate: "2026-11-06",
      processingStatus: "COMPLETED",
      processingStep: null,
      processingProgressPct: 100,
      sections: {
        PatientAdministrative: {
          first_name: "Paul",
          last_name: "MODÈLE",
          date_birth: "1964-08-19",
          date_rcp: "2026-11-06",
          gender: "Male",
        },
        PatientPerformanceStatus: { performance_status: 0 },
        TumorLocation: {
          tumor_location: "Oesophagus",
          stage: "Adénocarcinome du bas œsophage cT2 N0 M0",
        },
        TumorBiology: { msi_state: "MSS" },
        MTDCompleted: { is_mtd_complete: true, what_missing: [] },
        CareOrientationProposal: {
          care_adaptation_suggested: false,
          suggested_priority: "medium",
          proposed_care_type: "Protocole FLOT péri-opératoire",
          clinical_rationale: "Bilan d'extension complet et conforme au référentiel TNCD Œsophage.",
        },
      },
      manualEdits: {},
      executionTimes: { TumorLocation: 8.2 },
      metrics: {
        priority_level: "medium",
        is_complete: true,
        missing_count: 0,
        missing_items: [],
        care_adaptation_suggested: false,
        proposed_care_type: "Protocole FLOT péri-opératoire",
        specialties: ["oesophagus expert"],
      },
      markdownText:
        "# Synthèse RCP — M. Paul MODÈLE (#A-1037)\nAdénocarcinome bas œsophage cT2N0M0.",
    };

    // 3. SMA: Léo EXEMPLE (#S-0007) — 2 longitudinal sessions
    const leo1: MdtFormDetail = {
      file: "leo_exemple_2026_05_18.pdf",
      patientId: "S-0007",
      domain: "sma",
      mdtDate: "2026-05-18",
      processingStatus: "COMPLETED",
      processingStep: null,
      processingProgressPct: 100,
      sections: {
        PatientAdministrative: {
          first_name: "Léo",
          last_name: "EXEMPLE",
          date_birth: "2018-04-12",
          date_rcp: "2026-05-18",
          gender: "Male",
        },
        GeneticDiagnosis: {
          smn1_deletion_confirmed: true,
          smn2_copy_count: 3,
          other_genetic_variants: "None",
        },
        MotorFunctionStatus: {
          sma_type: "Type 2",
          motor_milestones: ["Sitting unsupported"],
          hfmse_score: 40,
          rulm_score: 26,
        },
        RespiratoryFunction: {
          requires_ventilation_support: false,
          ventilation_type: "None",
          forced_vital_capacity_percent: 74,
        },
        MTDCompleted: { is_mtd_complete: true, what_missing: [] },
        CareOrientationProposal: {
          care_adaptation_suggested: false,
          suggested_priority: "low",
          proposed_care_type: "Poursuite nusinersen intrathécal",
          clinical_rationale: "Stabilité motrice et respiratoire sous nusinersen.",
        },
      },
      manualEdits: {},
      executionTimes: { GeneticDiagnosis: 5.1, MotorFunctionStatus: 7.3 },
      metrics: {
        priority_level: "low",
        is_complete: true,
        missing_count: 0,
        missing_items: [],
        care_adaptation_suggested: false,
        proposed_care_type: "Poursuite nusinersen intrathécal",
        specialties: ["neurologist expert", "pulmonologist expert"],
      },
    };

    const leo2: MdtFormDetail = {
      file: "leo_exemple_2026_11_12.pdf",
      patientId: "S-0007",
      domain: "sma",
      mdtDate: "2026-11-12",
      processingStatus: "COMPLETED",
      processingStep: null,
      processingProgressPct: 100,
      sections: {
        PatientAdministrative: {
          first_name: "Léo",
          last_name: "EXEMPLE",
          date_birth: "2018-04-12",
          date_rcp: "2026-11-12",
          gender: "Male",
        },
        GeneticDiagnosis: {
          smn1_deletion_confirmed: true,
          smn2_copy_count: 3,
          other_genetic_variants: "None",
        },
        MotorFunctionStatus: {
          sma_type: "Type 2",
          motor_milestones: ["Position assise autonome stable"],
          hfmse_score: 42,
          rulm_score: 28,
        },
        RespiratoryFunction: {
          requires_ventilation_support: false,
          ventilation_type: "None",
          uses_cough_assist: true,
          forced_vital_capacity_percent: 72,
        },
        OrthopedicAndSpineStatus: {
          has_scoliosis: true,
          scoliosis_cobb_angle: 18,
          spine_surgery_history: false,
          wheelchair_user: true,
        },
        BulbarAndNutritionalStatus: {
          has_dysphagia: false,
          feeding_mode: "Oral",
          nutritional_status: "Normal",
        },
        MTDCompleted: { is_mtd_complete: true, what_missing: [] },
        ExpertAnswer: {
          "neurologist expert": {
            expert_relevant: true,
            patient_priority: "Patient is not urgent",
            why_relevant: "Suivi longitudinal SMA Type 2 sous nusinersen (+2 pts HFMSE).",
            suggestions: [
              {
                suggestion:
                  "Poursuivre le schéma d'entretien par nusinersen et maintenir la kinésithérapie motrice tri-hebdomadaire.",
                why: "Gain fonctionnel de +2 points au score HFMSE (42/66) et +2 points au RULM (28/37).",
                references: [
                  {
                    name: "PNDS Amyotrophie Spinale 2025 §6.1",
                    page: 24,
                    excerpt: "Évaluation HFMSE et RULM semestrielle sous traitement modificateur.",
                  },
                ],
              },
            ],
            sources_relevant: [],
          },
          "pulmonologist expert": {
            expert_relevant: true,
            patient_priority: "Patient is not urgent",
            why_relevant: "Surveillance de la capacité vitale forcée (CVF à 72 %).",
            suggestions: [
              {
                suggestion:
                  "Maintenir les séances quotidiennes de Cough Assist et contrôler l'oxymétrie nocturne.",
                why: "CVF stable > 70 % sans hypoventilation alvéolaire.",
                references: [],
              },
            ],
            sources_relevant: [],
          },
        },
        CareOrientationProposal: {
          care_adaptation_suggested: false,
          suggested_priority: "low",
          proposed_care_type: "Suivi habituel sous nusinersen + kinésithérapie",
          clinical_rationale:
            "Évolution motrice favorable (+2 pts HFMSE) et stabilité respiratoire (CVF 72 %) conformes au PNDS SMA.",
        },
      },
      manualEdits: {},
      executionTimes: {
        GeneticDiagnosis: 4.8,
        MotorFunctionStatus: 6.9,
        ExpertAnswer: 14.1,
      },
      metrics: {
        priority_level: "low",
        is_complete: true,
        missing_count: 0,
        missing_items: [],
        care_adaptation_suggested: false,
        proposed_care_type: "Suivi habituel sous nusinersen + kinésithérapie",
        specialties: ["neurologist expert", "pulmonologist expert"],
      },
      markdownText:
        "# Synthèse RCP SMA du 12/11/2026 — Léo EXEMPLE (#S-0007)\nSMA Type 2, 3 copies SMN2.",
    };

    for (const f of [jeanne1, jeanne2, jeanne3, paul, leo1, leo2]) {
      this.forms.set(f.file, f);
    }

    this.patientNotes.set("A-1042", [
      {
        practitionerId: "dr.chirurgie",
        practitionerName: "Dr M. Laurent (Chirurgie)",
        content:
          "Vérifier l'extension vasculaire VMS sur le scanner du 28/10 avant de statuer sur la résécabilité.",
        createdAt: "2026-11-05T08:15:00Z",
        updatedAt: "2026-11-05T08:15:00Z",
      },
    ]);

    // Seed Resources
    this.resources.set("TNCD_Pancreas_2026.pdf", {
      filename: "TNCD_Pancreas_2026.pdf",
      sizeBytes: 1_482_900,
      indexed: true,
      chunkCount: 142,
      updatedAt: "2026-10-15",
    });
    this.resources.set("TNCD_Oesophage_Estomac_2026.pdf", {
      filename: "TNCD_Oesophage_Estomac_2026.pdf",
      sizeBytes: 1_190_400,
      indexed: true,
      chunkCount: 118,
      updatedAt: "2026-10-12",
    });
    this.resources.set("PNDS_Amyotrophie_Spinale_SMA_2025.pdf", {
      filename: "PNDS_Amyotrophie_Spinale_SMA_2025.pdf",
      sizeBytes: 980_200,
      indexed: true,
      chunkCount: 94,
      updatedAt: "2026-09-20",
    });

    // Seed Queue Jobs
    this.jobs.set("job-running-1042", {
      jobId: "job-running-1042",
      jobType: "FULL_EXTRACTION",
      status: "RUNNING",
      priority: 1,
      domain: "oncology",
      filename: "jeanne_fictive_2026_11_06.pdf",
      section: "ExpertAnswer",
      progressPct: 68,
      step: "WAVE_3_EXPERTS",
      createdAt: "2026-10-31T11:58:00Z",
      startedAt: "2026-10-31T11:58:10Z",
      completedAt: null,
      error: null,
      preserveManualEdits: true,
    });
    this.jobs.set("job-pending-s008", {
      jobId: "job-pending-s008",
      jobType: "FULL_EXTRACTION",
      status: "PENDING",
      priority: 2,
      domain: "sma",
      filename: "sma_dossier_s0008.pdf",
      section: null,
      progressPct: 0,
      step: "QUEUED",
      createdAt: "2026-10-31T11:59:00Z",
      startedAt: null,
      completedAt: null,
      error: null,
    });
    this.jobs.set("job-failed-1039", {
      jobId: "job-failed-1039",
      jobType: "FULL_EXTRACTION",
      status: "FAILED",
      priority: 2,
      domain: "oncology",
      filename: "courrier_scan_illisible_1039.pdf",
      section: "DocumentParser",
      progressPct: 30,
      step: "OCR_EXTRACTION",
      createdAt: "2026-10-31T11:40:00Z",
      startedAt: "2026-10-31T11:40:05Z",
      completedAt: "2026-10-31T11:40:25Z",
      error: "Document PDF scanné illisible ou protégé.",
    });

    // Seed Bug Reports
    this.bugs.set("BUG-101", {
      id: "BUG-101",
      title: "Unité du CA 19-9 parfois omise sur les comptes rendus scannés",
      description:
        "Sur certains CR de biologie externes, l'unité U/mL n'est pas accolée à la valeur.",
      category: "extraction",
      severity: "low",
      status: "open",
      domain: "oncology",
      patientOrFile: "#A-1042",
      author: "Dr M. Laurent",
      createdAt: "2026-10-29",
    });
    this.bugs.set("BUG-102", {
      id: "BUG-102",
      title: "Affichage du score RULM antérieur dans la frise SMA",
      description: "Souhait d'afficher le delta RULM à côté du HFMSE sur la carte synoptique.",
      category: "ui",
      severity: "medium",
      status: "resolved",
      domain: "sma",
      patientOrFile: "#S-0007",
      author: "Dr C. Moreau",
      createdAt: "2026-10-25",
    });

    this.agendas.set("oncology", {
      sessionDate: "2026-11-13",
      sortStrategy: "hybrid",
      deferIncompleteFiles: false,
      attendingExperts: ["pancreas expert", "oesophagus expert", "hepatocellular expert"],
      enrolledPatientIds: ["A-1042", "A-1037"],
      pinnedMap: new Map(),
      updatedAt: "2026-11-01T18:00:00Z",
    });
    this.agendas.set("sma", {
      sessionDate: "2026-11-19",
      sortStrategy: "hybrid",
      deferIncompleteFiles: false,
      attendingExperts: [
        "neurologist expert",
        "geneticist expert",
        "pulmonologist expert",
        "orthopedist expert",
      ],
      enrolledPatientIds: ["S-0007"],
      pinnedMap: new Map(),
      updatedAt: "2026-11-01T18:00:00Z",
    });
  }

  private formToCard(form: MdtFormDetail, rcpCount = 1): MdtFormCard {
    const admin = (form.sections.PatientAdministrative ?? {}) as Record<string, unknown>;
    const firstName = String(admin.first_name ?? "");
    const lastName = String(admin.last_name ?? form.file);
    const patientName = `${lastName} ${firstName}`.trim();
    const loc = (form.sections.TumorLocation ?? form.sections.MotorFunctionStatus ?? {}) as Record<
      string,
      unknown
    >;
    const summaryText = String(
      loc.stage ??
        loc.tumor_location ??
        loc.sma_type ??
        (form.sections.CareOrientationProposal as Record<string, unknown> | undefined)
          ?.clinical_rationale ??
        "",
    );

    const mtdCompleted = (form.sections.MTDCompleted ?? {}) as Record<string, unknown>;
    const hasMtdCompleted = Object.keys(mtdCompleted).length > 0;
    const isAiCompleted =
      String(form.processingStatus ?? "COMPLETED")
        .trim()
        .toUpperCase() === "COMPLETED";
    const missingItems = Array.isArray(form.metrics.missing_items)
      ? (form.metrics.missing_items as string[])
      : Array.isArray(mtdCompleted.what_missing)
        ? (mtdCompleted.what_missing as string[])
        : [];
    const missingCount =
      typeof form.metrics.missing_count === "number"
        ? form.metrics.missing_count
        : missingItems.length;
    const hideMissingItems = Boolean(form.metrics.hide_missing_items ?? false);
    const isComplete = hideMissingItems
      ? true
      : isAiCompleted &&
        hasMtdCompleted &&
        (typeof form.metrics.is_complete === "boolean"
          ? form.metrics.is_complete
          : missingCount === 0) &&
        missingCount === 0;

    return {
      id: form.patientId ?? form.file,
      file: form.file,
      link: form.link ?? `/files/forms/${encodeURIComponent(form.file)}/pdf`,
      patientId: form.patientId,
      patientName,
      firstName,
      lastName,
      dateBirth: admin.date_birth ? String(admin.date_birth) : null,
      gender: admin.gender ? String(admin.gender) : null,
      domain: form.domain,
      mdtDate: form.mdtDate,
      priorityLevel: normalizePriorityLevel(form.metrics.priority_level),
      isComplete,
      missingCount,
      missingItems,
      careAdaptationSuggested:
        typeof form.metrics.care_adaptation_suggested === "boolean"
          ? form.metrics.care_adaptation_suggested
          : null,
      proposedCareType: form.metrics.proposed_care_type
        ? String(form.metrics.proposed_care_type)
        : null,
      specialties: Array.isArray(form.metrics.specialties)
        ? (form.metrics.specialties as string[])
        : [],
      processingStatus: form.processingStatus,
      processingStep: form.processingStep,
      processingProgressPct: form.processingProgressPct,
      rcpCount,
      summaryText,
    };
  }

  async listPatientCards(domain: ClinicalDomain): Promise<MdtFormCard[]> {
    const byPatient = new Map<string, MdtFormDetail[]>();
    for (const form of this.forms.values()) {
      if (form.domain !== domain && domain) continue;
      const key = form.patientId ?? form.file;
      const list = byPatient.get(key) ?? [];
      list.push(form);
      byPatient.set(key, list);
    }
    const cards: MdtFormCard[] = [];
    for (const [, list] of byPatient) {
      const sorted = [...list].sort((a, b) => (b.mdtDate ?? "").localeCompare(a.mdtDate ?? ""));
      const latest = sorted[0];
      if (latest) {
        cards.push(this.formToCard(latest, sorted.length));
      }
    }
    return cards;
  }

  async listRcpCards(domain: ClinicalDomain): Promise<MdtFormCard[]> {
    const cards: MdtFormCard[] = [];
    for (const form of this.forms.values()) {
      if (form.domain !== domain) continue;
      cards.push(this.formToCard(form, 1));
    }
    return cards;
  }

  async listPatients(domain: ClinicalDomain): Promise<PatientListItem[]> {
    const cards = await this.listPatientCards(domain);
    return cards.map((c) => ({
      id: c.patientId ?? c.id,
      firstName: c.firstName,
      lastName: c.lastName,
      dateBirth: c.dateBirth,
      gender: c.gender,
      rcpCount: c.rcpCount,
    }));
  }

  async deletePatient(patientId: string, _domain: ClinicalDomain): Promise<void> {
    for (const [file, form] of this.forms.entries()) {
      if (form.patientId === patientId || file === patientId) {
        this.forms.delete(file);
      }
    }
  }

  async deleteForm(filename: string, _domain: ClinicalDomain): Promise<void> {
    this.forms.delete(filename);
  }

  async getDomainSchema(domain: ClinicalDomain): Promise<DomainFormSchema> {
    return buildDefaultDomainFormSchema(domain);
  }

  async resolveTarget(
    target: string,
    _domain: ClinicalDomain,
  ): Promise<{
    kind: "patient" | "form";
    patientId?: string | null;
    filename?: string | null;
  }> {
    if (this.forms.has(target)) {
      const form = this.forms.get(target)!;
      return { kind: "form", filename: form.file, patientId: form.patientId };
    }
    for (const form of this.forms.values()) {
      if (form.patientId === target) {
        return { kind: "patient", patientId: target, filename: form.file };
      }
    }
    return { kind: "patient", patientId: target, filename: null };
  }

  async getFormDetail(filename: string, _domain: ClinicalDomain): Promise<MdtFormDetail | null> {
    return this.forms.get(filename) ?? null;
  }

  async getPatientForms(patientId: string, _domain: ClinicalDomain): Promise<MdtFormDetail[]> {
    const list: MdtFormDetail[] = [];
    for (const form of this.forms.values()) {
      if (form.patientId === patientId || form.file === patientId) {
        list.push(form);
      }
    }
    return list.sort((a, b) => (a.mdtDate ?? "").localeCompare(b.mdtDate ?? ""));
  }

  async updateFormSection(
    filename: string,
    section: string,
    data: Record<string, unknown>,
    editedBy: string,
    domain: ClinicalDomain,
  ): Promise<MdtFormDetail> {
    const form = this.forms.get(filename);
    if (!form) {
      throw new Error(`Form not found: ${filename}`);
    }
    const previousSectionObj = { ...(form.sections[section] ?? {}) };
    const originalAiObj =
      (form.manualEdits[section]?.previous_ai_value as Record<string, unknown> | undefined) ??
      previousSectionObj;
    const domainSchema = await this.getDomainSchema(domain);
    const coerced = coerceSectionUpdatePayload(section, data, previousSectionObj, domainSchema);
    const modifiedFields: Record<string, { ai_value?: unknown; human_value?: unknown }> =
      form.manualEdits[section]?.modified_fields ?? {};
    for (const [k, v] of Object.entries(coerced)) {
      if (JSON.stringify(previousSectionObj[k]) !== JSON.stringify(v)) {
        modifiedFields[k] = {
          ai_value: modifiedFields[k]?.ai_value ?? originalAiObj[k],
          human_value: v,
        };
      }
    }
    form.sections[section] = {
      ...previousSectionObj,
      ...coerced,
    };
    form.manualEdits[section] = {
      is_manual: true,
      edited_at: new Date().toISOString(),
      edited_by: editedBy,
      previous_ai_value: originalAiObj,
      modified_fields: modifiedFields,
    };
    return form;
  }

  async updateMissingItems(
    filename: string,
    input: MissingItemsUpdateInput,
    _domain: ClinicalDomain,
  ): Promise<MdtFormDetail> {
    const form = this.forms.get(filename);
    if (!form) {
      throw new Error(`Form not found: ${filename}`);
    }
    const mtdComp = (form.sections.MTDCompleted ?? {}) as Record<string, unknown>;
    const rawAll: string[] = Array.isArray(form.metrics.all_missing_items)
      ? [...form.metrics.all_missing_items]
      : Array.isArray(mtdComp.what_missing)
        ? (mtdComp.what_missing as string[]).map(String)
        : Array.isArray(form.metrics.missing_items)
          ? [...form.metrics.missing_items]
          : [];
    const nextAll = input.whatMissing ? [...input.whatMissing] : rawAll;
    let hidden: string[] = Array.isArray(form.metrics.hidden_missing_items)
      ? [...form.metrics.hidden_missing_items]
      : [];
    if (input.hiddenMissingItems) {
      hidden = [...input.hiddenMissingItems];
    }
    if (input.toggleItem) {
      const idx = hidden.indexOf(input.toggleItem);
      if (idx >= 0) {
        hidden.splice(idx, 1);
      } else {
        hidden.push(input.toggleItem);
      }
    }
    const hideAll =
      input.hideMissingItems !== undefined
        ? Boolean(input.hideMissingItems)
        : Boolean(form.metrics.hide_missing_items);
    const hiddenSet = new Set(hidden);
    const visible = hideAll ? [] : nextAll.filter((x) => !hiddenSet.has(x));

    form.sections.MTDCompleted = {
      ...mtdComp,
      what_missing: nextAll,
      is_mtd_complete: visible.length === 0,
    };
    form.metrics = {
      ...form.metrics,
      all_missing_items: nextAll,
      hidden_missing_items: hidden,
      hide_missing_items: hideAll,
      missing_items: visible,
      missing_count: visible.length,
      is_complete: visible.length === 0,
    };
    return form;
  }

  async rollbackSection(
    filename: string,
    section: string,
    _domain: ClinicalDomain,
  ): Promise<MdtFormDetail> {
    const form = this.forms.get(filename);
    if (!form) {
      throw new Error(`Form ${filename} not found`);
    }
    const canonical = resolveCanonicalSectionName(section);
    const existingMeta = form.manualEdits[section] ?? form.manualEdits[canonical];
    const aiOriginal =
      existingMeta?.previous_ai_value ??
      (existingMeta as Record<string, unknown> | undefined)?.ai_original;
    if (aiOriginal && typeof aiOriginal === "object" && !Array.isArray(aiOriginal)) {
      const targetKey = form.sections[section] !== undefined ? section : canonical;
      form.sections[targetKey] = { ...(aiOriginal as Record<string, unknown>) };
    }
    delete form.manualEdits[section];
    delete form.manualEdits[canonical];
    return form;
  }

  async rerunSection(
    filename: string,
    section: string,
    preserveManualEdits: boolean,
    domain: ClinicalDomain,
  ): Promise<{ jobId: string; preserveManualEdits: boolean }> {
    const form = this.forms.get(filename);
    if (form && !preserveManualEdits) {
      const canonical = resolveCanonicalSectionName(section);
      const existingMeta = form.manualEdits[section] ?? form.manualEdits[canonical];
      const aiOriginal =
        existingMeta?.previous_ai_value ??
        (existingMeta as Record<string, unknown> | undefined)?.ai_original;
      if (aiOriginal && typeof aiOriginal === "object" && !Array.isArray(aiOriginal)) {
        const targetKey = form.sections[section] !== undefined ? section : canonical;
        form.sections[targetKey] = {
          ...(aiOriginal as Record<string, unknown>),
        };
      }
      delete form.manualEdits[section];
      delete form.manualEdits[canonical];
    }
    const jobId = `job-rerun-${Date.now()}`;
    this.jobs.set(jobId, {
      jobId,
      jobType: "SECTION_RERUN",
      status: "COMPLETED",
      priority: 1,
      domain,
      filename,
      section,
      progressPct: 100,
      step: "COMPLETED",
      createdAt: new Date().toISOString(),
      startedAt: new Date().toISOString(),
      completedAt: new Date().toISOString(),
      error: null,
      preserveManualEdits,
    });
    return { jobId, preserveManualEdits };
  }

  async processFullForm(
    filename: string,
    preserveManualEdits: boolean,
    domain: ClinicalDomain,
  ): Promise<{ jobId: string }> {
    const form = this.forms.get(filename);
    if (form) {
      form.processingStatus = "PROCESSING_ADMIN";
      form.processingStep = "WAVE_1_ADMIN";
      form.processingProgressPct = 25;
      form.metrics.is_complete = false;
      if (!preserveManualEdits) {
        form.manualEdits = {};
      }
    }
    const jobId = `job-full-${Date.now()}`;
    this.jobs.set(jobId, {
      jobId,
      jobType: "FULL_EXTRACTION",
      status: "RUNNING",
      priority: 1,
      domain,
      filename,
      section: null,
      progressPct: 25,
      step: "WAVE_1_ADMIN",
      createdAt: new Date().toISOString(),
      startedAt: new Date().toISOString(),
      completedAt: null,
      error: null,
      preserveManualEdits,
    });
    return { jobId };
  }

  async linkFormToPatient(
    filename: string,
    patientId: string | null,
    _domain: ClinicalDomain,
  ): Promise<void> {
    const form = this.forms.get(filename);
    if (form) {
      form.patientId = patientId;
    }
  }

  async getFormPdfBuffer(
    filename: string,
    _domain: ClinicalDomain,
    _variant?: "plain" | "bbox",
  ): Promise<Buffer | null> {
    const form = this.forms.get(filename);
    if (!form) return MINIMAL_PDF_BUFFER;
    const admin = (form.sections.Administrative ?? {}) as Record<string, unknown>;
    const patientLabel =
      [admin.last_name, admin.first_name].filter(Boolean).join(" ") || form.patientId || form.file;
    const subtitle = `Patient : ${patientLabel}  |  Fichier : ${form.file}${form.mdtDate ? `  |  Seance RCP : ${form.mdtDate}` : ""}`;
    const lines = wrapPdfLines(
      form.markdownText ||
        `Dossier clinique ${patientLabel}\nFichier source : ${form.file}\nDate RCP : ${form.mdtDate ?? "Non renseignee"}`,
    );
    return buildClinicalPdfBuffer("DataSyntis — Fiche Source RCP / MDT", subtitle, lines);
  }

  async askDossierQuestion(
    target: { filename?: string; patientId?: string },
    question: string,
    domain: ClinicalDomain,
    language: Language,
  ): Promise<ChatReply> {
    const refDoc =
      target.filename ||
      (domain === "sma" ? "leo_exemple_2026_11_12.pdf" : "jeanne_fictive_2026_11_06.pdf");
    if (domain === "sma") {
      return {
        answer:
          language === "fr"
            ? `D'après le dossier longitudinal (#S-0007), le score HFMSE est passé de 40/66 (18/05/2026) à 42/66 (12/11/2026) sous nusinersen, avec une capacité vitale forcée (CVF) stable à 72 % pour votre question : « ${question} ».`
            : "Based on longitudinal record #S-0007, the HFMSE score improved from 40/66 to 42/66 under nusinersen with FVC at 72%.",
        references: [
          {
            name: refDoc,
            page: 1,
            excerpt: "HFMSE 42/66 (+2 pts), RULM 28/37, CVF 72 % de la théorique.",
          },
          {
            name: "PNDS Amyotrophie Spinale 2025 §6.1",
            page: 24,
            excerpt: "Suivi semestriel HFMSE / RULM et EFR.",
          },
        ],
      };
    }
    return {
      answer:
        language === "fr"
          ? `Le CA 19-9 est passé de 298 U/mL (14/10/2026) à 412 U/mL (06/11/2026), soit une hausse de +38 % après 6 cures de FOLFIRINOX (question : « ${question} »).`
          : "CA 19-9 increased from 298 U/mL (2026-10-14) to 412 U/mL (2026-11-06), +38% after 6 cycles of FOLFIRINOX.",
      references: [
        {
          name: refDoc,
          page: 1,
          excerpt: "CA 19-9 : 412 U/mL (+38 % vs 14/10/2026). Contact VMS < 180°.",
        },
        {
          name: "TNCD Pancréas §4.2",
          page: 18,
          excerpt: "Discussion d'une 2e ligne par gemcitabine + nab-paclitaxel.",
        },
      ],
    };
  }

  private resolvePatientKey(patientIdOrFile: string): string {
    const form = this.forms.get(patientIdOrFile);
    if (form?.patientId) return form.patientId;
    return patientIdOrFile;
  }

  async getPatientNotes(
    patientIdOrFile: string,
    _domain: ClinicalDomain,
  ): Promise<PractitionerNoteItem[]> {
    const key = this.resolvePatientKey(patientIdOrFile);
    return [...(this.patientNotes.get(key) ?? [])];
  }

  async upsertPatientNote(
    patientIdOrFile: string,
    input: {
      practitionerId: string;
      practitionerName: string;
      content: string;
    },
    _domain: ClinicalDomain,
  ): Promise<PractitionerNoteItem[]> {
    const key = this.resolvePatientKey(patientIdOrFile);
    const normId = input.practitionerId.trim().toLowerCase();
    const trimmedContent = input.content.trim();
    if (!normId || !trimmedContent) {
      throw new Error("Invalid practitioner note input");
    }
    const now = new Date().toISOString();
    const existingList = this.patientNotes.get(key) ?? [];
    const existingNote = existingList.find((n) => n.practitionerId.toLowerCase() === normId);
    const others = existingList.filter((n) => n.practitionerId.toLowerCase() !== normId);
    const updated: PractitionerNoteItem = {
      practitionerId: normId,
      practitionerName: input.practitionerName.trim() || normId,
      content: trimmedContent.slice(0, 2000),
      createdAt: existingNote?.createdAt ?? now,
      updatedAt: now,
    };
    const nextList = [updated, ...others];
    this.patientNotes.set(key, nextList);
    return [...nextList];
  }

  async deletePatientNote(
    patientIdOrFile: string,
    practitionerId: string,
    _domain: ClinicalDomain,
  ): Promise<PractitionerNoteItem[]> {
    const key = this.resolvePatientKey(patientIdOrFile);
    const normId = practitionerId.trim().toLowerCase();
    const existingList = this.patientNotes.get(key) ?? [];
    const nextList = existingList.filter((n) => n.practitionerId.toLowerCase() !== normId);
    this.patientNotes.set(key, nextList);
    return [...nextList];
  }

  async uploadForms(
    files: UploadFileInput[],
    batchId: string,
    domain: ClinicalDomain,
  ): Promise<{ batchId: string; filenames: string[] }> {
    const filenames: string[] = [];
    const batchFiles = files.map((f) => {
      filenames.push(f.filename);
      const pid = f.patientId || (domain === "sma" ? "S-0007" : "A-1042");
      const newForm: MdtFormDetail = {
        file: f.filename,
        patientId: pid,
        domain,
        mdtDate: new Date().toISOString().slice(0, 10),
        processingStatus: "COMPLETED",
        processingStep: null,
        processingProgressPct: 100,
        sections: {
          PatientAdministrative: {
            first_name: domain === "sma" ? "Léo" : "Jeanne",
            last_name: domain === "sma" ? "EXEMPLE" : "FICTIVE",
            date_rcp: new Date().toISOString().slice(0, 10),
          },
          MTDCompleted: { is_mtd_complete: true, what_missing: [] },
          CareOrientationProposal: {
            care_adaptation_suggested: false,
            suggested_priority: "medium",
            proposed_care_type: "Analyse initiale terminée",
            clinical_rationale: "Document importé et structuré automatiquement.",
          },
        },
        manualEdits: {},
        executionTimes: { DocumentParser: 2.1 },
        metrics: {
          priority_level: "medium",
          is_complete: true,
          missing_count: 0,
          missing_items: [],
          care_adaptation_suggested: false,
          proposed_care_type: "Analyse initiale terminée",
          specialties: domain === "sma" ? ["neurologist expert"] : ["pancreas expert"],
        },
      };
      this.forms.set(f.filename, newForm);
      return {
        filename: f.filename,
        status: "COMPLETED",
        step: "COMPLETED",
        progressPct: 100,
        error: null,
        patientId: pid,
      };
    });

    this.batches.set(batchId, {
      batchId,
      total: batchFiles.length,
      completed: batchFiles.length,
      running: 0,
      pending: 0,
      failed: 0,
      progressPct: 100,
      files: batchFiles,
    });

    return { batchId, filenames };
  }

  async getBatchStatus(batchId: string, _domain: ClinicalDomain): Promise<BatchStatus> {
    return (
      this.batches.get(batchId) ?? {
        batchId,
        total: 0,
        completed: 0,
        running: 0,
        pending: 0,
        failed: 0,
        progressPct: 0,
        files: [],
      }
    );
  }

  async listResources(_domain: ClinicalDomain): Promise<ResourceDocument[]> {
    return Array.from(this.resources.values());
  }

  async uploadResource(
    filename: string,
    content: Buffer,
    _domain: ClinicalDomain,
  ): Promise<ResourceDocument> {
    const doc: ResourceDocument = {
      filename,
      sizeBytes: content.byteLength || 512_000,
      indexed: true,
      chunkCount: 64,
      updatedAt: new Date().toISOString().slice(0, 10),
    };
    this.resources.set(filename, doc);
    return doc;
  }

  async reindexResource(filename: string, _domain: ClinicalDomain): Promise<void> {
    const doc = this.resources.get(filename);
    if (doc) {
      doc.indexed = true;
      doc.updatedAt = new Date().toISOString().slice(0, 10);
    }
  }

  async deleteResource(filename: string, _domain: ClinicalDomain): Promise<void> {
    this.resources.delete(filename);
  }

  async getResourcePdfBuffer(
    filename: string,
    domain: ClinicalDomain,
    _formFile?: string,
  ): Promise<Buffer | null> {
    const res = this.resources.get(filename);
    const domainLabel =
      domain === "sma"
        ? "PNDS — Maladies Neuromusculaires Rares (SMA)"
        : "Referentiel Scientifique TNCD — Oncologie Digestive";
    const lines = wrapPdfLines(
      [
        `Document referentiel : ${filename}`,
        `Domaine : ${domainLabel}`,
        `Statut RAG : ${res?.indexed ? "Indexe dans la base vectorielle locale" : "En attente d'indexation"}`,
        `Derniere mise a jour : ${res?.updatedAt ?? "2026-10-15"}`,
        "",
        "Synthese des recommandations cliniques de reference :",
        "- Verification collegiale des criteres d'eligibilite therapeutique en seance RCP.",
        "- Controle systematique de la completude du bilan pre-therapeutique (imagerie, biologie, anatomopathologie / genetique).",
        "- Toute proposition d'orientation pre-RCP doit etre validee par le college medical.",
      ].join("\n"),
    );
    return buildClinicalPdfBuffer(`DataSyntis — ${domainLabel}`, `Fichier : ${filename}`, lines);
  }

  async listAgents(domain: ClinicalDomain, language: Language): Promise<AgentModuleInfo[]> {
    const rawAgents =
      domain === "sma"
        ? [
            {
              name: "Administrative",
              role: "Extraction structurée de l'identité patient, du génotype SMN1/SMN2 et des scores fonctionnels neuromusculaires.",
              guidelines: ["PNDS_Amyotrophie_Spinale_SMA_2025.pdf"],
              models: ["mistral-nemo (temp=0.0)"],
              systemPrompt:
                "Tu es un assistant médical spécialisé en maladies neuromusculaires rares (Amyotrophie Spinale SMA). Extrais fidèlement chaque champ clinique à partir du dossier sans jamais inventer de valeur absente.",
            },
            {
              name: "neurologist expert",
              role: "Évaluation motrice (HFMSE, RULM, CHOP-INTEND) et traitements modificateurs (nusinersen, risdiplam, thérapie génique).",
              guidelines: ["PNDS_Amyotrophie_Spinale_SMA_2025.pdf"],
              models: ["mistral-nemo (temp=0.1)", "bge-m3 (RAG)"],
              systemPrompt:
                "Tu es neuropédiatre / neurologue référent en centre de référence maladies neuromusculaires (FILNEMUS). Analyse l'évolution des scores moteurs (HFMSE, RULM, CHOP-INTEND) et propose des pistes de discussion conformes au PNDS Amyotrophie Spinale.",
            },
            {
              name: "geneticist expert",
              role: "Confirmation moléculaire SMN1 et corrélation génotype-phénotype (copies SMN2).",
              guidelines: ["PNDS_Amyotrophie_Spinale_SMA_2025.pdf"],
              models: ["mistral-nemo (temp=0.1)"],
              systemPrompt:
                "Tu es médecin généticien moléculaire. Vérifie la confirmation de la délétion homozygote de l'exon 7 de SMN1, le nombre de copies de SMN2 et les éventuels variants modificateurs.",
            },
            {
              name: "pulmonologist expert",
              role: "Surveillance de la capacité vitale forcée (CVF), VNI nocturne et désencombrement mécanique (Cough Assist).",
              guidelines: ["PNDS_Amyotrophie_Spinale_SMA_2025.pdf"],
              models: ["mistral-nemo (temp=0.1)", "bge-m3 (RAG)"],
              systemPrompt:
                "Tu es pneumologue référent SMA. Évalue la fonction respiratoire (CVF %, oxymétrie nocturne, besoin de VNI BiPAP et d'aide mécanique à la toux) selon le PNDS.",
            },
            {
              name: "orthopedist expert",
              role: "Suivi rachidien (angle de Cobb, corset, arthrodèse) et rétractions articulaires.",
              guidelines: ["PNDS_Amyotrophie_Spinale_SMA_2025.pdf"],
              models: ["mistral-nemo (temp=0.1)"],
              systemPrompt:
                "Tu es chirurgien orthopédiste pédiatrique / MPR. Surveille l'évolution de la scoliose (angle de Cobb), le port de corset et les indications d'arthrodèse vertébrale.",
            },
          ]
        : [
            {
              name: "Administrative",
              role: "Extraction structurée des données administratives, du statut OMS, de l'anatomopathologie, de l'imagerie et des lignes de chimiothérapie.",
              guidelines: ["TNCD_Pancreas_2026.pdf", "TNCD_Oesophage_Estomac_2026.pdf"],
              models: ["mistral-nemo (temp=0.0)", "granite3.2-vision (OCR)"],
              systemPrompt:
                "Tu es un assistant d'extraction clinique en oncologie digestive. Extrais chaque rubrique du dossier patient avec ancrage strict dans les pièces sources, sans extrapoler.",
            },
            {
              name: "pancreas expert",
              role: "Stratégie médico-chirurgicale des adénocarcinomes pancréatiques résécables, borderline et localement avancés.",
              guidelines: ["TNCD_Pancreas_2026.pdf"],
              models: ["mistral-nemo (temp=0.1)", "bge-m3 (RAG Milvus)"],
              systemPrompt:
                "Tu es oncologue digestif et chirurgien hépato-bilio-pancréatique. Confronte le dossier aux recommandations du TNCD Pancréas en citant systématiquement les chapitres et les pièces du dossier.",
            },
            {
              name: "oesophagus expert",
              role: "Prise en charge des cancers œso-gastriques (FLOT péri-opératoire, radiochimiothérapie, immunothérapie).",
              guidelines: ["TNCD_Oesophage_Estomac_2026.pdf"],
              models: ["mistral-nemo (temp=0.1)", "bge-m3 (RAG Milvus)"],
              systemPrompt:
                "Tu es spécialiste des cancers œso-gastriques. Formule des propositions pré-RCP argumentées selon le référentiel TNCD Œsophage / Estomac.",
            },
            {
              name: "hepatocellular expert",
              role: "Carcinome hépatocellulaire (classification BCLC, transplantation, TACE, traitements systémiques).",
              guidelines: ["TNCD_Pancreas_2026.pdf"],
              models: ["mistral-nemo (temp=0.1)", "bge-m3 (RAG Milvus)"],
              systemPrompt:
                "Tu es hépatologue et oncologue digestif spécialisé dans le carcinome hépatocellulaire (CHC). Évalue le score Child-Pugh, le stade BCLC et les options médico-chirurgicales selon le TNCD.",
            },
            {
              name: "MDT Coordinator",
              role: "Synthèse pré-RCP non prescriptive, contrôle de complétude et priorisation collégiale des dossiers.",
              guidelines: ["TNCD_Pancreas_2026.pdf", "TNCD_Oesophage_Estomac_2026.pdf"],
              models: ["mistral-nemo (temp=0.0)"],
              systemPrompt:
                "Tu es le coordinateur médical de la RCP. Vérifie la complétude du dossier, synthétise les avis d'experts et propose un niveau de priorité de passage non prescriptif.",
            },
          ];

    return rawAgents.map((a) => {
      const pres = getAgentPresentation(a.name, language);
      return {
        name: a.name,
        label: pres.label,
        icon: pres.icon,
        role: a.role,
        description: a.role,
        guidelines: a.guidelines,
        models: a.models,
        systemPrompt: a.systemPrompt,
        userPrompts: getDomainUserPromptsForAgent(a.name, domain, language),
      };
    });
  }

  async askGuidelineQuestion(
    question: string,
    domain: ClinicalDomain,
    language: Language,
  ): Promise<ChatReply> {
    if (domain === "sma") {
      return {
        answer:
          language === "fr"
            ? `Selon le PNDS Amyotrophie Spinale (§6.1), le suivi repose sur l'évaluation semestrielle des échelles HFMSE et RULM ainsi que la mesure de la CVF et l'oxymétrie nocturne (question : « ${question} »).`
            : "According to the SMA PNDS guideline (§6.1), follow-up relies on biannual HFMSE/RULM motor scales and FVC respiratory monitoring.",
        references: [
          {
            name: "PNDS_Amyotrophie_Spinale_SMA_2025.pdf",
            page: 24,
            position: "§6.1 Suivi multidisciplinaire",
            excerpt:
              "Évaluation motrice standardisée (HFMSE, RULM) et exploration fonctionnelle respiratoire tous les 6 mois.",
          },
        ],
      };
    }
    return {
      answer:
        language === "fr"
          ? `Selon le référentiel TNCD Pancréas (§4.2), après échec ou progression sous une 1re ligne par FOLFIRINOX chez un patient OMS 0–1, une association gemcitabine + nab-paclitaxel est proposée à la discussion collégiale (question : « ${question} »).`
          : "According to TNCD Pancreas (§4.2), after progression on first-line FOLFIRINOX in WHO 0-1 patients, gemcitabine + nab-paclitaxel is proposed for MDT discussion.",
      references: [
        {
          name: "TNCD_Pancreas_2026.pdf",
          page: 18,
          position: "§4.2 Traitement de 2e ligne",
          excerpt:
            "En 2e ligne après FOLFIRINOX, une association gemcitabine + nab-paclitaxel est recommandée chez les patients OMS 0–1.",
        },
      ],
    };
  }

  async listBugs(_domain: ClinicalDomain): Promise<BugReportItem[]> {
    return Array.from(this.bugs.values());
  }

  async createBug(
    input: Omit<BugReportItem, "id" | "createdAt" | "status">,
  ): Promise<BugReportItem> {
    const id = `BUG-${100 + this.bugs.size + 1}`;
    const item: BugReportItem = {
      ...input,
      id,
      status: "open",
      createdAt: new Date().toISOString().slice(0, 10),
    };
    this.bugs.set(id, item);
    return item;
  }

  async updateBugStatus(
    id: string,
    status: string,
    _domain: ClinicalDomain,
  ): Promise<BugReportItem> {
    const bug = this.bugs.get(id);
    if (!bug) {
      throw new Error(`Bug not found: ${id}`);
    }
    bug.status = status;
    return bug;
  }

  async deleteBug(id: string, _domain: ClinicalDomain): Promise<void> {
    this.bugs.delete(id);
  }

  async getQueueStats(domain: ClinicalDomain, allDomains = true): Promise<QueueStats> {
    const jobs = await this.listQueueJobs(domain, allDomains);
    const pending = jobs.filter((j) => j.status === "PENDING").length;
    const running = jobs.filter((j) => j.status === "RUNNING").length;
    const completed = jobs.filter((j) => j.status === "COMPLETED").length;
    const failed = jobs.filter((j) => j.status === "FAILED").length;
    const cancelled = jobs.filter((j) => j.status === "CANCELLED").length;
    const active = jobs.find((j) => j.status === "RUNNING") ?? null;

    return {
      pending,
      running,
      completed,
      failed,
      cancelled,
      total: jobs.length,
      activeFormFile: active?.filename ?? null,
      activeStep: active?.step ?? null,
      activeProgressPct: active?.progressPct ?? 0,
      thinkingPreview: active
        ? "Analyse collégiale des critères TNCD Pancréas §4.2 et corrélation CA 19-9…"
        : null,
      gpuLocksCount: this.gpuLocksCount,
    };
  }

  async listQueueJobs(domain: ClinicalDomain, allDomains = true): Promise<QueueJobItem[]> {
    const all = Array.from(this.jobs.values());
    if (allDomains) return all;
    return all.filter((j) => j.domain === domain);
  }

  async retryQueueJob(jobId: string, _domain: ClinicalDomain): Promise<void> {
    const job = this.jobs.get(jobId);
    if (job) {
      job.status = "PENDING";
      job.error = null;
      job.progressPct = 0;
      job.step = "QUEUED";
    }
  }

  async cancelOrDeleteQueueJob(jobId: string, _domain: ClinicalDomain): Promise<void> {
    this.jobs.delete(jobId);
  }

  async cleanQueue(mode: "completed" | "failed" | "all", _domain: ClinicalDomain): Promise<number> {
    let removed = 0;
    for (const [id, job] of this.jobs.entries()) {
      if (
        mode === "all" ||
        (mode === "completed" && job.status === "COMPLETED") ||
        (mode === "failed" && job.status === "FAILED")
      ) {
        this.jobs.delete(id);
        removed += 1;
      }
    }
    return removed;
  }

  async releaseGpuLocks(_domain: ClinicalDomain): Promise<{ released: number }> {
    const released = this.gpuLocksCount;
    this.gpuLocksCount = 0;
    return { released };
  }

  private getDomainAvailableExperts(domain: ClinicalDomain): string[] {
    return domain === "sma"
      ? [
          "neurologist expert",
          "geneticist expert",
          "pulmonologist expert",
          "physiotherapy expert",
          "orthopedist expert",
        ]
      : ["pancreas expert", "oesophagus expert", "hepatocellular expert"];
  }

  private ensureAgendaState(domain: ClinicalDomain) {
    let st = this.agendas.get(domain);
    if (!st) {
      const avail = this.getDomainAvailableExperts(domain);
      const defaultIds = Array.from(
        new Set(
          Array.from(this.forms.values())
            .filter((f) => f.domain === domain)
            .map((f) => f.patientId ?? f.file),
        ),
      );
      st = {
        sessionDate: "2026-11-13",
        sortStrategy: "hybrid",
        deferIncompleteFiles: false,
        attendingExperts: [...avail],
        enrolledPatientIds: defaultIds,
        pinnedMap: new Map(),
        updatedAt: new Date().toISOString(),
      };
      this.agendas.set(domain, st);
    }
    return st;
  }

  async getMdtAgenda(domain: ClinicalDomain): Promise<MdtAgendaView> {
    const st = this.ensureAgendaState(domain);
    const availableExperts = this.getDomainAvailableExperts(domain);
    const attendingSet = new Set(st.attendingExperts);
    const allCards = await this.listPatientCards(domain);
    const cardMap = new Map<string, MdtFormCard>();
    for (const c of allCards) {
      cardMap.set(c.patientId ?? c.id, c);
    }

    const enrolledSet = new Set(st.enrolledPatientIds);
    const rawItems: MdtAgendaItem[] = [];

    for (const pid of st.enrolledPatientIds) {
      const card = cardMap.get(pid);
      if (!card) continue;
      const reqExperts = card.specialties.filter((s) => availableExperts.includes(s));
      const effectiveReq = reqExperts.length > 0 ? reqExperts : card.specialties;
      const presentReq = effectiveReq.filter((e) => attendingSet.has(e));
      const absentReq = effectiveReq.filter((e) => !attendingSet.has(e));
      const quorumMet = absentReq.length === 0;
      const coverage = effectiveReq.length > 0 ? presentReq.length / effectiveReq.length : 1.0;
      const clusterKey = presentReq[0] ?? effectiveReq[0] ?? "general";
      const urgencyScore =
        card.priorityLevel === "high" ? 2 : card.priorityLevel === "medium" ? 1 : 0;
      const urgencyLabel =
        card.priorityLevel === "high"
          ? "Urgent"
          : card.priorityLevel === "medium"
            ? "Semi-urgent"
            : "Standard";
      const pinned = Boolean(st.pinnedMap.get(pid));

      const reasons: string[] = [];
      if (pinned) reasons.push("Position épinglée manuellement");
      if (card.priorityLevel === "high") reasons.push("Priorité haute");
      else if (card.priorityLevel === "medium") reasons.push("Priorité modérée");
      else reasons.push("Priorité standard");

      if (effectiveReq.length > 0) {
        if (quorumMet) {
          reasons.push(`Quorum complet (${presentReq.length}/${effectiveReq.length})`);
        } else {
          reasons.push(`Quorum partiel (${presentReq.length}/${effectiveReq.length})`);
        }
      }
      if (!card.isComplete && st.deferIncompleteFiles) {
        reasons.push(`Dossier incomplet (${card.missingCount} manquante(s))`);
      } else if (card.careAdaptationSuggested) {
        reasons.push("Adaptation suggérée");
      }

      rawItems.push({
        position: 0,
        patientId: pid,
        filename: card.file,
        patientName: card.patientName,
        firstName: card.firstName,
        lastName: card.lastName,
        dateBirth: card.dateBirth ?? null,
        urgency: urgencyLabel,
        urgencyScore,
        priorityLevel: card.priorityLevel,
        isComplete: card.isComplete,
        missingCount: card.missingCount,
        missingItems: card.missingItems,
        careAdaptationSuggested: card.careAdaptationSuggested,
        proposedCareType: card.proposedCareType,
        requiredExperts: effectiveReq,
        presentRequiredExperts: presentReq,
        absentRequiredExperts: absentReq,
        quorumMet,
        expertCoverageRatio: coverage,
        clusterKey,
        pinned,
        rankReason: reasons.join(" · "),
        mdtDate: card.mdtDate,
      });
    }

    const clusterStats = new Map<string, { urgent: number; total: number }>();
    for (const item of rawItems) {
      const cur = clusterStats.get(item.clusterKey) ?? { urgent: 0, total: 0 };
      cur.total += 1;
      if (item.priorityLevel === "high") cur.urgent += 1;
      clusterStats.set(item.clusterKey, cur);
    }

    let ordered: MdtAgendaItem[];
    if (st.sortStrategy === "manual") {
      ordered = [...rawItems];
    } else {
      const unpinned = rawItems.filter((i) => !i.pinned);
      unpinned.sort((a, b) => {
        if (st.deferIncompleteFiles && a.isComplete !== b.isComplete) {
          return a.isComplete ? -1 : 1;
        }
        if (st.sortStrategy === "urgency_first") {
          if (b.urgencyScore !== a.urgencyScore) return b.urgencyScore - a.urgencyScore;
          if (b.expertCoverageRatio !== a.expertCoverageRatio) {
            return b.expertCoverageRatio - a.expertCoverageRatio;
          }
          return a.patientName.localeCompare(b.patientName, "fr");
        }
        if (st.sortStrategy === "expert_grouping") {
          if (a.quorumMet !== b.quorumMet) return a.quorumMet ? -1 : 1;
          if (a.clusterKey !== b.clusterKey) {
            const ca = clusterStats.get(a.clusterKey) ?? {
              urgent: 0,
              total: 0,
            };
            const cb = clusterStats.get(b.clusterKey) ?? {
              urgent: 0,
              total: 0,
            };
            if (cb.urgent !== ca.urgent) return cb.urgent - ca.urgent;
            if (cb.total !== ca.total) return cb.total - ca.total;
            return a.clusterKey.localeCompare(b.clusterKey);
          }
          if (b.urgencyScore !== a.urgencyScore) return b.urgencyScore - a.urgencyScore;
          return a.patientName.localeCompare(b.patientName, "fr");
        }
        const aTopUrgent = a.priorityLevel === "high" && a.quorumMet;
        const bTopUrgent = b.priorityLevel === "high" && b.quorumMet;
        if (aTopUrgent !== bTopUrgent) return aTopUrgent ? -1 : 1;
        if (a.quorumMet !== b.quorumMet) return a.quorumMet ? -1 : 1;
        if (a.clusterKey !== b.clusterKey) {
          const ca = clusterStats.get(a.clusterKey) ?? { urgent: 0, total: 0 };
          const cb = clusterStats.get(b.clusterKey) ?? { urgent: 0, total: 0 };
          if (cb.urgent !== ca.urgent) return cb.urgent - ca.urgent;
          if (cb.total !== ca.total) return cb.total - ca.total;
        }
        if (b.urgencyScore !== a.urgencyScore) return b.urgencyScore - a.urgencyScore;
        return a.patientName.localeCompare(b.patientName, "fr");
      });

      ordered = [];
      let unpinnedIdx = 0;
      for (let idx = 0; idx < rawItems.length; idx++) {
        const orig = rawItems[idx]!;
        if (orig.pinned) {
          ordered.push(orig);
        } else if (unpinnedIdx < unpinned.length) {
          ordered.push(unpinned[unpinnedIdx++]!);
        }
      }
    }

    ordered.forEach((item, index) => {
      item.position = index + 1;
    });
    st.enrolledPatientIds = ordered.map((i) => i.patientId);

    const expertWindows: MdtExpertWindow[] = availableExperts.map((exp) => {
      const matching = ordered.filter((it) => it.requiredExperts.includes(exp));
      const positions = matching.map((it) => it.position);
      const firstPos = positions.length > 0 ? Math.min(...positions) : null;
      const lastPos = positions.length > 0 ? Math.max(...positions) : null;
      const isContiguous =
        positions.length <= 1 ||
        (firstPos !== null && lastPos !== null && lastPos - firstPos + 1 === positions.length);
      return {
        expertName: exp,
        isAttending: attendingSet.has(exp),
        caseCount: matching.length,
        urgentCaseCount: matching.filter((it) => it.priorityLevel === "high").length,
        firstPosition: firstPos,
        lastPosition: lastPos,
        isContiguous,
        patientIds: matching.map((it) => it.patientId),
      };
    });

    const candidates: MdtAgendaCandidate[] = allCards
      .filter((c) => !enrolledSet.has(c.patientId ?? c.id))
      .map((c) => {
        const pid = c.patientId ?? c.id;
        const urgencyScore = c.priorityLevel === "high" ? 2 : c.priorityLevel === "medium" ? 1 : 0;
        const urgencyLabel =
          c.priorityLevel === "high"
            ? "Urgent"
            : c.priorityLevel === "medium"
              ? "Semi-urgent"
              : "Standard";
        return {
          patientId: pid,
          filename: c.file,
          patientName: c.patientName,
          firstName: c.firstName,
          lastName: c.lastName,
          dateBirth: c.dateBirth ?? null,
          urgency: urgencyLabel,
          urgencyScore,
          priorityLevel: c.priorityLevel,
          isComplete: c.isComplete,
          missingCount: c.missingCount,
          missingItems: c.missingItems,
          careAdaptationSuggested: c.careAdaptationSuggested,
          proposedCareType: c.proposedCareType,
          requiredExperts: c.specialties,
          mdtDate: c.mdtDate,
        };
      });

    return {
      agendaId: `next_mdt_${domain}`,
      domain,
      sessionDate: st.sessionDate,
      sortStrategy: st.sortStrategy,
      deferIncompleteFiles: st.deferIncompleteFiles,
      availableExperts,
      attendingExperts: st.attendingExperts,
      totalEnrolled: ordered.length,
      urgentCount: ordered.filter((i) => i.priorityLevel === "high").length,
      incompleteCount: ordered.filter((i) => !i.isComplete).length,
      quorumWarningCount: ordered.filter((i) => !i.quorumMet).length,
      items: ordered,
      expertWindows,
      candidates,
      updatedAt: st.updatedAt,
    };
  }

  async updateMdtAgenda(
    input: MdtAgendaUpdateInput,
    domain: ClinicalDomain,
  ): Promise<MdtAgendaView> {
    const st = this.ensureAgendaState(domain);
    if (input.sessionDate) st.sessionDate = input.sessionDate;
    if (input.sortStrategy) st.sortStrategy = input.sortStrategy;
    if (input.deferIncompleteFiles !== undefined) {
      st.deferIncompleteFiles = Boolean(input.deferIncompleteFiles);
    }
    if (input.attendingExperts) {
      st.attendingExperts = [...input.attendingExperts];
    }
    if (input.toggleExpert) {
      const idx = st.attendingExperts.indexOf(input.toggleExpert);
      if (idx >= 0) {
        st.attendingExperts.splice(idx, 1);
      } else {
        st.attendingExperts.push(input.toggleExpert);
      }
    }
    if (input.resetEnrolledPatients || input.patientIds !== undefined) {
      st.pinnedMap.clear();
      if (input.patientIds !== undefined) {
        st.enrolledPatientIds = [...new Set(input.patientIds.filter(Boolean))];
      } else {
        const cards = await this.listPatientCards(domain);
        st.enrolledPatientIds = cards.map((c) => c.patientId ?? c.id);
      }
    }
    st.updatedAt = new Date().toISOString();
    return this.getMdtAgenda(domain);
  }

  async addPatientsToMdtAgenda(
    input: MdtAgendaEnrollInput,
    domain: ClinicalDomain,
  ): Promise<MdtAgendaView> {
    const st = this.ensureAgendaState(domain);
    const toAdd: string[] = [];
    if (input.patientId) toAdd.push(input.patientId);
    if (Array.isArray(input.patientIds)) toAdd.push(...input.patientIds);

    if (input.enrollAllCandidates) {
      const cards = await this.listPatientCards(domain);
      for (const c of cards) {
        const pid = c.patientId ?? c.id;
        if (input.filterMode === "complete" && !c.isComplete) continue;
        if (input.filterMode === "urgent" && c.priorityLevel !== "high") continue;
        toAdd.push(pid);
      }
    }

    for (const pid of toAdd) {
      if (pid && !st.enrolledPatientIds.includes(pid)) {
        st.enrolledPatientIds.push(pid);
      }
    }
    st.updatedAt = new Date().toISOString();
    return this.getMdtAgenda(domain);
  }

  async removePatientFromMdtAgenda(
    patientId: string,
    domain: ClinicalDomain,
  ): Promise<MdtAgendaView> {
    const st = this.ensureAgendaState(domain);
    st.enrolledPatientIds = st.enrolledPatientIds.filter((id) => id !== patientId);
    st.pinnedMap.delete(patientId);
    st.updatedAt = new Date().toISOString();
    return this.getMdtAgenda(domain);
  }

  async clearMdtAgenda(domain: ClinicalDomain): Promise<MdtAgendaView> {
    const st = this.ensureAgendaState(domain);
    st.enrolledPatientIds = [];
    st.pinnedMap.clear();
    st.updatedAt = new Date().toISOString();
    return this.getMdtAgenda(domain);
  }

  async movePatientInMdtAgenda(
    patientId: string,
    input: MdtAgendaMoveInput,
    domain: ClinicalDomain,
  ): Promise<MdtAgendaView> {
    const st = this.ensureAgendaState(domain);
    await this.getMdtAgenda(domain);

    if (input.pinned !== undefined && !input.direction && input.targetPosition === undefined) {
      st.pinnedMap.set(patientId, Boolean(input.pinned));
      st.updatedAt = new Date().toISOString();
      return this.getMdtAgenda(domain);
    }

    const idx = st.enrolledPatientIds.indexOf(patientId);
    if (idx < 0) return this.getMdtAgenda(domain);

    let targetIdx = idx;
    if (input.direction === "up" && idx > 0) {
      targetIdx = idx - 1;
    } else if (input.direction === "down" && idx < st.enrolledPatientIds.length - 1) {
      targetIdx = idx + 1;
    } else if (typeof input.targetPosition === "number") {
      targetIdx = Math.max(0, Math.min(st.enrolledPatientIds.length - 1, input.targetPosition - 1));
    }

    if (targetIdx !== idx) {
      const [moved] = st.enrolledPatientIds.splice(idx, 1);
      if (moved) {
        st.enrolledPatientIds.splice(targetIdx, 0, moved);
      }
      st.sortStrategy = "manual";
    }
    if (input.pinned !== undefined) {
      st.pinnedMap.set(patientId, Boolean(input.pinned));
    } else {
      st.pinnedMap.set(patientId, true);
    }
    st.updatedAt = new Date().toISOString();
    return this.getMdtAgenda(domain);
  }
}
