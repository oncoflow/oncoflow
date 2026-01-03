import inspect
import json

from typing import List, Optional, ClassVar
from datetime import datetime

from pydantic import BaseModel, Field, PastDate

from src.domain.common_ressources import *

from src.application.config import AppConfig
from src.domain.agents import Agents
from src.application.agent.agent import OncowflowAgent
from src.application.reader import DocumentReader
from src.infrastructure.documents.mongodb import Mongodb

class PatientMDTOncologicForm(DocumentReader):
    """
    This class contains all patient and oncological disease information for the report.
    """

    mtd_datas: dict = {}
    db_client = None

    def __init__(self, config=AppConfig, document=str) -> None:
        super(PatientMDTOncologicForm, self).__init__(config=config, document=document)

        self.read_document()

        if config.rcp.display_type == "mongodb":
            self.db_client = Mongodb(config)
        else:
            logger.info("DB Type %s not known, fallback to stdout", config.rcp.display_type)

        self.mtd_datas["file"] = document

        self.basemodel_list = [
            cls_attribute
            for cls_attribute in self.__class__.__dict__.values()
            if inspect.isclass(cls_attribute)
            and issubclass(cls_attribute, self.default_model)
            and cls_attribute.__name__ != "default_model"
        ]

    def read_all_models(self) -> dict:
        for model in self.basemodel_list:
            self.read_model(model)
        return self.mtd_datas

    def read_model(self, model):
        if len(model.agents) == 1:
            agent = model.agents[0](config=self.config, mtd=self, output_format=model)
            datas = agent.ask(model.question)
            self.logger.debug(f"DATAS : {datas} ...")
            if datas:
                self.mtd_datas[model.__name__] = datas
        else:
            for magent in model.agents:
                agent = magent(config=self.config, mtd=self, output_format=model)
                datas = agent.ask(model.question)
                self.logger.debug(f"DATAS : {datas} ...")
                if datas:
                    if model.__name__ not in self.mtd_datas:
                        self.mtd_datas[model.__name__] = {}
                    self.mtd_datas[model.__name__][magent.agent_name] = datas
        del agent

    def insert_datas_in_db(self, replace: bool = True):
        if self.db_client is not None:
            if replace:
                self.db_client.delete_docs(
                    collections=["rcp_info", "rcp_metadata"], filter={"file": self.mtd_datas["file"]}
                )
            self.db_client.prepare_insert_doc(collection="rcp_info", document=self.mtd_datas)
            self.db_client.insert_docs()
            self.db_client.close()


    @classmethod
    def parse_raw(cls, value):
        if isinstance(value, dict):
            return cls(**value)
        elif isinstance(value, str):
            return cls.parse_raw(json.loads(value))
        else:
            raise ValueError("Invalid input")

    class default_model(BaseModel):

        question: ClassVar[str] = ""
        agents: ClassVar[list[OncowflowAgent]] = [Agents.Administratives_agent]


    #  // // // // // Tested and Working classes // // // // //

    class PatientAdministrative(default_model):
        """
        Patient administrative informations
        """

        first_name: str = Field(description="First name of the patient")
        last_name: str = Field(description="Last name of the patient")
        age: int = Field(description="Age of the patient")
        date_birth: Optional[datetime] = Field(
            description="Date of birth of the patient"
        )
        gender: Gender = Field(description="Gender of the patient")

        question: ClassVar[str] = (
            "Extract the patient's administrative details: First Name, Last Name, Age, Date of Birth, and Gender."
        )

    class PatientPerformanceStatus(default_model):
        """
        Patient WHO performance status
        """

        performance_status: WHOPerformanceStatus = Field(
            description="WHO/OMS performance status of the patient, score from 0 to 4"
        )

        question: ClassVar[str] = (
            "Determine the WHO performance status of the patient (0-4)."
        )

    class TumorLocation(default_model):
        """
        Location of the tumor
        """

        tumor_location: PrimaryOrganEnum = Field(
            description="Organ where the primary tumor is present"
        )

        question: ClassVar[str] = "Identify the primary organ where the tumor is located."

    class TumorBiology(default_model):
        """
        Biology of the tumor
        """

        msi_state: Optional[bool] = Field(description="Is the tumor MSI or MSS")

        question: ClassVar[str] = "Is the tumor classified as MSI (Microsatellite Instability) or MSS (Microsatellite Stable)?"

    class RadiologicExams(default_model):
        """
        List of radiological exams
        """

        exams_list: list[RadiologicalExamination] = Field(
            description="List of radiological exams"
        )

        question: ClassVar[str] = (
            "List all radiological exams found in the documents. Include date, name, type, and a summary of results for each."
        )

    class PreviousCurativeSurgery(default_model):
        """
        Previous curative surgery
        """

        previous_curative_surgery: bool = Field(
            description="If a curative surgery has already been done"
        )
        previous_curative_surgery_date: Optional[PastDate] = Field(
            description="Date of the surgery"
        )

        question: ClassVar[str] = (
            "Has a curative surgery already been performed for this tumor? If yes, provide the date."
        )

    class PlannedCurativeSurgery(default_model):
        """
        Planned curative surgery
        """

        planned_curative_surgery: bool = Field(
            description="If a curative surgery has been planned"
        )

        question: ClassVar[str] = (
            "Is a curative surgery planned for this tumor?"
        )

    class ChemotherapyTreament(default_model):
        """
        Chemotherapy treatments
        """

        chemotherapy: bool = Field(
            description="If a chemotherapy has already been done"
        )
        chemotherapy_list: Optional[List[ChemotherapyData]] = Field(
            description="List of chemotherapies that have been done"
        )

        question: ClassVar[str] = (
            "Has the patient received any chemotherapy for this tumor? If yes, provide details of the treatments."
        )
    class ExpertAnswer(default_model):

        agents = [
            Agents.Pancreas_expert_agent,
            Agents.Oesophagus_expert_agent,
            Agents.Hepatocellular_expert_agent,
        ]

        expert_relevant: bool = Field(description="Is your expertise relevant for this patient's case?")

        patient_priority: PatientPriority = Field(
            description="Urgency of the patient's treatment"
        )

        why_relevant: str = Field(
            description="Explain why your expertise is relevant (or not) for this patient and justify the priority given."
        )

        sources_relevant: list[Reference] = Field(
            description="Give the sources of your relevant answer"
        )

        suggestions: list[ExpertSuggestion] = Field(
            description="List of suggestions. Empty if expert is not relevant."
        )

        question: ClassVar[str] = (
            """
            As an expert in your field, determine if the patient requires urgent treatment. Assess if your expertise is relevant to this case and explain your reasoning.
            """
        )

    class MTDCompleted(default_model):
        agents = [
            Agents.Pancreas_expert_agent,
            Agents.Oesophagus_expert_agent,
            Agents.Hepatocellular_expert_agent,
        ]
        mtd_complete: MTDComplete = Field(description="Is the MDT file complete?")

        question: ClassVar[str] = (
            """
            As an expert, determine if the MDT (Multidisciplinary Team) file is complete. Are there missing elements required for a decision?
            """
        )

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
