import inspect
import json
import os

from typing import List, Optional, ClassVar
from datetime import datetime

from pydantic import BaseModel, Field, PastDatetime, model_validator

from src.domain.common_ressources import *  # noqa: F403

from src.application.config import AppConfig
from src.domain.agents import Agents
from src.application.agent.agent import OncowflowAgent
from src.application.reader import DocumentReader
from src.infrastructure.documents.mongodb import Mongodb
from src.application.agent.collaborate import collaborative_debate


class PatientMDTOncologicForm(DocumentReader):
    """
    This class contains all patient and oncological disease information for the report.
    """

    mtd_datas: dict = {}
    mtd_datas_json: dict = {}
    db_client = None

    def __init__(self, config: AppConfig, document: str) -> None:
        super(PatientMDTOncologicForm, self).__init__(config=config, document=document)

        self.mtd_datas["file"] = document
        self.mtd_datas["execution_times"] = {}

        self.basemodel_list = [
            cls_attribute
            for cls_attribute in self.__class__.__dict__.values()
            if inspect.isclass(cls_attribute)
            and issubclass(cls_attribute, self.default_model)
            and cls_attribute.__name__ != "default_model"
        ]

        self.read_document()

        if config.rcp.display_type == "mongodb":
            self.db_client = Mongodb(config)
        else:
            self.logger.info(
                "DB Type %s not known, fallback to stdout", config.rcp.display_type
            )

        if self.db_client is not None:
            self.db_client.set_uniq_index(collection="rcp_info", field="file")
            db_document = self.db_client.get_or_create_document(
                collection="rcp_info", document={"file": document}
            )
            self.mtd_datas["id"] = db_document["_id"]
            if "execution_times" in db_document:
                self.mtd_datas["execution_times"] = db_document["execution_times"]
            self.dict_to_models(db_document)
        else:
            self.mtd_datas["id"] = None

    def dict_to_models(self, dic: dict, subkey=None):
        for key, value in dic.items():
            for m in self.basemodel_list:
                if m.__name__ == key:
                    if len(m.agents) > 1 and not getattr(m, "collaborative", False):
                        for a in m.agents:
                            if isinstance(value, dict) and a.agent_name in value:
                                self.mtd_datas[key] = {
                                    a.agent_name: m.model_validate(value[a.agent_name])
                                }
                    else:
                        if (
                            getattr(m, "collaborative", False)
                            and len(m.agents) > 1
                            and isinstance(value, dict)
                        ):
                            # Backward compatibility: extract nested data if saved in old agent-keyed format
                            has_any_field = any(
                                field in value for field in m.model_fields
                            )
                            if not has_any_field:
                                for a in m.agents:
                                    if a.agent_name in value:
                                        value = value[a.agent_name]
                                        break
                        self.mtd_datas[key] = m.model_validate(value)

    def read_all_models(self) -> dict:
        for model in self.basemodel_list:
            self.read_model(model)
        return self.mtd_datas

    def read_model(
        self,
        model: "type[PatientMDTOncologicForm.default_model]",
        upsert: bool = False,
        callbacks: list = None,
    ):
        import time

        if upsert and self.config.rcp.display_type == "mongodb":
            self.db_client = Mongodb(self.config)

        start_time = time.time()

        if getattr(model, "collaborative", False) and len(model.agents) > 1:
            datas = collaborative_debate(
                agents_classes=model.agents,
                question=model.question,
                output_format=model,
                config=self.config,
                mtd=self,
                logger=self.logger,
                callbacks=callbacks,
            )
            self.mtd_datas[model.__name__] = datas
        else:
            agents = [
                magent(config=self.config, mtd=self, output_format=model)
                for magent in model.agents
            ]
            memory = {}
            for a in agents:
                if memory and model.agents_memory:
                    model.question = f"""
                    Agents memory datas :
                    {memory}
                    {model.question}
                    """
                datas = json.loads(a.ask(model.question, callbacks=callbacks).json())
                self.logger.debug(f"DATAS : {datas} ...")
                if datas:
                    if isinstance(datas, dict):
                        datas["reasoning_thinking"] = getattr(
                            a, "latest_thinking", None
                        )
                    if model.agents_memory:
                        memory = memory | datas
                    if model.__name__ not in self.mtd_datas:
                        self.mtd_datas[model.__name__] = {}
                    if len(agents) > 1:
                        self.mtd_datas[model.__name__][a.agent_name] = datas
                    else:
                        self.mtd_datas[model.__name__] = datas
                del a
            del agents

        duration = time.time() - start_time
        if "execution_times" not in self.mtd_datas:
            self.mtd_datas["execution_times"] = {}
        self.mtd_datas["execution_times"][model.__name__] = duration

        if upsert and self.db_client is not None:
            self.logger.debug(
                f"Document final inserted: {json.dumps(self.mtd_datas, default=str)}"
            )
            self.db_client.update_doc(
                collection="rcp_info",
                filter={"file": self.mtd_datas["file"]},
                upsertable_data={
                    model.__name__: self.mtd_datas[model.__name__],
                    "execution_times": self.mtd_datas["execution_times"],
                },
            )
            self.db_client.close()

    def delete(self):
        if self.db_client is not None:
            self.db_client.delete_docs(
                collections=["rcp_info", "rcp_metadata"],
                filter={"file": self.mtd_datas["file"]},
            )
        if os.path.exists(self.document_path):
            os.remove(self.document_path)
        if self.db_client is not None:
            self.db_client.close()

    def insert_datas_in_db(self, replace: bool = True):
        if self.db_client is not None:
            if replace:
                self.db_client.delete_docs(
                    collections=["rcp_info", "rcp_metadata"],
                    filter={"file": self.mtd_datas["file"]},
                )
            self.db_client.prepare_insert_doc(
                collection="rcp_info", document=self.mtd_datas
            )
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
        agents: ClassVar[list[type[OncowflowAgent]]] = [Agents.Administratives_agent]
        agents_memory: ClassVar[bool] = False
        collaborative: ClassVar[bool] = False
        collaborative_agent: ClassVar[type[OncowflowAgent] | None] = None
        reasoning_thinking: ClassVar[str | None] = None
        time_execution: ClassVar[int | None] = None

    #  // // // // // Tested and Working classes // // // // //

    class PatientAdministrative(default_model):
        """
        Patient administrative informations
        """

        first_name: str = Field(description="First name of the patient")
        last_name: str = Field(description="Last name of the patient")
        born_name: Optional[str] = Field(
            description="Name of the patient at birth", default=None
        )

        age: int = Field(description="Age of the patient")
        date_birth: Optional[PastDatetime] = Field(
            description="Date of birth of the patient (Format: YYYY-MM-DD)"
        )
        date_rcp: Optional[datetime] = Field(
            description="Date of the MTD (Format: YYYY-MM-DD)"
        )
        gender: Gender = Field(description="Gender of the patient")  # noqa: F405

        @model_validator(mode="after")
        def check_dates_coherence(self):
            now = datetime.now()
            if self.date_birth and self.date_birth.year < (now.year - 150):
                self.date_birth = None

            if self.date_rcp and self.date_rcp.year < (now.year - 5):
                self.date_rcp = None

            if self.date_birth and self.date_rcp:
                if self.date_birth.replace(tzinfo=None) > self.date_rcp.replace(
                    tzinfo=None
                ):
                    raise ValueError("Date of birth must be before Date of RCP")
            return self

        question: ClassVar[
            str
        ] = """Search and Extract the patient's administrative details from MTD.
            1. Find the patient's First Name, Last Name, Age AND Date of birth. Note that age is often written as 'XX ans'. If age is missing but Date of birth is present, you can deduce the age based on the Date of RCP.
            2. Find the date of the MTD (RCP).
            3. Find the gender of the patient.
            If a value is not found, state it clearly.
            You can use tools multiple time for each element.
            Format all dates strictly as YYYY-MM-DD (e.g. 1956-06-04).
            Ensure dates are coherent:
            1. Date of birth must be less than 150 years ago.
            2. Date of RCP must be less than 5 years ago.
            3. Date of birth must be strictly before Date of RCP.
            """

    class PatientPerformanceStatus(default_model):
        """
        Patient WHO performance status
        """

        performance_status: WHOPerformanceStatus = Field(  # noqa: F405
            description="WHO/OMS performance status of the patient, score from 0 to 4"
        )

        question: ClassVar[str] = (
            "Determine the WHO performance status of the patient (0-4). Look for 'OMS', 'WHO', or 'Performance Status' in the document. If not found, indicate it."
        )

    class TumorLocation(default_model):
        """
        Location of the tumor
        """

        tumor_location: PrimaryOrganEnum = Field(  # noqa: F405
            description="Organ where the primary tumor is present"
        )

        question: ClassVar[str] = (
            "Identify the primary organ where the tumor is located. Search for the principal diagnosis or the primary tumor site."
        )

    class TumorBiology(default_model):
        """
        Biology of the tumor
        """

        msi_state: Optional[bool] = Field(description="Is the tumor MSI or MSS")

        question: ClassVar[str] = (
            "Is the tumor classified as MSI (Microsatellite Instability) or MSS (Microsatellite Stable)? Search for 'MSI', 'MSS', 'instabilité microsatellitaire', or 'statut MMR'. If not mentioned, state it."
        )

    class RadiologicExams(default_model):
        """
        List of radiological exams
        """

        exams_list: list[RadiologicalExamination] = Field(  # noqa: F405
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
        previous_curative_surgery_date: Optional[datetime] = Field(
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

        question: ClassVar[str] = "Is a curative surgery planned for this tumor?"

    class ChemotherapyTreament(default_model):
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

    class ExpertAnswer(default_model):
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

    class MTDCompleted(default_model):
        agents: ClassVar[list[type[OncowflowAgent]]] = Agents().expert_agents
        mtd_complete: MTDComplete = Field(description="Is the MDT file complete?")  # noqa: F405

        collaborative = True

        question: ClassVar[str] = """
            As an expert, determine if the MDT (Multidisciplinary Team) file is complete.
            Are there missing elements required for a treatment decision?
            You can use search_on_ressources tool what type of elements/documents is needed.
            You can use tools multiple times for each element
            """

    class isInterventionRequiered(default_model):
        """
        Consensus on whether an intervention is required, its urgency, and description.
        """

        agents: ClassVar[list[type[OncowflowAgent]]] = Agents().expert_agents
        collaborative = True

        intervention_required: bool = Field(
            description="Is a medical, surgical, or radiologic intervention required for this patient?"
        )
        urgency: Optional[PatientPriority] = Field(  # noqa: F405
            default=None,
            description="How urgently the intervention should be performed. None if no intervention is required.",
        )
        intervention_type: Optional[str] = Field(
            default=None,
            description="Type of intervention required (e.g., surgery, chemotherapy, biliary drainage, endoscopy, etc.). None if no intervention is required.",
        )
        justification: str = Field(
            description="Clinical justification for the consensus decision."
        )

        question: ClassVar[str] = """
            Based on the expert debate, determine if a medical, surgical, or radiological intervention is required for this patient.
            If yes, specify:
            1. If the intervention must be done urgently (rapidly) or not.
               CRITICAL SAFETY RULE: If even a single expert in the debate recommends or identifies that the intervention is urgent or high priority (e.g., if one expert says it is urgent due to rapid tumor progression or suspected metastases), you MUST default to classifying the overall urgency as urgent (high priority), regardless of whether other experts disagree or recommend a lower priority. The consensus must respect this safety principle and escalate to the highest urgency flagged.
            2. What kind of intervention is required.
            Provide a clear justification detailing the positions of the experts, especially highlighting any divergence in opinions regarding urgency.
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
