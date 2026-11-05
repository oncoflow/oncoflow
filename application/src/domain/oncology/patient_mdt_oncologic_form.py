from typing import List, Optional, ClassVar
from datetime import datetime

from pydantic import Field

from src.domain.common.common_ressources import *  # noqa: F403

from src.application.agent.agent import OncowflowAgent
from src.domain.oncology.agents import Agents
from src.domain.common.patient_mdt_common_form import PatientMDTForm


class PatientMDTOncologicForm(PatientMDTForm):
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

    class CancerDescription(PatientMDTForm.default_model):
        """
        Histological characterization, TNM staging, metastatic spread, and RECIST response
        """

        type_of_cancer: str = Field(
            default="Non renseigné",
            description="Histological type of the tumor (e.g., ductal adenocarcinoma, squamous cell carcinoma, hepatocellular carcinoma, neuroendocrine tumor)",
        )
        histological_grade: Optional[str] = Field(
            default=None,
            description="Histological differentiation grade (e.g., G1 well differentiated, G2 moderately differentiated, G3 poorly differentiated, or Ki-67 index %)",
        )
        tnm_status: Optional[str] = Field(
            default=None,
            description="Clinical or pathological TNM classification (e.g., cT3N1M0, ypT1N0M0)",
        )
        figo_stage: Optional[str] = Field(
            default=None,
            description="Overall stage (AJCC/UICC I-IV or FIGO stage if applicable)",
        )
        metastatic_status: Optional[bool] = Field(
            default=None,
            description="True if distant metastases are present (M1), False if localized (M0)",
        )
        metastatic_sites: list[str] = Field(
            default_factory=list,
            description="List of organs affected by distant metastases (e.g., liver, lung, peritoneum, bone, distant lymph nodes)",
        )
        target_lesion_size_mm: Optional[float | int | str] = Field(
            default=None,
            description="Size of the primary tumor or main target lesion in millimeters (mm)",
        )
        recist_response: Optional[str] = Field(
            default=None,
            description="Radiological response according to RECIST 1.1: Baseline / Bilan initial, Complete Response (RC), Partial Response (RP), Stable Disease (SD), or Progressive Disease (PD)",
        )

        question: ClassVar[str] = (
            "Extract the histological type and differentiation grade of the tumor, the TNM staging (cTNM or ypTNM), whether distant metastases are present and their sites, the size of the primary/target lesion in mm, and the RECIST 1.1 radiological evolution if mentioned."
        )

    class TumorBiology(PatientMDTForm.default_model):
        """
        Biology of the tumor
        """

        msi_state: Optional[bool] = Field(
            default=None,
            description="Is the tumor MSI (True) or MSS (False)",
        )
        ca19_9: Optional[float | int | str] = Field(
            default=None,
            description="Serum CA 19-9 tumor marker level (U/mL)",
        )
        ace: Optional[float | int | str] = Field(
            default=None,
            description="Serum CEA / ACE (Carcinoembryonic Antigen) tumor marker level (ng/mL)",
        )
        afp: Optional[float | int | str] = Field(
            default=None,
            description="Serum Alpha-Fetoprotein (AFP) tumor marker level (ng/mL, crucial for hepatocellular carcinoma)",
        )
        dpd_uracilemia: Optional[float | int | str] = Field(
            default=None,
            description="Pre-therapeutic plasma uracilemia (ng/mL) or DPD deficiency status (mandatory in France before 5-FU / capecitabine)",
        )
        ras_braf_status: Optional[str] = Field(
            default=None,
            description="KRAS, NRAS, and BRAF molecular mutation status (e.g., KRAS G12D mutated, RAS/BRAF wild-type)",
        )
        her2_status: Optional[str] = Field(
            default=None,
            description="HER2 overexpression/amplification and PD-L1 CPS/TPS status if tested",
        )

        question: ClassVar[str] = (
            "Extract tumor biology and biomarkers: MSI/MSS (MMR) status, serum tumor markers (CA 19-9 in U/mL, ACE/CEA in ng/mL, AFP in ng/mL), pre-therapeutic DPD / uracilemia (ng/mL), and molecular alterations (KRAS, NRAS, BRAF, HER2, PD-L1 CPS). Set missing items to null."
        )

    class SurgicalStatus(PatientMDTForm.default_model):
        """
        Vascular resectability assessment and surgical margin status
        """

        resectability_status: Optional[str] = Field(
            default=None,
            description="Surgical and vascular resectability status according to TNCD criteria: Resectable, Borderline, Locally advanced, Unresectable, or Metastatic",
            json_schema_extra={
                "options": [
                    "Resectable",
                    "Borderline",
                    "Locally advanced",
                    "Unresectable",
                    "Metastatic",
                ]
            },
        )
        surgery_done: bool = Field(
            default=False,
            description="Has a tumor resection surgery been performed?",
        )
        resection_margin: Optional[str] = Field(
            default=None,
            description="Pathological resection margin status if operated: R0 (clear margins), R1 (microscopic residual tumor), or R2 (macroscopic residual tumor)",
            json_schema_extra={
                "options": [
                    "R0",
                    "R1",
                    "R2",
                ]
            },
        )

        question: ClassVar[str] = (
            "Determine the surgical resectability status of the tumor (Resectable, Borderline, Locally advanced, Unresectable, or Metastatic based on vascular contact and staging), whether tumor resection was performed, and the resection margin status (R0, R1, R2) if available."
        )

    class NutritionalStatus(PatientMDTForm.default_model):
        """
        Nutritional assessment, weight evolution, and body mass index
        """

        weight_kg: Optional[float | int | str] = Field(
            default=None,
            description="Current patient weight in kilograms (kg)",
        )
        weight_loss_percent: Optional[float | int | str] = Field(
            default=None,
            description="Percentage of weight loss compared to baseline weight (%)",
        )
        bmi: Optional[float | int | str] = Field(
            default=None,
            description="Body Mass Index (BMI / IMC) in kg/m²",
        )
        nutritional_status: Optional[str] = Field(
            default=None,
            description="Overall nutritional status (Normal, Moderate malnutrition / Dénutrition modérée, Severe malnutrition / Dénutrition sévère)",
        )

        question: ClassVar[str] = (
            "Extract the patient's nutritional parameters: current weight (kg), weight loss percentage (%), BMI (IMC in kg/m²), and overall nutritional status."
        )

    class HepaticStatus(PatientMDTForm.default_model):
        """
        Hepatic biological function, bilirubin level, Child-Pugh score, and BCLC stage
        """

        bilirubin_umol_l: Optional[float | int | str] = Field(
            default=None,
            description="Total serum bilirubin level in µmol/L (crucial for jaundice, biliary drainage indication, and chemotherapy eligibility)",
        )
        child_pugh_score: Optional[str] = Field(
            default=None,
            description="Child-Pugh liver function class and score (e.g., A5, A6, B7, B8, C10) if cirrhosis or hepatocellular carcinoma",
        )
        bclc_stage: Optional[str] = Field(
            default=None,
            description="Barcelona Clinic Liver Cancer (BCLC) stage (0, A, B, C, D) for hepatocellular carcinoma",
        )

        question: ClassVar[str] = (
            "Extract hepatic function indicators: total bilirubin level (µmol/L), Child-Pugh score/class (A5 to C15), and BCLC stage if applicable."
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
            Based on the multidisciplinary oncology expert debate, synthesize a pre-MDT orientation proposal to assist the medical board (do not replace the physicians' final decision):
            Determine if an initiation or adaptation of medical, surgical, or radiological care should be discussed for this patient.
            If yes, specify:
            1. The suggested priority level (`suggested_priority`) for the MDT discussion.
               CRITICAL SAFETY RULE: If even a single expert in the debate recommends or identifies that the case is urgent or high priority (e.g., due to rapid tumor progression, biliary obstruction, or suspected metastases), you MUST default to classifying `suggested_priority` as urgent (high priority), regardless of whether other experts disagree or recommend a lower priority.
            2. What kind of care modality (`proposed_care_type`) should be discussed (e.g., surgery, chemotherapy, biliary drainage, endoscopy, radiotherapy, or surveillance).
            Provide a clear `clinical_rationale` detailing the positions of the experts and TNCD references, especially highlighting any divergence in opinions regarding urgency.
            """

    # class ExpertPancreasAnswer(default_model):

    #     expert_relevant: bool = Field(description="Is Pancreas Expert is relevant")

    #     why_relevant: str =  Field( description="Explain why expert is relevant or not and why this priority is given" )

    #     sources_relevant: list[Reference] =  Field( description="Give the sources of your relevant answer" )

    #     patient_priority: PatientPriority = Field(
    #         description="patient treatment emergency"
    #     )

    #     suggetions: list[ExpertSuggestion] = Field(
    #         description="One suggetion by item, this list can be empty if expert is not relevant"
    #     )

    #     question: ClassVar[str] = (
    #         """
    #         As expert, tell me if the patient must be threat urgently for the pancreas, if your expertise is relevant and why do you have answer that.
    #         """
    #     )
    # class ExpertOesophagusAnswer(default_model):

    #     expert_relevant: bool = Field(description="Is Oesophagus Expert is relevant")

    #     why_relevant: str =  Field( description="Explain why expert is relevant or not and why this priority is given" )

    #     sources_relevant: list[Reference] =  Field( description="Give the sources of your relevant answer" )

    #     patient_priority: PatientPriority = Field(
    #         description="patient treatment emergency"
    #     )

    #     suggetions: list[ExpertSuggestion] = Field(
    #         description="One suggetion by item, this list can be empty if expert is not relevant"
    #     )

    #     question: ClassVar[str] = (
    #         "As expert, tell me if the patient must be threat urgently for the oesophagus, if your expertise is relevant and why do you have answer that."
    #     )

    # class ExpertHepatocellularAnswer(default_model):

    #     expert_relevant: bool = Field(description="Is Oesophagus Expert is relevant")

    #     why_relevant: str =  Field( description="Explain why expert is relevant or not and why this priority is given" )

    #     sources_relevant: list[Reference] =  Field( description="Give the sources of your relevant answer" )

    #     patient_priority: PatientPriority = Field(
    #         description="patient treatment emergency"
    #     )

    #     suggetions: list[ExpertSuggestion] = Field(
    #         description="One suggetion by item"
    #     )

    #     question: ClassVar[str] = (
    #         "As expert, tell me if the patient must be threat urgently for the hepatocellular, if your expertise is relevant and why do you have answer that."
    #     )

    #  // // // // // //  WORK IN PROGRESS

    # class ClinicalTrial(default_model):

    #     trial_title: str = Field(description="Title of the trial")
    #     inclusion_criteria: List[str] = Field(description="List of inclusion criteria")
    #     non_inclusion_criteria: List[str] = Field(description="List of non-inclusion criteria")

    #     question: ClassVar[str] = "Tell me the name, inclusion and non-inclusion criteria of this clinical trial ?"

    # class PreviousTreatments(default_model):

    #     treaments: Optional[List[PreviousTreatmentData]] = Field(description="List of treaments already done, can be None")

    #     question: ClassVar[str] = "Tell me if curative or palliative treaments like surgery, chemotherapy, radiotherapy and immunotherapy have already been done ?"

    # class TumorType(default_model):

    #     # cancer_location: CancerTypesEnum = Field(description="Location of the tumor")
    #     tumor: str = Field(description="Tumor present")
    #     # cancer_name: str = Field(description="Location of the tumor")
    #     question: ClassVar[str] = "Tell me where is located the primary tumor ?"

    # class MetastaticState(default_model):
    #     """
    #     Tumor metastatic state.
    # class MetastaticState(default_model):
    #     """
    #     Tumor metastatic state.

    #     Attributes:
    #         metastatic_disease (bool): Tumor metastatic state (True if present, False otherwise).
    #         metastatic_location (Optional[list[MetastaticLocationsEnum]]): Organs affected by metastasis.
    #     Attributes:
    #         metastatic_disease (bool): Tumor metastatic state (True if present, False otherwise).
    #         metastatic_location (Optional[list[MetastaticLocationsEnum]]): Organs affected by metastasis.

    #     Examples:
    #         >>> metastatic_state = MetastaticState(
    #                 metastatic_disease=True,
    #                 metastatic_location=[MetastaticLocationsEnum.BONE, MetastaticLocationsEnum.LIVER]
    #             )
    #     """
    #     metastatic_disease: bool = Field(description="Tumor metastatic state (True if present, False otherwise)")
    #     metastatic_location: Optional[list[MetastaticLocationsEnum]] = Field(description="Organs affected by metastasis")
    #     Examples:
    #         >>> metastatic_state = MetastaticState(
    #                 metastatic_disease=True,
    #                 metastatic_location=[MetastaticLocationsEnum.BONE, MetastaticLocationsEnum.LIVER]
    #             )
    #     """
    #     metastatic_disease: bool = Field(description="Tumor metastatic state (True if present, False otherwise)")
    #     metastatic_location: Optional[list[MetastaticLocationsEnum]] = Field(description="Organs affected by metastasis")

    #     question: ClassVar[str] = "Tell me if the tumor is metastatic or not, and which organs are involved."

    # class RadiologicExams(default_model):

    #     exams_list: Optional[list[RadiologicalExamination]] = Field(description="List of radiological exams")

    #     question: ClassVar[str] = "Give me a list of the radiological exams with date, name and type "

    #     question: ClassVar[str] = "Tell me if the tumor is metastatic or not, and which organs are involved."

    # class RadiologicExams(default_model):

    #     exams_list: Optional[list[RadiologicalExamination]] = Field(description="List of radiological exams")

    #     question: ClassVar[str] = "Give me a list of the radiological exams with date, name and type "

    # class PancreaticTumor(BaseModel):
    #     '''
    #     This class contains pancreatic tumor specific items
    #     '''

    #     onset_symptoms: Optional[List[PancreaticSymptomsEnum]] = Field(description="Contains initials symptoms")
    #     actual_symptoms: Optional[List[PancreaticSymptomsEnum]] = Field(description="Contains actual symptoms")

    # class LiverTumor(BaseModel):
    #     '''
    #     This class contains pancreatic tumor specific items
    #     '''

    #     onset_symptoms: Optional[List[LiverSymptomsEnum]] = Field(description="Contains initials symptoms")
    #     actual_symptoms: Optional[List[LiverSymptomsEnum]] = Field(description="Contains actual symptoms")

    # class Cardiologue(default_model):
    #     necessary: bool = Field(description="Est-ce que l'évaluation par un cardiologue est nécessaire pour traiter ce patient ?")
    #     reason: str = Field(description="Pourquoi ?")
    #     base_prompt: ClassVar[list] = [
    #         ("human", "Que vas-tu répondre si tu n'as pas tous les éléments?"),
    #         ("ai", "inconnu"),
    #         ("human", "Es tu prêt à répondre de manière brève et en francais à une question?"),
    #         ("ai", "Oui, quelle est la question concernant ce patient ?"),
    #         ("human", "{question}"),
    #     ]
    #     models: ClassVar[list] = ["phi3"]
    #     ressources: ClassVar[list] = ["TNCDPANCREAS.pdf"]
    #         ("ai", "Alors je réponds qu'une évaluation par un chirurgien est souhaitable et je justifie avec les éléments du TNCD et du dossier du patient"),
    #         ("human", "{question}"),
    #     ]
    #     models: ClassVar[list] = ["phi3", "llama3-chatqa"]
    #    ressources: ClassVar[list] = ["TNCDPANCREAS.pdf"]
    #     question: ClassVar[str] = "Alors réponds moi, est-qu'une une évaluation du dossier par un chirurgien pancréatique est nécessaire  ?"

    # class ChirurgienHepatique(default_model):
    #     necessary: bool = Field(description="Est-ce que l'évaluation par un chirurgien hépatique est nécessaire ?")
    #     reason: str = Field(description="Pourquoi ?")
    #     base_prompt: ClassVar[list] = [
    #         ("human", "Que vas-tu répondre si tu n'as pas tous les éléments?"),
    #         ("ai", "inconnu"),
    #         ("human", "Es tu prêt à répondre de manière brève et en francais à une question?"),
    #         ("ai", "Oui, quelle est la question concernant ce patient ?"),
    #         ("human", "{question}"),
    #     ]
    #     models: ClassVar[list] = ["phi3"]
    #     ressources: ClassVar[list] = ["TNCDPANCREAS.pdf"]
    #     question: ClassVar[str] = "En te basant sur les traitements possibles à proposer à ce patient, est-ce qu'une évaluation par un chirurgien hépatique est nécessaire ?"

    # class ChirurgienColorectal(default_model):
    #     necessary: bool = Field(description="Est-ce que l'évaluation par un chirurgien colorectal est nécessaire ?")
    #     reason: str = Field(description="Pourquoi ?")
    #     base_prompt: ClassVar[list] = [
    #         ("human", "Que vas-tu répondre si tu n'as pas tous les éléments?"),
    #         ("ai", "inconnu"),
    #         ("human", "Es tu prêt à répondre de manière brève et en francais à une question?"),
    #         ("ai", "Oui, quelle est la question concernant ce patient ?"),
    #         ("human", "{question}"),
    #     ]
    #     models: ClassVar[list] = ["phi3"]
    #     ressources: ClassVar[list] = ["TNCDPANCREAS.pdf"]
    #     question: ClassVar[str] = "En te basant sur les traitements possibles à proposer à ce patient, est-ce qu'une évaluation par un chirurgien colorectal est nécessaire ?"

    # class EssaiClinique(default_model):
    #     necessary: bool = Field(description="Est-ce qu'un essai clinique peut être proposé au patient ?")
    #     reason: str = Field(description="Pourquoi ?")
    #     trial_name: str = Field(description="Nom de l'essai clinique à proposer au patient")
    #     base_prompt: ClassVar[list] = [
    #         ("human", "Que vas-tu répondre si tu n'as pas tous les éléments?"),
    #         ("ai", "inconnu"),
    #         ("human", "Es tu prêt à répondre de manière brève et en francais à une question?"),
    #         ("ai", "Oui, quelle est la question concernant ce patient ?"),
    #         ("human", "{question}"),
    #     ]
    #     models: ClassVar[list] = ["phi3"]
    #     ressources: ClassVar[list] = ["TNCDPANCREAS.pdf"]
    #     question: ClassVar[str] = "En te basant sur les traitements possibles à proposer à ce patient, est-ce qu'une évaluation par un chirurgien colorectal est nécessaire ?"
