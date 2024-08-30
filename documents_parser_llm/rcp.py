import inspect
import json

from enum import Enum
from typing import List, Optional, ClassVar
from datetime import date
from langchain_core.pydantic_v1 import BaseModel, Field, PastDate


class RadiologicExamType(str, Enum):
    CT = 'CT'
    MRI = 'MRI'
    PET = 'PET'


class Gender(str, Enum):
    male = "male"
    female = "female"
    other = "other"
    not_given = "not_given"


class RevealingMode(str, Enum):
    '''
    This class lists the ways in which the tumor can be revealed 
    '''
    symptoms = 'symptoms'
    incidental_radiologic = 'incidental radiologic finding'
    incidental_biologic = 'incidental biologic finding'
    follow_up = 'follow up'
    unknown = 'unknown'


class MetastaticLocationsEnum(str, Enum):
    '''
    This class lists possible metastatic sites
    '''
    liver = 'liver'
    lung = 'lung'
    peritoneal = 'peritoneal'
    bone = 'bone'
    brain = 'brain'
    other = 'other'


class WHOPerformanceStatus(int, Enum):
    _0 = 0
    _1 = 1
    _2 = 2
    _3 = 3
    _4 = 4

    @classmethod
    def labels(cls) -> dict:
        return {
            cls._0: "No limitation of activities (none)",
            cls._1: "Limitation in strenuous activities, but able to do light work or other activities",
            cls._2: "Considerable limitation in activities; some assistance occasionally needed",
            cls._3: "Severe limitation in activities; frequent assistance required",
            cls._4: "Complete limitation of activities; unable to perform any activity"
        }


class PrimaryOrganEnum(str, Enum):

    pancreas = 'Pancreas'
    colon = "Colon "
    liver = "Liver"
    stomach = "Stomach"
    oesophagus = "Oesophagus"
    rectum = "Rectum"
    intra_hepatic_bile_duct = "Intra-hepatic bile duct"
    extra_hepatic_bile_duct = "Extra-hepatic bile duct"
    unknown = "unknown"


class TNCDCancerTypesEnum(str, Enum):

    ampulloma = 'tumor of the ampulla of Vater'
    localized_colon_cancer = 'localized colon cancer, without distant metastasis'
    metastatic_colorectal = 'metastatic colorectal cancer'
    rectum = 'rectal cancer'
    anal_canal = 'anal canal cancer'
    liverhcc = 'hepatocellular carcinoma (primary liver cancer)'
    biliary_tract = 'biliary tract cancer'
    pancreas = 'pancreatic cancer'

    gastric = 'gastric cancer'
    oesophagus_junction = 'oesophagus and esophagogastric junction cancer'
    unknown = 'unknown cancer type'


class CancerTypesEnum(str, Enum):

    colorectal_cancer = 'rectum and colon primitive cancer'
    liver_primary_cancer = 'hepatocellular carcinoma (primary liver cancer)'
    biliary_tract_cancer = 'biliary tract cancer'
    pancreatic_cancer = 'pancreatic cancer'
    gastric_cancer = 'gastric cancer'
    oesophagus_junction_cancer = 'oesophagus and esophagogastric junction cancer'
    unknown = 'unknown cancer type'


class TreatmentEnum(str, Enum):

    surgery = "Surgery"
    chemotherapy = "Chemotherapy"
    radiotherapy = "Radiotherapy"
    immunotherapy = "Immunotherapy"


class TreatmentStatusEnum(str, Enum):

    curative = "Curative"
    palliative = "Palliative"
    adjuvant = "Adjuvant"
    neo_adjuvant = "Neo-adjuvant"


class TreatmentToleranceEnum(str, Enum):
    good = "Good"
    medium = "Medium"
    poor = "Poor"


class ChemotherapyData(BaseModel):

    chemotherapy_name: str = Field(description="Name of the chemotherapy")
    chemotherapy_start_date: Optional[date] = Field(
        description="Date of the beginning of the chemotherapy")
    chemotherapy_end_date: Optional[date] = Field(
        description="Date of the end of the chemotherapy")
    chemotherapy_tolerance: TreatmentToleranceEnum = Field(
        description="Tolerance of the chemotherapy")

# class CurativeSurgery(BaseModel):

#     surgery_date: date = Field(description="Date of the surgery")
#     surgeon_name: Optional[str] = Field(description="Name of the surgeon")
#     surgery_name: Optional[str] = Field(description="Name of the surgery")


class PreviousTreatmentData(BaseModel):

    treatment_date: PastDate = Field(deacription="Date of the treatment")
    treatment_name: TreatmentEnum = Field(description="Name of the treatment")
    treatment_status: TreatmentStatusEnum = Field(
        description="Status of the treatment on the deasise")


# class CurativeSurgery(BaseModel):

#     surgery_date: date = Field(description="Date of the surgery")
#     surgeon_name: Optional[str] = Field(description="Name of the surgeon")
#     surgery_name: Optional[str] = Field(description="Name of the surgery")


class PancreaticTumorEnum(str, Enum):
    adenocarcinoma = 'adenocarcinoma'
    neuroendocrin = 'neuroendocrine tumor'
    unknown = 'unknow'


class PancreaticSymptomsEnum(str, Enum):
    pain = 'pain'
    jaundice = 'jaundice'
    mass = 'mass'
    weight_loss = 'weight loss'


class LiverSymptomsEnum(str, Enum):
    ascite = 'ascite'
    jaundice = 'jaundice'
    digestive_bleeding = 'digestive bleeding'
    encephalopathy = 'encephalopathy'


class ChildPugh(BaseModel):
    """
    Evaluation of the Child-Pugh score.

    Attributes:
        bilirubine: Bilirubin level in blood.
        albumine: Albumin level in blood.
        prothrombine: Prothrombin time.
        ascite: Presence of ascites.
        encephalopathie: Presence of encephalopathy.

    Examples:
        >>> child_pugh = ChildPugh(
                bilirubine=2,
                albumine=3,
                prothrombine=50,
                ascite=False,
                encephalopathie=False
            )
    """
    bilirubin: int = Field(description="Bilirubin level in blood")
    bilirubin: int = Field(description="Bilirubin level in blood")
    albumine: int = Field(description="Albumin level in blood")
    prothrombine: int = Field(description="Prothrombin time")
    ascite: bool = Field(description="Presence of ascites")
    encephalopathie: bool = Field(description="Presence of encephalopathy")

    question: ClassVar[str] = "Tell me the Child-Pugh score."


class RadiologicalExamination(BaseModel):
    '''
    This class contains all possible informations about one imagery exam
    '''
    exam_name: str = Field(description="The name of the radiological exam")
    exam_date: date = Field(
        description="The date when the radiological examination was performed.")
    exam_date: date = Field(
        description="The date when the radiological examination was performed.")
    exam_type: RadiologicExamType = Field(
        description="The type of radiological examination performed (e.g., CT, MRI, X-ray).")
    exam_result: Optional[str] = Field(
        description='Result of the radiological exam')


class HistologicAnalysis(BaseModel):
    '''
    This class contains all informations related to a histological analysis.

    Attributes:
        date (datetime): Date when the biopsy or resection was performed.
        contributive (bool): Indicator of the importance of the results (conclusive or not).
        result (str): Complete result of the histological analysis.

    Examples:
        >>> analysis = HistologicAnalysis(
                date=datetime.date(2022, 1, 1),
                contributive=True,
                result="Result of a detailed histological analysis"
            )
    '''
    histology_date: date = Field(description="Date of biopsy or resection")
    contributive: bool = Field(
        description="Importance of results (conclusive or not)")
    result: str = Field(
        description='Complete result of the histological analysis')


class RadiologicalExaminations(BaseModel):
    """
    A container for a patient's radiology studies.

    Attributes:
        exams_all (list[RadiologicalExamination]): All of the patient's radiology studies.
        ct_scans (list[RadiologicalExamination]): The patient's computed tomography (CT) scans.
        mri_studies (list[RadiologicalExamination]): The patient's magnetic resonance imaging (MRI) studies.
        pet_scans (list[RadiologicalExamination]): The patient's positron emission tomography (PET) scans.

    Examples:
        >>> exams = RadiologicalExaminations(
                exams_all=[RadiologicalExamination(...)],
                ct_scans=[RadiologicalExamination(...)],
                mri_studies=[RadiologicalExamination(...)],
                pet_scans=[RadiologicalExamination(...)]
            )
    """
    exams_all: list[RadiologicalExamination] = Field(
        "All of the patient's radiology studies")
    ct_scans: list[RadiologicalExamination] = Field(
        "The patient's computed tomography (CT) scans")
    mri_studies: list[RadiologicalExamination] = Field(
        "The patient's magnetic resonance imaging (MRI) studies")
    pet_scans: list[RadiologicalExamination] = Field(
        "The patient's positron emission tomography (PET) scans")


class PatientMDTOncologicForm():
    '''
    This class contains all patient and oncological disease information for the report.
    '''

    base_prompt = [
        ("system",
         "You are a medical assistant, you have to answer questions based on this patient record: {context}.")
    ]

    def __init__(self) -> None:
        self.datas = {}
        self.basemodel_list = [cls_attribute for cls_attribute in self.__class__.__dict__.values()
                               if inspect.isclass(cls_attribute)
                               and issubclass(cls_attribute, self.default_model) and cls_attribute.__name__ != "default_model"]

    
    def set_datas(self, basemodel, datas) -> None:
        self.datas[basemodel.__name__] = datas

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
        '''
        Patient administrative informations
        '''
        first_name: str = Field(description="First name of the patient")
        last_name: str = Field(description="Last name of the patient")
        age: int = Field(description="Age of the patient")
        date_birth: Optional[int] = Field(
            description="Date of birth of the patient")
        gender: Gender = Field(description="Gender of the patient")

        question: ClassVar[str] = "Tell me the first name, Last name, age, date of birth and gender of the patient."

    class PatientPerformanceStatus(default_model):
        '''
        Patient WHO performance status
        '''

        performance_status: WHOPerformanceStatus = Field(
            description="OMS performance status of the patient, from 0 to 4")

        question: ClassVar[
            str] = "Tell me the WHO performance status of the patient (0-4)."
        performance_status: WHOPerformanceStatus = Field(
            description="OMS performance status of the patient, from 0 to 4")

        question: ClassVar[
            str] = "Tell me the WHO performance status of the patient (0-4)."

    class TumorLocation(default_model):
        '''
        Location of the tumor
        '''

        tumor_location: PrimaryOrganEnum = Field(
            description="Organ where the primary tumor is present")

        question: ClassVar[str] = "Tell me where is located the primary tumor ?"

    class TumorBiology(default_model):
        '''
        Biology of the tumor
        '''

        msi_state: Optional[bool] = Field(
            description="Is the tumor MSI or MSS")

        question: ClassVar[str] = "Tell me if the tumor is stated MSI or MSS ?"

    class RadiologicExams(default_model):
        '''
        List of radiological exams
        '''

        exams_list: Optional[list[RadiologicalExamination]] = Field(
            description="List of radiological exams")

        question: ClassVar[str] = "Give me a list of the radiological exams with date, name and type "

    class PreviousCurativeSurgery(default_model):
        '''
        Previous curative surgery
        '''

        previous_curative_surgery: bool = Field(
            description="If a curative surgery has already been done")
        previous_curative_surgery_date: Optional[PastDate] = Field(
            description="Date of the surgery")

        question: ClassVar[str] = "Tell me if a curative surgery has already been done for this tumor ?"

    class PlannedCurativeSurgery(default_model):
        '''
        Planned curative surgery
        '''

        planned_curative_surgery: bool = Field(
            description="If a curative surgery has been planned")

        question: ClassVar[str] = "Tell me if a curative surgery has been planned for this tumor ?"

    class ChemotherapyTreament(default_model):
        '''
        Chemotherapy treatments
        '''

        chemotherapy: bool = Field(
            description="If a chemotherapy has already been done")
        chemotherapy_list: Optional[List[ChemotherapyData]] = Field(
            description="List of chemotherapies that have been done")

        question: ClassVar[str] = "Tell me if one or several chemotherapies have already been done for this tumor?"

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
