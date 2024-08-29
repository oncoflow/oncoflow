from enum import Enum, IntEnum
from typing import List, Optional, ClassVar
from datetime import date, datetime
from langchain_core.pydantic_v1 import BaseModel, Field, validator
import inspect

class ImageryType(str, Enum):
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
    unknown  = 'unknown'

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


    class CancerTypesEnum(str, Enum):
        """
        Types of digestive tract and associated organ cancers.

        This enumeration contains the following types of cancer:

        * oesophagus_junction : Esophageal and esophagogastric junction cancer
        * gastric : Gastric cancer
        * localized_colon_cancer : Localized colon cancer, where cancer cells have not spread to distant parts of the body
        * metastatic_colorectal : Metastatic colorectal cancer
        * rectum : Rectal cancer
        * anal_canal : Anal canal cancer
        * liverhcc : Hepatocellular carcinoma (primary liver cancer)
        * biliary_tract : Biliary tract cancer
        * pancreas : Pancreatic cancer
        * ampulloma : Tumor of the ampulla of Vater

        Use this enumeration to specify the type of cancer in corresponding fields.
        """

        oesophagus_junction = 'oesophagus and esophagogastric junction cancer'
        gastric = 'gastric cancer'
        localized_colon_cancer = 'localized colon cancer, without distant metastasis'
        metastatic_colorectal ='metastatic colorectal cancer'
        rectum = 'rectal cancer'
        anal_canal = 'anal canal cancer'
        liverhcc = 'hepatocellular carcinoma (primary liver cancer)'
        biliary_tract ='biliary tract cancer'
        pancreas = 'pancreatic cancer'
        ampulloma = 'tumor of the ampulla of Vater'


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
    bilirubine: int = Field(description="Bilirubin level in blood")
    albumine: int = Field(description="Albumin level in blood")
    prothrombine: int = Field(description="Prothrombin time")
    ascite: bool = Field(description="Presence of ascites")
    encephalopathie: bool = Field(description="Presence of encephalopathy")

    question: ClassVar[str] = "Tell me the Child-Pugh score."

class RadiologicalExamination(BaseModel):
    '''
    This class contains all possible informations about one imagery exam
    '''
    date: datetime = Field(description="The date when the radiological examination was performed.") 
    type:  ImageryType= Field(description="The type of radiological examination performed.")  #to do : valider que cela soit soit IRM/TDM/TEP
    centre: Optional[str]= Field(description="The place where the radiological examination was performed.")
    centre_expert: Optional[bool]= Field(description="Whether the radiological examination was performed is a tertiary center.")
    radiologue: Optional[str]= Field(description="The contains the name of the radiologist who performed the examination.")
    interpretationfull: Optional[str]= Field(description="Contient le compte rendu complet de l'examen d'imagerie")
    interpretationcut: Optional[str]= Field(description="Contient un résumé de l'examen d'imagerie")
    relecture: Optional[bool]= Field(description="Indique si une relecture de l'examen d'imagerie en centre expert a ete realisee")
    relecteur: Optional[str]= Field(description="Contient le nom du radiologue en centre expert ayant realise la relecture de l'examen d'imagerie")
    reinterpretation: Optional[str]= Field(description="Contient le cCompte rendu de la relecture de l'examen d'imagerie en centre expert")

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
    date: datetime = Field(description="Date of biopsy or resection")
    contributive: bool = Field(description="Importance of results (conclusive or not)")
    result: str = Field(description='Complete result of the histological analysis')

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
    exams_all: list[RadiologicalExamination] = Field("All of the patient's radiology studies")
    ct_scans: list[RadiologicalExamination] = Field("The patient's computed tomography (CT) scans")
    mri_studies: list[RadiologicalExamination] = Field("The patient's magnetic resonance imaging (MRI) studies")
    pet_scans: list[RadiologicalExamination] = Field("The patient's positron emission tomography (PET) scans")
class RcpFiche():   # pourquoi RCPFiche n'est pas un basemodel ?
    '''
    This class contains all patient and oncological disease information.
    '''

    base_prompt = [
        ("system",
         "You are a medical assistant, you have to answer questions based on this patient record: {context}."),
    ]

    def __init__(self) -> None:
        self.basemodel_list = [cls_attribute for cls_attribute in self.__class__.__dict__.values()
                               if inspect.isclass(cls_attribute)
                               and issubclass(cls_attribute, self.default_model) and cls_attribute.__name__ != "default_model"]
        
    def json(self):
        return self.dict()

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
            ("human", "{question}"),
        ]
        prompt: ClassVar[list] = []
        models: ClassVar[list] = []
        question: ClassVar[str] = ""
        ressources: ClassVar[list] = []

    class Patient(default_model):
        '''
        Patient base informations
        '''
        name: str = Field(description="Full name of the patient")
        age: int = Field(description="Age of the patient")
        gender: Gender = Field(description="Gender of the patient")
        performance_status: WHOPerformanceStatus = Field(description="OMS performance status of the patient, from 0 to 4")
        question: ClassVar[str] = "Tell me the full name, age, gender and OMS performance status of the patient (0-4)."

    class TumorType(default_model):
        '''
        Type of cancer
        '''

        cancer_type: CancerTypesEnum = Field(description="Cancer type among cancer type enum list")
        question: ClassVar[str] = "Tell me what is the tumor cancer type."

    class MetastaticState(default_model):
        """
        Tumor metastatic state.

        Attributes:
            metastatic_disease (bool): Tumor metastatic state (True if present, False otherwise).
            metastatic_location (Optional[list[MetastaticLocationsEnum]]): Organs affected by metastasis.

        Examples:
            >>> metastatic_state = MetastaticState(
                    metastatic_disease=True,
                    metastatic_location=[MetastaticLocationsEnum.BONE, MetastaticLocationsEnum.LIVER]
                )
        """
        metastatic_disease: bool = Field(description="Tumor metastatic state (True if present, False otherwise)")
        metastatic_location: Optional[list[MetastaticLocationsEnum]] = Field(description="Organs affected by metastasis")

        question: ClassVar[str] = "Tell me if the tumor is metastatic or not, and which organs are involved."
        
    

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
    #     question: ClassVar[str] = "En te basant sur les traitements possibles à proposer à ce patient, est-ce qu'une évaluation par un cardiologue est nécessaire ? "

    # class ChirurgienPancreatique(default_model):
    #     necessary: bool = Field(description="Est-ce que l'évaluation par un chirurgien pancréatique est nécessaire ?")
    #     reason: str = Field(description="Pourquoi ?")
    #     base_prompt: ClassVar[list] = [
    #         ("human", "Je vais te demander si une évaluation du dossier par un chirurgien pancréatique est nécessaire, quels éléments te permettraient de répondre correctement à la question ?"),
    #         ("ai", "Je dois vérifier que le patient ne présente pas de métastases ou d'envahissement artériel qui contre-indiquerai la chirurgie selon les recommandations du TNCD"),
    #         ("human", "Exactement, et si tu n'es pas certains de la réponse ?"),
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