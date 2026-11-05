from typing import Any, ClassVar, Optional
import re

from pydantic import Field, field_validator

from src.domain.common.common_ressources import *  # noqa: F403

from src.application.agent.agent import OncowflowAgent
from src.domain.sma.agents import Agents
from src.domain.common.patient_mdt_common_form import PatientMDTForm


class PatientMDTSmaForm(PatientMDTForm):
    """
    This class contains all patient and SMA disease information for the report.
    """

    class PatientPerformanceStatus(PatientMDTForm.default_model):
        """
        Patient WHO performance status
        """

        performance_status: WHOPerformanceStatus = Field(  # noqa: F405
            description="WHO/OMS performance status of the patient, score from 0 to 4"
        )

        question: ClassVar[str] = (
            "Determine the WHO performance status of the patient (0-4). Look for 'OMS', 'WHO', or 'Performance Status' in the document. If not found, indicate it."
        )

    class GeneticDiagnosis(PatientMDTForm.default_model):
        """
        Genetic characteristics of Spinal Muscular Atrophy (SMN1 mutation and SMN2 copy number)
        """

        smn1_deletion_confirmed: bool = Field(
            description="Is the homozygous deletion or mutation of SMN1 confirmed?"
        )
        smn2_copy_count: int = Field(
            ge=0,
            le=10,
            description="Number of SMN2 backup gene copies (crucial for prognosis and treatment eligibility)",
        )
        other_genetic_variants: Optional[str] = Field(
            default=None,
            description="Other genetic modifiers or variations found, if any",
        )

        question: ClassVar[str] = (
            "Extract molecular genetic testing results. Confirm if the SMN1 homozygous deletion is present and find the exact number of SMN2 copies (typically 1 to 5 copies)."
        )

    class MotorFunctionStatus(PatientMDTForm.default_model):
        """
        SMA clinical classification and standardized motor scale scores
        """

        sma_type: str = Field(
            description="Clinical type of SMA: Type 1 (Werdnig-Hoffmann), Type 2, Type 3 (Kugelberg-Welander), or Type 4",
            json_schema_extra={
                "options": [
                    "Type 1",
                    "Type 2",
                    "Type 3",
                    "Type 4",
                    "Pré-symptomatique",
                ]
            },
        )
        motor_milestones: list[str] = Field(
            description="Achieved motor milestones (e.g. head control, sitting unsupported, standing, independent walking)"
        )
        hfmse_score: Optional[int | float | str] = Field(
            default=None,
            description="Hammersmith Functional Motor Scale Expanded (HFMSE) raw score (0-66, ratio, bilateral, or clinical note)",
        )
        chop_intend_score: Optional[int | float | str] = Field(
            default=None,
            description="CHOP INTEND raw score (usually for Type 1 infants, 0-64, ratio, or clinical note)",
        )
        rulm_score: Optional[int | float | str] = Field(
            default=None,
            description="Revised Upper Limb Module (RULM) raw score (0-37, ratio, bilateral D/G, or clinical note)",
        )

        @staticmethod
        def _validate_raw_motor_scale(
            value: Any, min_val: float, max_val: float, label: str
        ) -> int | float | str | None:
            """Validate a motor scale value while preserving raw ratios, bilateral scores, and clinical notes."""
            if value is None:
                return None
            if isinstance(value, bool):
                raise ValueError(f"{label} cannot be a boolean.")
            if isinstance(value, (int, float)):
                if float(value) < min_val or float(value) > max_val:
                    raise ValueError(
                        f"{label} score must be between {min_val:g} and {max_val:g}."
                    )
                return value
            if isinstance(value, str):
                cleaned = value.strip()
                if not cleaned:
                    return None
                if re.fullmatch(r"[-+]?\d+(?:\.\d+)?", cleaned):
                    num = float(cleaned)
                    if num < min_val or num > max_val:
                        raise ValueError(
                            f"{label} score must be between {min_val:g} and {max_val:g}."
                        )
                    return int(num) if re.fullmatch(r"[-+]?\d+", cleaned) else num
                return cleaned
            raise ValueError(f"Unsupported type for {label}.")

        @field_validator("hfmse_score", mode="before")
        @classmethod
        def validate_hfmse_score(cls, v: Any) -> int | float | str | None:
            return cls._validate_raw_motor_scale(v, 0, 66, "HFMSE")

        @field_validator("chop_intend_score", mode="before")
        @classmethod
        def validate_chop_intend_score(cls, v: Any) -> int | float | str | None:
            return cls._validate_raw_motor_scale(v, 0, 64, "CHOP INTEND")

        @field_validator("rulm_score", mode="before")
        @classmethod
        def validate_rulm_score(cls, v: Any) -> int | float | str | None:
            return cls._validate_raw_motor_scale(v, 0, 37, "RULM")

        question: ClassVar[str] = (
            "Determine the SMA clinical type (1, 2, 3, or 4), list the patient's current motor milestones, and extract any standardized motor scale scores found in the clinical records (HFMSE, CHOP INTEND, RULM)."
        )

    class RespiratoryFunction(PatientMDTForm.default_model):
        """
        Respiratory status and mechanical ventilation requirements
        """

        requires_ventilation_support: bool = Field(
            description="Does the patient require respiratory assistance?"
        )
        ventilation_type: Optional[str] = Field(
            default=None,
            description="Type of support: Non-invasive ventilation (NIV/BiPAP), Tracheostomy, or None",
            json_schema_extra={
                "options": [
                    "None",
                    "Non-invasive ventilation (NIV/BiPAP)",
                    "Tracheostomy",
                ]
            },
        )
        daily_ventilation_hours: Optional[float] = Field(
            default=None,
            ge=0,
            le=24,
            description="Number of hours of ventilation per day",
        )
        uses_cough_assist: bool = Field(
            description="Does the patient use a mechanical insufflator-exsufflator (cough assist)?"
        )
        forced_vital_capacity_percent: Optional[float] = Field(
            default=None,
            ge=0,
            le=150,
            description="Forced Vital Capacity (FVC / CVF) in % of predicted value",
        )

        question: ClassVar[str] = (
            "Extract respiratory evaluations: check if the patient uses ventilation support (NIV, tracheostomy) or a cough assist machine, and look for pulmonary function test values like FVC (CVF) percentage."
        )

    class OrthopedicAndSpineStatus(PatientMDTForm.default_model):
        """
        Spine deformities and joint contractures assessment
        """

        has_scoliosis: bool = Field(description="Presence of scoliosis")
        scoliosis_cobb_angle: Optional[float] = Field(
            default=None,
            ge=0,
            le=180,
            description="Scoliosis Cobb angle in degrees if measured",
        )
        spine_surgery_history: bool = Field(
            description="Has the patient undergone spinal fusion / arthrodesis?"
        )
        joint_contractures: list[str] = Field(
            description="Affected joints with contractures (e.g. hips, knees, ankles)"
        )
        wheelchair_user: bool = Field(
            description="Does the patient require a wheelchair (manual or electric)?"
        )

        question: ClassVar[str] = (
            "Search for spine and orthopedic assessments. Check for scoliosis presence, the Cobb angle, history of spinal surgery, joints affected by contractures, and whether the patient is wheelchair-dependent."
        )

    class BulbarAndNutritionalStatus(PatientMDTForm.default_model):
        """
        Swallowing abilities, feeding methods, and growth/weight monitoring
        """

        has_dysphagia: bool = Field(
            description="Does the patient have swallowing difficulties?"
        )
        feeding_mode: str = Field(
            description="Primary feeding mode: Oral, Oral with thickening, Gastrostomy tube (G-tube / GPE), or Nasogastric tube",
            json_schema_extra={
                "options": [
                    "Oral",
                    "Oral with thickening",
                    "Gastrostomy tube (G-tube / GPE)",
                    "Nasogastric tube",
                ]
            },
        )
        history_aspiration_pneumonia: bool = Field(
            description="History of aspiration pneumonia (fausses routes)"
        )
        nutritional_status: str = Field(
            description="Nutritional status: Normal, Failure to thrive / Underweight, Overweight",
            json_schema_extra={
                "options": [
                    "Normal",
                    "Failure to thrive / Underweight",
                    "Overweight",
                ]
            },
        )

        question: ClassVar[str] = (
            "Extract information regarding bulbar function: presence of dysphagia, history of aspiration pneumonia, current feeding method (oral or tube feeding), and overall nutritional/weight monitoring."
        )

    class RadiologicExams(PatientMDTForm.default_model):
        """
        List of radiological exams
        """

        exams_list: list[RadiologicalExamination] = Field(  # noqa: F405
            description="List of radiological exams"
        )

        question: ClassVar[str] = (
            "List all radiological exams found in the documents. Include date, name, type, and a summary of results for each."
        )

    class ExpertAnswer(PatientMDTForm.ExpertAnswer):
        agents: ClassVar[list[type[OncowflowAgent]]] = [
            Agents.Neurologist_expert_agent,
            Agents.Geneticist_expert_agent,
            Agents.Pulmonologist_expert_agent,
            Agents.Physiotherapy_expert_agent,
            Agents.Orthopedist_expert_agent,
        ]

    class MTDCompleted(PatientMDTForm.MTDCompleted):
        agents: ClassVar[list[type[OncowflowAgent]]] = Agents().expert_agents

    class CareOrientationProposal(PatientMDTForm.CareOrientationProposal):
        """
        Pre-MDT collaborative synthesis proposing whether an initiation or adaptation
        of patient care should be discussed by the medical board, its priority, and rationale.
        """

        agents: ClassVar[list[type[OncowflowAgent]]] = Agents().expert_agents
        collaborative = True

        question: ClassVar[str] = """
            Based on the multidisciplinary SMA expert debate (neurologist, geneticist, pulmonologist, orthopedist, physiotherapist), synthesize a pre-MDT orientation proposal to assist the medical board (do not replace the physicians' final decision):
            Determine if an initiation or adaptation of therapeutic, respiratory, nutritional, orthopedic, or rehabilitative care should be discussed for this SMA patient.
            If yes, specify:
            1. The suggested priority level (`suggested_priority`) for the MDT discussion.
               CRITICAL SAFETY RULE: In Spinal Muscular Atrophy, motor neuron loss is irreversible ("Time is Motoneuron") and respiratory/bulbar decompensations are life-threatening. If even a single expert in the debate flags the case as urgent or high priority (e.g., infant SMA Type 1 or pre-symptomatic newborn needing immediate disease-modifying therapy, rapid motor regression on HFMSE/CHOP-INTEND/RULM, respiratory insufficiency requiring NIV/Cough Assist, dysphagia with aspiration pneumonia risk, or rapidly progressing scoliosis compromising lung function), you MUST default to classifying `suggested_priority` as urgent (high priority), regardless of whether other experts recommend a lower priority.
            2. What kind of care modality (`proposed_care_type`) should be discussed (e.g., SMN-targeted disease-modifying therapy initiation/switch [nusinersen, risdiplam, onasemnogene abeparvovec], NIV/BiPAP or Cough Assist adaptation, nutritional/gastrostomy support, orthopedic spine management/arthrodesis, or specialized rehabilitation).
            Provide a clear `clinical_rationale` detailing the positions of the experts and French PNDS SMA guidelines, especially highlighting any divergence in opinions regarding urgency.
            """
