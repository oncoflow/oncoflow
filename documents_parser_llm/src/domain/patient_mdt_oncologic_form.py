import inspect
import json

from typing import List, Optional, ClassVar

from langchain_core.pydantic_v1 import BaseModel, Field, PastDate

from src.domain.common_ressources import *


class PatientMDTOncologicForm:
    """
    This class contains all patient and oncological disease information for the report.
    """

    base_prompt = [
        (
            "system",
            "You are a medical assistant, you have to answer questions based on this patient record: {context}.",
        )
    ]

    def __init__(self) -> None:
        self.datas = {}
        self.basemodel_list = [
            cls_attribute
            for cls_attribute in self.__class__.__dict__.values()
            if inspect.isclass(cls_attribute)
            and issubclass(cls_attribute, self.default_model)
            and cls_attribute.__name__ != "default_model"
        ]

    def set_datas(self, basemodel, datas) -> None:
        self.datas[basemodel.__name__] = datas

    def get_datas(self) -> dict:
        return json.loads(
            json.dumps(
                self.__dict__["datas"], default=lambda o: getattr(o, "__dict__", str(o))
            )
        )

    @classmethod
    def parse_raw(cls, value):
        if isinstance(value, dict):
            return cls(**value)
        elif isinstance(value, str):
            return cls.parse_raw(json.loads(value))
        else:
            raise ValueError("Invalid input")

    class default_model(BaseModel):
        base_prompt: ClassVar[list] = [
            ("system", "You have to answer the user question.\n {format_instructions}"),
            ("human", "Question: {question}"),
        ]
        prompt: ClassVar[list] = []
        models: ClassVar[list] = []
        question: ClassVar[str] = ""
        ressources: ClassVar[list] = []
        
    
     #  // // // // // Tested and Working classes // // // // //

    class PatientAdministrative(default_model):
        """
        Patient administrative informations
        """

        first_name: str = Field(description="First name of the patient")
        last_name: str = Field(description="Last name of the patient")
        age: int = Field(description="Age of the patient")
        date_birth: Optional[int] = Field(description="Date of birth of the patient")
        gender: Gender = Field(description="Gender of the patient")

        question: ClassVar[str] = (
            "Tell me the first name, Last name, age, date of birth and gender of the patient."
        )

    class PatientPerformanceStatus(default_model):
        """
        Patient WHO performance status
        """

        performance_status: WHOPerformanceStatus = Field(
            description="OMS performance status of the patient, from 0 to 4"
        )

        question: ClassVar[str] = (
            "Tell me the WHO performance status of the patient (0-4)."
        )
        performance_status: WHOPerformanceStatus = Field(
            description="OMS performance status of the patient, from 0 to 4"
        )

        question: ClassVar[str] = (
            "Tell me the WHO performance status of the patient (0-4)."
        )

    class TumorLocation(default_model):
        """
        Location of the tumor
        """

        tumor_location: PrimaryOrganEnum = Field(
            description="Organ where the primary tumor is present"
        )

        question: ClassVar[str] = "Tell me where is located the primary tumor ?"
    
    class TumorHistologicType(default_model):
        '''
        Histologic type of the tumor
        '''
        
        histologic_state: HistologicStateEnum = Field(description="Histological evidence of the tumor ")
        histologic_analysis: Optional[List[HistologicAnalysis]] = Field(description="Histological analysis done")
        
        question: ClassVar[str] = "Tell me where if tumor is histologicaly proven or suspected and when the histological samples were taken, with the following contributivity ?"
    
    class TumorHistologicType(default_model):
        '''
        Histologic type of the tumor
        '''
        
        histologic_state: HistologicStateEnum = Field(description="Histological evidence of the tumor ")
        histologic_analysis: Optional[List[HistologicAnalysis]] = Field(description="Histological analysis done")
        
        question: ClassVar[str] = "Tell me where if tumor is histologicaly proven or suspected and when the histological samples were taken, with the following contributivity ?"

    class TumorBiology(default_model):
        '''
        Biology of the tumor
        '''

        msi_state: Optional[bool] = Field(description="Is the tumor MSI or MSS")

        question: ClassVar[str] = "Tell me if the tumor is stated MSI or MSS ?"

    class RadiologicExams(default_model):
        """
        List of radiological exams
        """

        exams_list: Optional[list[RadiologicalExamination]] = Field(
            description="List of radiological exams"
        )

        question: ClassVar[str] = (
            "Give me a list of the radiological exams with date, name and type "
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
            "Tell me if a curative surgery has already been done for this tumor ?"
        )

    class PlannedCurativeSurgery(default_model):
        """
        Planned curative surgery
        """

        planned_curative_surgery: bool = Field(
            description="If a curative surgery has been planned"
        )

        question: ClassVar[str] = (
            "Tell me if a curative surgery has been planned for this tumor ?"
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
            "Tell me if one or several chemotherapies have already been done for this tumor?"
                )

    class LastBiologicalResults(default_model):
        '''
        Last biological laboratory results
        '''
        
        labtests: Optional[List[LabTest]] = Field(description="List of last laboratory results")
        
                
    class LastBiologicalResults(default_model):
        '''
        Last biological laboratory results
        '''
        
        labtests: Optional[List[LabTest]] = Field(description="List of last laboratory results")
        
        
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
    #     ressources: ClassVar[list] = ["TNCDPANCREAS.pdf"]
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
