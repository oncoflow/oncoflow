from typing import Optional, ClassVar

from pydantic import Field

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
            description="Number of SMN2 backup gene copies (crucial for prognosis and treatment eligibility)"
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
            description="Clinical type of SMA: Type 1 (Werdnig-Hoffmann), Type 2, Type 3 (Kugelberg-Welander), or Type 4"
        )
        motor_milestones: list[str] = Field(
            description="Achieved motor milestones (e.g. head control, sitting unsupported, standing, independent walking)"
        )
        hfmse_score: Optional[int] = Field(
            default=None,
            description="Hammersmith Functional Motor Scale Expanded (HFMSE) score (0-66)",
        )
        chop_intend_score: Optional[int] = Field(
            default=None,
            description="CHOP INTEND score (usually for Type 1 infants, 0-64)",
        )
        rulm_score: Optional[int] = Field(
            default=None,
            description="Revised Upper Limb Module (RULM) score (0-37)",
        )

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
        )
        daily_ventilation_hours: Optional[float] = Field(
            default=None, description="Number of hours of ventilation per day"
        )
        uses_cough_assist: bool = Field(
            description="Does the patient use a mechanical insufflator-exsufflator (cough assist)?"
        )
        forced_vital_capacity_percent: Optional[float] = Field(
            default=None,
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
            default=None, description="Scoliosis Cobb angle in degrees if measured"
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
            description="Primary feeding mode: Oral, Oral with thickening, Gastrostomy tube (G-tube / GPE), or Nasogastric tube"
        )
        history_aspiration_pneumonia: bool = Field(
            description="History of aspiration pneumonia (fausses routes)"
        )
        nutritional_status: str = Field(
            description="Nutritional status: Normal, Failure to thrive / Underweight, Overweight"
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

    class ExpertAnswer(PatientMDTForm.default_model):
        agents: ClassVar[list[type[OncowflowAgent]]] = [
            Agents.Neurologist_expert_agent,
            Agents.Geneticist_expert_agent,
            Agents.Pulmonologist_expert_agent,
            Agents.Physiotherapy_expert_agent,
            Agents.Orthopedist_expert_agent,
        ]

        expert_relevant: bool = Field(
            description="Is your expertise relevant for this patient's case?"
        )

        patient_priority: PatientPriority = Field(  # noqa: F405
            description="Urgency of the patient's treatment"
        )

        why_relevant: str = Field(
            description="Explain why your expertise is relevant (or not) for this patient and justify the priority given."
        )

        sources_relevant: list[Reference] = Field(  # noqa: F405
            description="Give the sources of your relevant answer"
        )

        suggestions: list[ExpertSuggestion] = Field(  # noqa: F405
            description="List of suggestions. Empty if expert is not relevant."
        )

        question: ClassVar[str] = """
            As an expert in your field, determine if the patient requires urgent treatment. Assess if your expertise is relevant to this case and explain your reasoning.
            You can use tools multiple times for each element and have more scientific elements.
            """
