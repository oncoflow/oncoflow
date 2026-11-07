"""Pure domain models and calculators for the longitudinal Patient Record Dashboard."""

from datetime import date, datetime
import re
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from src.domain.patient_mdt_form import get_domain_mdt_form_cls

MetricPolarity = Literal["higher_is_better", "lower_is_better", "neutral"]
MetricValueType = Literal["numeric_or_mixed", "categorical", "boolean", "list"]


class PatientMetricDescriptor(BaseModel):
    """Domain descriptor for a tracked longitudinal metric."""

    metric_key: str = Field(description="Canonical Section.field identifier")
    section: str = Field(description="Clinical section name on PatientMDTForm")
    field: str = Field(description="Field key inside the clinical section")
    label: str = Field(description="Localized clinical label")
    clinical_category: str = Field(
        default="", description="Human-readable clinical pole/category label"
    )
    unit: str = Field(default="", description="Display unit or scale denominator")
    scale_min: Optional[float] = Field(
        default=None, description="Theoretical minimum value when applicable"
    )
    scale_max: Optional[float] = Field(
        default=None, description="Theoretical maximum value when applicable"
    )
    polarity: MetricPolarity = Field(
        default="neutral",
        description="Clinical interpretation of an upward numeric variation",
    )
    value_type: MetricValueType = Field(
        default="numeric_or_mixed",
        description="Category of raw metric value",
    )


class RawMetricObservation(BaseModel):
    """Parsed representation of a raw clinical value preserving 100% of the source value."""

    raw_value: Any = Field(description="Original untouched value from the record")
    display_value: str = Field(description="Human-readable raw string representation")
    numeric_value: Optional[float] = Field(
        default=None,
        description="Extracted primary numeric coordinate for line plotting when available",
    )
    sub_values: Optional[dict[str, float]] = Field(
        default=None,
        description="Extracted sub-coordinates for bilateral scores such as D/G",
    )
    is_annotative_only: bool = Field(
        default=False,
        description="True when a numeric_or_mixed metric contains a qualitative note without a number",
    )


class PatientMetricPoint(BaseModel):
    """Single chronological observation along a multi-year patient metric timeline."""

    form_id: str = Field(description="Filename of the source PatientMDTForm")
    form_date: Optional[str] = Field(
        default=None, description="ISO-8601 date of the MDT session"
    )
    form_date_label: str = Field(
        default="Date inconnue", description="Formatted DD/MM/YYYY date label"
    )
    days_since_first_rcp: int = Field(
        default=0, description="Elapsed days since the patient's earliest MDT form"
    )
    x_ratio: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Normalized proportional time position in [0.0, 1.0]",
    )
    raw_value: Any = Field(description="Original raw value")
    display_value: str = Field(description="Formatted raw display string")
    numeric_value: Optional[float] = Field(default=None)
    sub_values: Optional[dict[str, float]] = Field(default=None)
    is_annotative_only: bool = Field(default=False)
    is_manual: bool = Field(
        default=False,
        description="True when the parent section was manually edited by a clinician",
    )
    edited_by: Optional[str] = Field(default=None)
    edited_at: Optional[str] = Field(default=None)
    delta_numeric: Optional[float] = Field(
        default=None,
        description="Numeric difference compared to the previous numeric observation",
    )
    delta_display: Optional[str] = Field(
        default=None,
        description="Formatted delta string compared to the previous observation",
    )


class PatientMetricSeries(BaseModel):
    """Chronological series of raw metric observations across all forms of a patient."""

    metric_key: str
    section: str
    field: str
    label: str
    clinical_category: str = ""
    unit: str = ""
    scale_min: Optional[float] = None
    scale_max: Optional[float] = None
    polarity: MetricPolarity = "neutral"
    value_type: MetricValueType = "numeric_or_mixed"
    points: list[PatientMetricPoint] = Field(default_factory=list)


class PatientRecordSummaryContent(BaseModel):
    """Structured longitudinal clinical synthesis across a patient's entire MDT history."""

    clinical_trajectory_overview: str = Field(
        description="Global chronological summary of the patient's clinical trajectory"
    )
    disease_and_treatment_evolution: str = Field(
        description="Evolution of therapeutic lines, surgical/orthopedic interventions, and clinical response"
    )
    notable_metric_changes: list[str] = Field(
        default_factory=list,
        description="Key raw metric variations observed across MDT forms with dates",
    )
    unresolved_vigilance_points: list[str] = Field(
        default_factory=list,
        description="Active missing items or clinical vigilance points requiring follow-up",
    )
    mdt_decisions_recap: list[str] = Field(
        default_factory=list,
        description="Chronological recap of CareOrientationProposal / MDT orientations",
    )
    sources_used: list[str] = Field(
        default_factory=list,
        description="List of PatientMDTForm filenames synthesized",
    )


SMA_METRIC_DESCRIPTORS: list[PatientMetricDescriptor] = [
    PatientMetricDescriptor(
        metric_key="MotorFunctionStatus.rulm_score",
        section="MotorFunctionStatus",
        field="rulm_score",
        label="Score RULM (Membre supérieur)",
        clinical_category="Fonction motrice",
        unit="/ 37",
        scale_min=0.0,
        scale_max=37.0,
        polarity="higher_is_better",
        value_type="numeric_or_mixed",
    ),
    PatientMetricDescriptor(
        metric_key="MotorFunctionStatus.hfmse_score",
        section="MotorFunctionStatus",
        field="hfmse_score",
        label="Score HFMSE (Fonction motrice)",
        clinical_category="Fonction motrice",
        unit="/ 66",
        scale_min=0.0,
        scale_max=66.0,
        polarity="higher_is_better",
        value_type="numeric_or_mixed",
    ),
    PatientMetricDescriptor(
        metric_key="MotorFunctionStatus.chop_intend_score",
        section="MotorFunctionStatus",
        field="chop_intend_score",
        label="Score CHOP-INTEND",
        clinical_category="Fonction motrice",
        unit="/ 64",
        scale_min=0.0,
        scale_max=64.0,
        polarity="higher_is_better",
        value_type="numeric_or_mixed",
    ),
    PatientMetricDescriptor(
        metric_key="RespiratoryFunction.forced_vital_capacity_percent",
        section="RespiratoryFunction",
        field="forced_vital_capacity_percent",
        label="Capacité Vitale Forcée (CVF)",
        clinical_category="Fonction respiratoire",
        unit="%",
        scale_min=0.0,
        scale_max=140.0,
        polarity="higher_is_better",
        value_type="numeric_or_mixed",
    ),
    PatientMetricDescriptor(
        metric_key="RespiratoryFunction.daily_ventilation_hours",
        section="RespiratoryFunction",
        field="daily_ventilation_hours",
        label="Ventilation quotidienne",
        clinical_category="Fonction respiratoire",
        unit="h/j",
        scale_min=0.0,
        scale_max=24.0,
        polarity="lower_is_better",
        value_type="numeric_or_mixed",
    ),
    PatientMetricDescriptor(
        metric_key="OrthopedicAndSpineStatus.scoliosis_cobb_angle",
        section="OrthopedicAndSpineStatus",
        field="scoliosis_cobb_angle",
        label="Angle de Cobb (Scoliose)",
        clinical_category="Statut orthopédique & Rachis",
        unit="°",
        scale_min=0.0,
        scale_max=120.0,
        polarity="lower_is_better",
        value_type="numeric_or_mixed",
    ),
    PatientMetricDescriptor(
        metric_key="PatientPerformanceStatus.performance_status",
        section="PatientPerformanceStatus",
        field="performance_status",
        label="Statut OMS / WHO",
        clinical_category="État général",
        unit="/ 4",
        scale_min=0.0,
        scale_max=4.0,
        polarity="lower_is_better",
        value_type="numeric_or_mixed",
    ),
    PatientMetricDescriptor(
        metric_key="MotorFunctionStatus.best_motor_function",
        section="MotorFunctionStatus",
        field="best_motor_function",
        label="Meilleure fonction motrice",
        clinical_category="Fonction motrice",
        unit="",
        polarity="neutral",
        value_type="categorical",
    ),
    PatientMetricDescriptor(
        metric_key="MotorFunctionStatus.motor_milestones",
        section="MotorFunctionStatus",
        field="motor_milestones",
        label="Jalons moteurs acquis",
        clinical_category="Fonction motrice",
        unit="",
        polarity="neutral",
        value_type="list",
    ),
    PatientMetricDescriptor(
        metric_key="RespiratoryFunction.ventilation_type",
        section="RespiratoryFunction",
        field="ventilation_type",
        label="Support ventilatoire",
        clinical_category="Fonction respiratoire",
        unit="",
        polarity="neutral",
        value_type="categorical",
    ),
    PatientMetricDescriptor(
        metric_key="BulbarAndNutritionalStatus.feeding_mode",
        section="BulbarAndNutritionalStatus",
        field="feeding_mode",
        label="Mode d'alimentation",
        clinical_category="Nutrition & Déglutition",
        unit="",
        polarity="neutral",
        value_type="categorical",
    ),
    PatientMetricDescriptor(
        metric_key="BulbarAndNutritionalStatus.nutritional_status",
        section="BulbarAndNutritionalStatus",
        field="nutritional_status",
        label="Statut nutritionnel",
        clinical_category="Nutrition & Déglutition",
        unit="",
        polarity="neutral",
        value_type="categorical",
    ),
]

ONCOLOGY_METRIC_DESCRIPTORS: list[PatientMetricDescriptor] = [
    PatientMetricDescriptor(
        metric_key="PatientPerformanceStatus.performance_status",
        section="PatientPerformanceStatus",
        field="performance_status",
        label="Statut OMS / WHO",
        clinical_category="État général",
        unit="/ 4",
        scale_min=0.0,
        scale_max=4.0,
        polarity="lower_is_better",
        value_type="numeric_or_mixed",
    ),
    PatientMetricDescriptor(
        metric_key="TumorBiology.ca19_9",
        section="TumorBiology",
        field="ca19_9",
        label="Marqueur tumoral CA 19-9",
        clinical_category="Biologie & Biomarqueurs",
        unit="U/mL",
        scale_min=0.0,
        polarity="lower_is_better",
        value_type="numeric_or_mixed",
    ),
    PatientMetricDescriptor(
        metric_key="TumorBiology.ace",
        section="TumorBiology",
        field="ace",
        label="Marqueur tumoral ACE (CEA)",
        clinical_category="Biologie & Biomarqueurs",
        unit="ng/mL",
        scale_min=0.0,
        polarity="lower_is_better",
        value_type="numeric_or_mixed",
    ),
    PatientMetricDescriptor(
        metric_key="TumorBiology.afp",
        section="TumorBiology",
        field="afp",
        label="Alpha-fœtoprotéine (AFP)",
        clinical_category="Biologie & Biomarqueurs",
        unit="ng/mL",
        scale_min=0.0,
        polarity="lower_is_better",
        value_type="numeric_or_mixed",
    ),
    PatientMetricDescriptor(
        metric_key="TumorBiology.dpd_uracilemia",
        section="TumorBiology",
        field="dpd_uracilemia",
        label="Uracilémie pré-thérapeutique (DPD)",
        clinical_category="Biologie & Biomarqueurs",
        unit="ng/mL",
        scale_min=0.0,
        polarity="lower_is_better",
        value_type="numeric_or_mixed",
    ),
    PatientMetricDescriptor(
        metric_key="CancerDescription.target_lesion_size_mm",
        section="CancerDescription",
        field="target_lesion_size_mm",
        label="Taille de la lésion cible",
        clinical_category="Caractéristiques tumorales",
        unit="mm",
        scale_min=0.0,
        polarity="lower_is_better",
        value_type="numeric_or_mixed",
    ),
    PatientMetricDescriptor(
        metric_key="NutritionalStatus.weight_kg",
        section="NutritionalStatus",
        field="weight_kg",
        label="Poids corporel",
        clinical_category="Nutrition & État général",
        unit="kg",
        scale_min=0.0,
        polarity="higher_is_better",
        value_type="numeric_or_mixed",
    ),
    PatientMetricDescriptor(
        metric_key="NutritionalStatus.weight_loss_percent",
        section="NutritionalStatus",
        field="weight_loss_percent",
        label="Perte de poids",
        clinical_category="Nutrition & État général",
        unit="%",
        scale_min=0.0,
        scale_max=100.0,
        polarity="lower_is_better",
        value_type="numeric_or_mixed",
    ),
    PatientMetricDescriptor(
        metric_key="NutritionalStatus.bmi",
        section="NutritionalStatus",
        field="bmi",
        label="Indice de Masse Corporelle (IMC)",
        clinical_category="Nutrition & État général",
        unit="kg/m²",
        scale_min=10.0,
        scale_max=60.0,
        polarity="higher_is_better",
        value_type="numeric_or_mixed",
    ),
    PatientMetricDescriptor(
        metric_key="HepaticStatus.bilirubin_umol_l",
        section="HepaticStatus",
        field="bilirubin_umol_l",
        label="Bilirubine totale",
        clinical_category="Fonction hépatique",
        unit="µmol/L",
        scale_min=0.0,
        polarity="lower_is_better",
        value_type="numeric_or_mixed",
    ),
    PatientMetricDescriptor(
        metric_key="CancerDescription.tnm_status",
        section="CancerDescription",
        field="tnm_status",
        label="Classification TNM",
        clinical_category="Caractéristiques tumorales",
        unit="",
        polarity="neutral",
        value_type="categorical",
    ),
    PatientMetricDescriptor(
        metric_key="CancerDescription.recist_response",
        section="CancerDescription",
        field="recist_response",
        label="Réponse radiologique (RECIST 1.1)",
        clinical_category="Caractéristiques tumorales",
        unit="",
        polarity="neutral",
        value_type="categorical",
    ),
    PatientMetricDescriptor(
        metric_key="CancerDescription.figo_stage",
        section="CancerDescription",
        field="figo_stage",
        label="Stade FIGO / UICC",
        clinical_category="Caractéristiques tumorales",
        unit="",
        polarity="neutral",
        value_type="categorical",
    ),
    PatientMetricDescriptor(
        metric_key="CancerDescription.histological_grade",
        section="CancerDescription",
        field="histological_grade",
        label="Grade histologique",
        clinical_category="Caractéristiques tumorales",
        unit="",
        polarity="neutral",
        value_type="categorical",
    ),
    PatientMetricDescriptor(
        metric_key="CancerDescription.type_of_cancer",
        section="CancerDescription",
        field="type_of_cancer",
        label="Type histologique / tumoral",
        clinical_category="Caractéristiques tumorales",
        unit="",
        polarity="neutral",
        value_type="categorical",
    ),
    PatientMetricDescriptor(
        metric_key="CancerDescription.metastatic_sites",
        section="CancerDescription",
        field="metastatic_sites",
        label="Sites métastatiques",
        clinical_category="Caractéristiques tumorales",
        unit="",
        polarity="lower_is_better",
        value_type="list",
    ),
    PatientMetricDescriptor(
        metric_key="TumorLocation.tumor_location",
        section="TumorLocation",
        field="tumor_location",
        label="Localisation tumorale primitive",
        clinical_category="Caractéristiques tumorales",
        unit="",
        polarity="neutral",
        value_type="categorical",
    ),
    PatientMetricDescriptor(
        metric_key="TumorBiology.msi_state",
        section="TumorBiology",
        field="msi_state",
        label="Statut MSI / MMR",
        clinical_category="Biologie & Biomarqueurs",
        unit="",
        polarity="neutral",
        value_type="categorical",
    ),
    PatientMetricDescriptor(
        metric_key="TumorBiology.ras_braf_status",
        section="TumorBiology",
        field="ras_braf_status",
        label="Statut moléculaire RAS / BRAF",
        clinical_category="Biologie & Biomarqueurs",
        unit="",
        polarity="neutral",
        value_type="categorical",
    ),
    PatientMetricDescriptor(
        metric_key="TumorBiology.her2_status",
        section="TumorBiology",
        field="her2_status",
        label="Statut HER2 / PD-L1",
        clinical_category="Biologie & Biomarqueurs",
        unit="",
        polarity="neutral",
        value_type="categorical",
    ),
    PatientMetricDescriptor(
        metric_key="SurgicalStatus.resectability_status",
        section="SurgicalStatus",
        field="resectability_status",
        label="Statut de résécabilité",
        clinical_category="Chirurgie & Traitements",
        unit="",
        polarity="neutral",
        value_type="categorical",
    ),
    PatientMetricDescriptor(
        metric_key="SurgicalStatus.surgery_done",
        section="SurgicalStatus",
        field="surgery_done",
        label="Chirurgie réalisée",
        clinical_category="Chirurgie & Traitements",
        unit="",
        polarity="neutral",
        value_type="boolean",
    ),
    PatientMetricDescriptor(
        metric_key="SurgicalStatus.resection_margin",
        section="SurgicalStatus",
        field="resection_margin",
        label="Marges d'exérèse (R0/R1/R2)",
        clinical_category="Chirurgie & Traitements",
        unit="",
        polarity="neutral",
        value_type="categorical",
    ),
    PatientMetricDescriptor(
        metric_key="HepaticStatus.child_pugh_score",
        section="HepaticStatus",
        field="child_pugh_score",
        label="Score de Child-Pugh",
        clinical_category="Fonction hépatique",
        unit="",
        polarity="neutral",
        value_type="categorical",
    ),
    PatientMetricDescriptor(
        metric_key="HepaticStatus.bclc_stage",
        section="HepaticStatus",
        field="bclc_stage",
        label="Stade BCLC (CHC)",
        clinical_category="Fonction hépatique",
        unit="",
        polarity="neutral",
        value_type="categorical",
    ),
    PatientMetricDescriptor(
        metric_key="NutritionalStatus.nutritional_status",
        section="NutritionalStatus",
        field="nutritional_status",
        label="Statut nutritionnel",
        clinical_category="Nutrition & État général",
        unit="",
        polarity="neutral",
        value_type="categorical",
    ),
    PatientMetricDescriptor(
        metric_key="Chemotherapy.chemotherapy_name",
        section="Chemotherapy",
        field="chemotherapy_name",
        label="Ligne de chimiothérapie",
        clinical_category="Chirurgie & Traitements",
        unit="",
        polarity="neutral",
        value_type="categorical",
    ),
    PatientMetricDescriptor(
        metric_key="Chemotherapy.chemotherapy_tolerance",
        section="Chemotherapy",
        field="chemotherapy_tolerance",
        label="Tolérance de la chimiothérapie",
        clinical_category="Chirurgie & Traitements",
        unit="",
        polarity="neutral",
        value_type="categorical",
    ),
]


def get_domain_metric_descriptors(
    domain: str = "oncology",
) -> list[PatientMetricDescriptor]:
    """Return the ordered list of longitudinal metric descriptors for the given domain."""
    norm = (domain or "oncology").strip().lower()
    if norm == "sma":
        return list(SMA_METRIC_DESCRIPTORS)
    return list(ONCOLOGY_METRIC_DESCRIPTORS)


_BILATERAL_PART_PATTERN = re.compile(r"^(\d+(?:[.,]\d+)?)\(([DGRL])\)$")
_LEADING_NUMBER_PATTERN = re.compile(r"^[-+]?\d+(?:[.,]\d+)?")


def _parse_bilateral_scores(text: str) -> dict[str, float] | None:
    """Extract bilateral limb scores (e.g. '28 (D) / 30 (G)') without complex regexes."""
    compact = "".join(text.split()).upper()
    for sep in ("/", "|", ",", "-"):
        if sep not in compact:
            continue
        parts = compact.split(sep)
        if len(parts) != 2:
            return None
        m1 = _BILATERAL_PART_PATTERN.match(parts[0])
        m2 = _BILATERAL_PART_PATTERN.match(parts[1])
        if m1 and m2:
            v1 = float(m1.group(1).replace(",", "."))
            v2 = float(m2.group(1).replace(",", "."))
            return {m1.group(2): v1, m2.group(2): v2}
        return None
    return None


def parse_raw_metric_value(
    raw_value: Any,
    descriptor: PatientMetricDescriptor | None = None,
) -> RawMetricObservation:
    """
    Parse a raw clinical metric value into a `RawMetricObservation`.
    Never alters `raw_value`; extracts optional numeric coordinates for chart plotting.
    """
    v_type = descriptor.value_type if descriptor else "numeric_or_mixed"

    if isinstance(raw_value, bool):
        return RawMetricObservation(
            raw_value=raw_value,
            display_value="Oui" if raw_value else "Non",
            numeric_value=1.0 if raw_value else 0.0,
            is_annotative_only=False,
        )

    if isinstance(raw_value, (int, float)):
        num = float(raw_value)
        disp = str(raw_value) if isinstance(raw_value, int) else f"{num:g}"
        return RawMetricObservation(
            raw_value=raw_value,
            display_value=disp,
            numeric_value=num,
            is_annotative_only=False,
        )

    if isinstance(raw_value, list):
        items = [str(x).strip() for x in raw_value if str(x).strip()]
        disp = ", ".join(items) if items else "—"
        return RawMetricObservation(
            raw_value=raw_value,
            display_value=disp,
            numeric_value=float(len(items)) if v_type == "list" else None,
            is_annotative_only=(v_type == "numeric_or_mixed"),
        )

    text = str(raw_value).strip() if raw_value is not None else ""
    if not text:
        return RawMetricObservation(
            raw_value=raw_value,
            display_value="—",
            numeric_value=None,
            is_annotative_only=True,
        )

    if v_type != "numeric_or_mixed":
        return RawMetricObservation(
            raw_value=raw_value,
            display_value=text,
            numeric_value=None,
            is_annotative_only=False,
        )

    # Check bilateral pattern first: e.g. "28 (D) / 30 (G)"
    bilat_sub = _parse_bilateral_scores(text)
    if bilat_sub:
        vals = list(bilat_sub.values())
        return RawMetricObservation(
            raw_value=raw_value,
            display_value=text,
            numeric_value=(vals[0] + vals[1]) / 2.0,
            sub_values=bilat_sub,
            is_annotative_only=False,
        )

    # Check leading numeric or ratio: e.g. "34/37", "31.5 pts", "32"
    num_match = _LEADING_NUMBER_PATTERN.match(text)
    if num_match:
        num = float(num_match.group(0).replace(",", "."))
        return RawMetricObservation(
            raw_value=raw_value,
            display_value=text,
            numeric_value=num,
            is_annotative_only=False,
        )

    # Purely qualitative/annotative note on a numeric metric (e.g. "Non testé (fatigue)")
    return RawMetricObservation(
        raw_value=raw_value,
        display_value=text,
        numeric_value=None,
        is_annotative_only=True,
    )


def _normalize_dt(value: Any) -> datetime | None:
    """Convert a datetime, date, or ISO string into a naive datetime."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            m = re.search(r"(\d{4})-(\d{2})-(\d{2})", s)
            if m:
                return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return None


def _extract_form_datetime(doc: dict[str, Any], form_cls: Any) -> datetime | None:
    """Extract the clinical MDT date (or fallback refresh date) of a PatientMDTForm document."""
    extracted = form_cls.extract_mdt_date(doc)
    dt = _normalize_dt(extracted)
    if dt is not None:
        return dt
    admin = doc.get("PatientAdministrative")
    if isinstance(admin, dict):
        dt = _normalize_dt(admin.get("date_rcp"))
        if dt is not None:
            return dt
    return _normalize_dt(doc.get("ui_date")) or _normalize_dt(doc.get("date_refresh"))


def build_patient_metric_series(
    forms: list[dict[str, Any]],
    domain: str = "oncology",
) -> list[PatientMetricSeries]:
    """
    Build chronological multi-year metric series across a patient's `PatientMDTForm` records.
    Sorts forms from oldest to newest and computes proportional `x_ratio` coordinates.
    """
    form_cls = get_domain_mdt_form_cls(domain)
    descriptors = get_domain_metric_descriptors(domain)

    dated_forms: list[tuple[datetime, int, dict[str, Any]]] = []
    for idx, doc in enumerate(forms or []):
        if not isinstance(doc, dict):
            continue
        dt = _extract_form_datetime(doc, form_cls) or datetime(1970, 1, 1)
        dated_forms.append((dt, idx, doc))

    # Sort oldest first for left-to-right longitudinal time charts
    dated_forms.sort(key=lambda item: (item[0], item[1]))

    if not dated_forms:
        return []

    real_dates = [dt for dt, _, _ in dated_forms if dt.year > 1970]
    min_dt = min(real_dates) if real_dates else dated_forms[0][0]
    max_dt = max(real_dates) if real_dates else dated_forms[-1][0]
    total_span_days = max(0, (max_dt - min_dt).days)
    count = len(dated_forms)

    series_out: list[PatientMetricSeries] = []

    for desc in descriptors:
        points: list[PatientMetricPoint] = []
        prev_numeric: float | None = None

        for pos, (dt, _, doc) in enumerate(dated_forms):
            sec_data = doc.get(desc.section)
            if not isinstance(sec_data, dict) and desc.section == "Chemotherapy":
                sec_data = doc.get("ChemotherapyTreament")
            if not isinstance(sec_data, dict):
                continue
            raw_val = sec_data.get(desc.field)
            if (
                (raw_val is None or raw_val == "" or raw_val == [])
                and desc.section == "Chemotherapy"
                and isinstance(sec_data.get("chemotherapy_list"), list)
                and sec_data["chemotherapy_list"]
            ):
                first_line = sec_data["chemotherapy_list"][0]
                if isinstance(first_line, dict):
                    raw_val = first_line.get(desc.field)
            if raw_val is None or raw_val == "" or raw_val == []:
                continue

            obs = parse_raw_metric_value(raw_val, desc)
            if obs.display_value == "—":
                continue

            has_real_date = dt.year > 1970
            days_since_first = max(0, (dt - min_dt).days) if has_real_date else pos * 30
            if count <= 1:
                x_ratio = 0.5
            elif total_span_days > 0 and has_real_date:
                x_ratio = min(
                    1.0, max(0.0, (dt - min_dt).days / float(total_span_days))
                )
            else:
                x_ratio = pos / float(count - 1)

            manual_edits = doc.get("manual_edits")
            manual_meta = (
                manual_edits.get(desc.section)
                if isinstance(manual_edits, dict)
                else None
            )
            is_manual = isinstance(manual_meta, dict)
            edited_by = (
                str(manual_meta.get("edited_by"))
                if isinstance(manual_meta, dict) and manual_meta.get("edited_by")
                else None
            )
            edited_at = (
                str(manual_meta.get("edited_at"))
                if isinstance(manual_meta, dict) and manual_meta.get("edited_at")
                else None
            )

            delta_num: float | None = None
            delta_disp: str | None = None
            if obs.numeric_value is not None and prev_numeric is not None:
                delta_num = round(obs.numeric_value - prev_numeric, 2)
                sign = "+" if delta_num > 0 else ""
                delta_disp = f"{sign}{delta_num:g}"

            if obs.numeric_value is not None:
                prev_numeric = obs.numeric_value

            points.append(
                PatientMetricPoint(
                    form_id=str(doc.get("file") or f"rcp_{pos + 1}"),
                    form_date=dt.strftime("%Y-%m-%d") if has_real_date else None,
                    form_date_label=dt.strftime("%d/%m/%Y")
                    if has_real_date
                    else "Date non renseignée",
                    days_since_first_rcp=days_since_first,
                    x_ratio=round(x_ratio, 4),
                    raw_value=obs.raw_value,
                    display_value=obs.display_value,
                    numeric_value=obs.numeric_value,
                    sub_values=obs.sub_values,
                    is_annotative_only=obs.is_annotative_only,
                    is_manual=is_manual,
                    edited_by=edited_by,
                    edited_at=edited_at,
                    delta_numeric=delta_num,
                    delta_display=delta_disp,
                )
            )

        if points:
            series_out.append(
                PatientMetricSeries(
                    metric_key=desc.metric_key,
                    section=desc.section,
                    field=desc.field,
                    label=desc.label,
                    clinical_category=desc.clinical_category,
                    unit=desc.unit,
                    scale_min=desc.scale_min,
                    scale_max=desc.scale_max,
                    polarity=desc.polarity,
                    value_type=desc.value_type,
                    points=points,
                )
            )

    return series_out


def evaluate_patient_record_summary_obsolescence(
    summary_snapshot: dict[str, Any] | None,
    current_forms: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """
    Evaluate whether a persisted `record_summary` snapshot is obsolete relative to
    the patient's current list of `PatientMDTForm` documents.
    """
    if not summary_snapshot or not isinstance(summary_snapshot, dict):
        return None

    generated_at_dt = _normalize_dt(summary_snapshot.get("generated_at"))
    covered_ids = [
        str(f) for f in (summary_snapshot.get("covered_form_ids") or []) if f
    ]
    covered_set = set(covered_ids)

    current_files: list[str] = []
    modified_forms: list[str] = []
    newer_mdt_date_forms: list[str] = []

    latest_gen_mdt_dt = _normalize_dt(
        summary_snapshot.get("latest_form_date_at_generation")
    )

    for doc in current_forms or []:
        if not isinstance(doc, dict):
            continue
        fname = str(doc.get("file") or "").strip()
        if not fname:
            continue
        current_files.append(fname)

        refresh_dt = _normalize_dt(doc.get("date_refresh"))
        if (
            generated_at_dt is not None
            and refresh_dt is not None
            and fname in covered_set
            and refresh_dt > generated_at_dt
        ):
            modified_forms.append(fname)

        admin = doc.get("PatientAdministrative")
        mdt_dt = (
            _normalize_dt(admin.get("date_rcp"))
            if isinstance(admin, dict)
            else _normalize_dt(doc.get("mdt_date"))
        )
        if (
            latest_gen_mdt_dt is not None
            and mdt_dt is not None
            and mdt_dt > latest_gen_mdt_dt
            and fname not in modified_forms
        ):
            newer_mdt_date_forms.append(fname)

    current_set = set(current_files)
    new_forms = [f for f in current_files if f not in covered_set]
    removed_forms = [f for f in covered_ids if f not in current_set]

    reasons: list[str] = []
    if new_forms or newer_mdt_date_forms:
        reasons.append("NEW_FORM_ADDED")
    if removed_forms:
        reasons.append("FORM_REMOVED")
    if modified_forms:
        reasons.append("EXISTING_FORM_UPDATED")

    is_obsolete = len(reasons) > 0
    enriched = dict(summary_snapshot)
    enriched["has_summary"] = True
    enriched["is_obsolete"] = is_obsolete
    enriched["obsolete_reasons"] = reasons
    enriched["new_forms_since_summary"] = new_forms
    enriched["removed_forms_since_summary"] = removed_forms
    enriched["modified_forms_since_summary"] = modified_forms
    return enriched


def synthesize_patient_record_summary_from_forms(
    patient_label: str,
    forms: list[dict[str, Any]],
    domain: str = "oncology",
    model_used: str = "deterministic-synthesis",
) -> dict[str, Any]:
    """
    Build a grounded, non-prescriptive longitudinal `PatientRecordSummary` snapshot
    directly from the patient's chronological `PatientMDTForm` records.
    """
    form_cls = get_domain_mdt_form_cls(domain)
    series_list = build_patient_metric_series(forms, domain=domain)

    dated_forms: list[tuple[datetime | None, dict[str, Any]]] = []
    for doc in forms or []:
        if isinstance(doc, dict) and doc.get("file"):
            dated_forms.append((_extract_form_datetime(doc, form_cls), doc))
    dated_forms.sort(key=lambda item: item[0] or datetime.min)

    covered_ids = [str(doc["file"]) for _, doc in dated_forms]
    latest_dt = dated_forms[-1][0] if dated_forms else None
    latest_id = covered_ids[-1] if covered_ids else None

    first_date_str = (
        dated_forms[0][0].strftime("%d/%m/%Y")
        if dated_forms and dated_forms[0][0]
        else "date non renseignée"
    )
    last_date_str = (
        latest_dt.strftime("%d/%m/%Y") if latest_dt else "date non renseignée"
    )

    domain_label = "Amyotrophie Spinale (SMA)" if domain == "sma" else "Oncologie"
    overview = (
        f"Dossier longitudinal ({domain_label}) de {patient_label} consolidant "
        f"{len(covered_ids)} fiche(s) RCP du {first_date_str} au {last_date_str}."
    )

    notable_changes: list[str] = []
    for s in series_list:
        if len(s.points) >= 2:
            first_pt = s.points[0]
            last_pt = s.points[-1]
            delta_str = f" (Δ {last_pt.delta_display})" if last_pt.delta_display else ""
            unit_str = f" {s.unit}".rstrip() if s.unit else ""
            notable_changes.append(
                f"{s.label} : {first_pt.display_value}{unit_str} ({first_pt.form_date_label}) "
                f"→ {last_pt.display_value}{unit_str} ({last_pt.form_date_label}){delta_str}"
            )
        elif len(s.points) == 1:
            pt = s.points[0]
            unit_str = f" {s.unit}".rstrip() if s.unit else ""
            notable_changes.append(
                f"{s.label} : {pt.display_value}{unit_str} ({pt.form_date_label})"
            )

    decisions_recap: list[str] = []
    treatment_notes: list[str] = []
    vigilance_points: list[str] = []

    for dt, doc in dated_forms:
        d_label = dt.strftime("%d/%m/%Y") if dt else str(doc.get("file"))
        care = doc.get("CareOrientationProposal")
        if isinstance(care, dict):
            prop_type = care.get("proposed_care_type")
            rationale = care.get("clinical_rationale")
            if prop_type:
                decisions_recap.append(f"[{d_label}] {prop_type}")
            if rationale:
                treatment_notes.append(f"[{d_label}] {rationale}")

        mtd = doc.get("MTDCompleted")
        if isinstance(mtd, dict):
            nested = (
                mtd.get("mtd_complete")
                if isinstance(mtd.get("mtd_complete"), dict)
                else mtd
            )
            missing = nested.get("what_missing") if isinstance(nested, dict) else None
            if isinstance(missing, list):
                for item in missing:
                    item_s = str(item).strip()
                    if item_s and item_s not in vigilance_points:
                        vigilance_points.append(item_s)

    disease_evolution = (
        " ".join(treatment_notes[-2:])
        if treatment_notes
        else "Évolution clinique et thérapeutique documentée à travers les fiches RCP successives."
    )

    content = PatientRecordSummaryContent(
        clinical_trajectory_overview=overview,
        disease_and_treatment_evolution=disease_evolution,
        notable_metric_changes=notable_changes[:8],
        unresolved_vigilance_points=vigilance_points[:6],
        mdt_decisions_recap=decisions_recap,
        sources_used=covered_ids,
    )

    now = datetime.now()
    return {
        "has_summary": True,
        "generated_at": now.isoformat(),
        "covered_form_ids": covered_ids,
        "latest_form_id_at_generation": latest_id,
        "latest_form_date_at_generation": latest_dt.isoformat() if latest_dt else None,
        "model_used": model_used,
        "is_obsolete": False,
        "obsolete_reasons": [],
        "new_forms_since_summary": [],
        "removed_forms_since_summary": [],
        "modified_forms_since_summary": [],
        "content": content.model_dump(mode="json"),
    }
