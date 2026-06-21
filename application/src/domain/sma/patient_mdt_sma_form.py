from typing import List, Optional, ClassVar
from datetime import datetime

from pydantic import Field

from src.domain.common.common_ressources import *  # noqa: F403

from src.application.agent.agent import OncowflowAgent
from src.domain.oncology.agents import Agents
from src.domain.common.patient_mdt_common_form import PatientMDTForm


class PatientMDTSmaForm(PatientMDTForm):
    """
    This class contains all patient and oncological disease information for the report.
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

    class TumorLocation(PatientMDTForm.default_model):
        """
        Location of the tumor
        """

        tumor_location: PrimaryOrganEnum = Field(  # noqa: F405
            description="Organ where the primary tumor is present"
        )

        question: ClassVar[str] = (
            "Identify the primary organ where the tumor is located. Search for the principal diagnosis or the primary tumor site."
        )

    class TumorBiology(PatientMDTForm.default_model):
        """
        Biology of the tumor
        """

        msi_state: Optional[bool] = Field(description="Is the tumor MSI or MSS")

        question: ClassVar[str] = (
            "Is the tumor classified as MSI (Microsatellite Instability) or MSS (Microsatellite Stable)? Search for 'MSI', 'MSS', 'instabilité microsatellitaire', or 'statut MMR'. If not mentioned, state it."
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

    class PreviousCurativeSurgery(PatientMDTForm.default_model):
        """
        Previous curative surgery
        """

        previous_curative_surgery: bool = Field(
            description="If a curative surgery has already been done"
        )
        previous_curative_surgery_date: Optional[datetime] = Field(
            description="Date of the surgery"
        )

        question: ClassVar[str] = (
            "Has a curative surgery already been performed for this tumor? If yes, provide the date."
        )

    class PlannedCurativeSurgery(PatientMDTForm.default_model):
        """
        Planned curative surgery
        """

        planned_curative_surgery: bool = Field(
            description="If a curative surgery has been planned"
        )

        question: ClassVar[str] = "Is a curative surgery planned for this tumor?"

    class ChemotherapyTreament(PatientMDTForm.default_model):
        """
        Chemotherapy treatments
        """

        chemotherapy: bool = Field(
            description="If a chemotherapy has already been done"
        )
        chemotherapy_list: Optional[List[ChemotherapyData]] = Field(  # noqa: F405
            description="List of chemotherapies that have been done"
        )

        question: ClassVar[str] = (
            "Has the patient received any chemotherapy for this tumor? If yes, provide details of the treatments."
        )

    class ExpertAnswer(PatientMDTForm.default_model):
        agents: ClassVar[list[type[OncowflowAgent]]] = [
            Agents.Pancreas_expert_agent,
            Agents.Oesophagus_expert_agent,
            Agents.Hepatocellular_expert_agent,
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
