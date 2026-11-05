import { translateValue } from "./i18n.js";
import { getSectionPresentation } from "./section-metadata.js";
import type { ClinicalDomain, DomainFormSchema, FormSectionSchema } from "./types.js";

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

export const BOOLEAN_SELECT_OPTIONS: FieldSelectOption[] = [
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
  CancerDescription: [
    {
      key: "type_of_cancer",
      inputType: "text",
      nullable: true,
      defaultValue: null,
      placeholderFr: "Ex : Adénocarcinome canalaire pancréatique",
      placeholderEn: "E.g. Pancreatic ductal adenocarcinoma",
    },
    {
      key: "histological_grade",
      inputType: "text",
      nullable: true,
      defaultValue: null,
      placeholderFr: "Ex : Bien différencié (G1), Moyennement différencié (G2)",
      placeholderEn: "E.g. Well differentiated (G1), Moderately differentiated (G2)",
    },
    {
      key: "tnm_status",
      inputType: "text",
      nullable: true,
      defaultValue: null,
      placeholderFr: "Ex : cT3N1M0, ypT2N0M0",
      placeholderEn: "E.g. cT3N1M0, ypT2N0M0",
    },
    {
      key: "figo_stage",
      inputType: "text",
      nullable: true,
      defaultValue: null,
      placeholderFr: "Ex : FIGO IIIB",
      placeholderEn: "E.g. FIGO IIIB",
    },
    {
      key: "metastatic_status",
      inputType: "nullable_boolean",
      nullable: true,
      defaultValue: null,
      options: BOOLEAN_SELECT_OPTIONS,
    },
    {
      key: "metastatic_sites",
      inputType: "string_list",
      nullable: false,
      defaultValue: [],
      placeholderFr: "Ex : Foie, Péritoine, Poumon (séparer par des virgules)",
      placeholderEn: "E.g. Liver, Peritoneum, Lung (comma-separated)",
    },
    {
      key: "target_lesion_size_mm",
      inputType: "float",
      nullable: true,
      defaultValue: null,
      min: 0,
      max: 500,
      step: 0.5,
      unit: "mm",
    },
    {
      key: "recist_response",
      inputType: "select",
      nullable: true,
      defaultValue: null,
      options: [
        { value: "", labelFr: "Non renseigné", labelEn: "Not documented" },
        { value: "CR", labelFr: "RC (CR) — Réponse complète", labelEn: "CR — Complete Response" },
        { value: "PR", labelFr: "RP (PR) — Réponse partielle", labelEn: "PR — Partial Response" },
        { value: "SD", labelFr: "MS (SD) — Maladie stable", labelEn: "SD — Stable Disease" },
        {
          value: "PD",
          labelFr: "MP (PD) — Progression tumorale",
          labelEn: "PD — Progressive Disease",
        },
        {
          value: "Baseline",
          labelFr: "Bilan initial (Baseline)",
          labelEn: "Baseline",
        },
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
    {
      key: "ca19_9",
      inputType: "float",
      nullable: true,
      defaultValue: null,
      min: 0,
      max: 1000000,
      step: 0.5,
      unit: "U/mL",
    },
    {
      key: "ace",
      inputType: "float",
      nullable: true,
      defaultValue: null,
      min: 0,
      max: 100000,
      step: 0.1,
      unit: "ng/mL",
    },
    {
      key: "afp",
      inputType: "float",
      nullable: true,
      defaultValue: null,
      min: 0,
      max: 1000000,
      step: 0.5,
      unit: "ng/mL",
    },
    {
      key: "dpd_uracilemia",
      inputType: "float",
      nullable: true,
      defaultValue: null,
      min: 0,
      max: 500,
      step: 0.1,
      unit: "ng/mL",
    },
    {
      key: "ras_braf_status",
      inputType: "text",
      nullable: true,
      defaultValue: null,
      placeholderFr: "Ex : KRAS G12D muté, BRAF V600E sauvage",
      placeholderEn: "E.g. KRAS G12D mutated, BRAF wild-type",
    },
    {
      key: "her2_status",
      inputType: "text",
      nullable: true,
      defaultValue: null,
      placeholderFr: "Ex : HER2 négatif (IHC 0), CPS PD-L1 = 5",
      placeholderEn: "E.g. HER2 negative (IHC 0), PD-L1 CPS = 5",
    },
  ],
  HepaticStatus: [
    {
      key: "bilirubin_umol_l",
      inputType: "float",
      nullable: true,
      defaultValue: null,
      min: 0,
      max: 1000,
      step: 0.5,
      unit: "µmol/L",
    },
    {
      key: "child_pugh_score",
      inputType: "text",
      nullable: true,
      defaultValue: null,
      placeholderFr: "Ex : A5, A6, B7",
      placeholderEn: "E.g. A5, A6, B7",
    },
    {
      key: "bclc_stage",
      inputType: "text",
      nullable: true,
      defaultValue: null,
      placeholderFr: "Ex : BCLC A, BCLC B, BCLC C",
      placeholderEn: "E.g. BCLC A, BCLC B, BCLC C",
    },
  ],
  NutritionalStatus: [
    {
      key: "weight_kg",
      inputType: "float",
      nullable: true,
      defaultValue: null,
      min: 0,
      max: 300,
      step: 0.5,
      unit: "kg",
    },
    {
      key: "weight_loss_percent",
      inputType: "float",
      nullable: true,
      defaultValue: null,
      min: 0,
      max: 100,
      step: 0.5,
      unit: "%",
    },
    {
      key: "bmi",
      inputType: "float",
      nullable: true,
      defaultValue: null,
      min: 0,
      max: 100,
      step: 0.1,
      unit: "kg/m²",
    },
    {
      key: "nutritional_status",
      inputType: "text",
      nullable: true,
      defaultValue: null,
      placeholderFr: "Ex : Normal, Dénutrition modérée, Dénutrition sévère",
      placeholderEn: "E.g. Normal, Moderate malnutrition, Severe malnutrition",
    },
  ],
  SurgicalStatus: [
    {
      key: "resectability_status",
      inputType: "select",
      nullable: true,
      defaultValue: null,
      options: [
        { value: "", labelFr: "Non renseigné", labelEn: "Not documented" },
        { value: "Resectable", labelFr: "Résécable", labelEn: "Resectable" },
        { value: "Borderline", labelFr: "Borderline (limite)", labelEn: "Borderline" },
        {
          value: "Locally advanced",
          labelFr: "Localement avancé",
          labelEn: "Locally advanced",
        },
        { value: "Unresectable", labelFr: "Non résécable", labelEn: "Unresectable" },
        { value: "Metastatic", labelFr: "Métastatique", labelEn: "Metastatic" },
      ],
    },
    {
      key: "surgery_done",
      inputType: "nullable_boolean",
      nullable: true,
      defaultValue: null,
      options: BOOLEAN_SELECT_OPTIONS,
    },
    {
      key: "resection_margin",
      inputType: "select",
      nullable: true,
      defaultValue: null,
      options: [
        { value: "", labelFr: "Non renseigné", labelEn: "Not documented" },
        { value: "R0", labelFr: "R0 — Résection complète microscopique", labelEn: "R0" },
        { value: "R1", labelFr: "R1 — Reliquat microscopique", labelEn: "R1" },
        { value: "R2", labelFr: "R2 — Reliquat macroscopique", labelEn: "R2" },
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
          "CancerDescription",
          "TumorBiology",
          "HepaticStatus",
          "PatientPerformanceStatus",
          "NutritionalStatus",
          "RadiologicExams",
          "SurgicalStatus",
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
      } else if (fs.inputType === "integer" || fs.inputType === "float") {
        const base = {
          type: fs.inputType === "integer" ? "integer" : "number",
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
