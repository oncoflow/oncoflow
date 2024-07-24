from enum import Enum, IntEnum
from typing import List, Optional, ClassVar
from datetime import date, datetime
from langchain_core.pydantic_v1 import BaseModel, Field, validator
import inspect


    # "Est-ce qu'une biopsie avec un résultat anatomopathologique a déja été obtenu ?",
    # "Est-ce qu'il est fait mention d'un traitement par anticoagulants ?",
    # "Quel sont les examens d'imagerie réalisés chez ce patient, je souhaite un format en sortie avec date de réalisation, type d'examen, résultat principal ?",
    # "Quel est le stade OMS du patient ?",
    # "Est-ce qu'un traitement par chimiothérapie à déja été réalisé ?"]
class ImageryType(str, Enum):
    CT = 'CT'
    MRI = 'MRI'
    PET = 'PET'

class Gender(str, Enum):
    male = 'male'
    female = 'female'
    other = 'other'
    not_given = 'not_given'

class MetastaticLocalisationsEnum(str, Enum):
    liver = 'liver'
    lung = 'lung'
    peritoneal = 'peritoneal'
    bone = 'bone'
    other = 'other'

class PerformanceStatus(IntEnum):
    '''
    This class contains all allowed ECOG or Performance Status values
    '''
    ecog0 = '0'
    ecog1 = '1'
    ecog2 = '2'
    ecog3 = '3'
    ecog4 = '4'

class TumorTypes(str, Enum):
    liverHCC = 'liver hepatocarcinoma'
    liverBiliary = 'intra hepatic cholangiocarcinoma'
    extrabiliary = 'extra hepatic biliary tract cholangiocarcinoma'
    pancreaticCarcinoma = 'pancreas adenocarcinoma'
    colon = 'colon cancer'
    rectum = 'rectal cancer'
    oesophagus = 'oesophagus'

class RadiologicalExamination(BaseModel):
    '''
    This class contains all informations about one imagery exam
    '''
    date: datetime = Field(description="The date when the radiological examination was performed.") 
    type:  ImageryType= Field(description="The type of radiological examination performed.")  #to do : valider que cela soit soit IRM/TDM/TEP
    centre: Optional[str]= Field(description="The place where the radiological examination was performed.")
    centre_expert: Optional[bool]= Field(description="Whether the where the radiological examination was performed is a tertiary center.")
    radiologue: Optional[str]= Field(description="The contains the name of the radiologist who performed the examination.")
    interpretationfull: Optional[str]= Field(description="Contient le compte rendu complet de l'examen d'imagerie")
    interpretationcut: Optional[str]= Field(description="Contient un résumé de l'examen d'imagerie")
    relecture: Optional[bool]= Field(description="Indique si une relecture de l'examen d'imagerie en centre expert a ete realisee")
    relecteur: Optional[str]= Field(description="Contient le nom du radiologue en centre expert ayant realise la relecture de l'examen d'imagerie")
    reinterpretation: Optional[str]= Field(description="Contient le cCompte rendu de la relecture de l'examen d'imagerie en centre expert")

    

class ExamenAnapath(BaseModel):
    '''
    This class contains all informations about one pathology exam
    '''
    date: datetime = Field(description="Contains the date when the biopsy or resection was performed")
    contributif: bool = Field(description="Indicates whether the results are conclusive or not")

class RadiologicalExaminations(BaseModel):
    '''
    This class list all the patient's radiology studies
    '''
    Examsall: list[RadiologicalExamination]= Field(description="List all the patient's radiology studies")
    CTAll: list[RadiologicalExamination]= Field(description="List all the patient's radiology CT scan studies")
    MRIAll: list[RadiologicalExamination]= Field(description="List all the patient's radiology MRI studies")
    PETAll: list[RadiologicalExamination]= Field(description="List all the patient's radiology PET studies")
class RcpFiche():   # pourquoi RCPFiche n'est pas un basemodel ?
    '''
    This class contains all patient and oncological disease information.
    '''

    base_prompt = [
        ("system",
         "You are a medical assistant, you must base your answers on this patient record: {context}."),
    ]
    
    def __init__(self) -> None:  
        self.basemodel_list = [cls_attribute for cls_attribute in self.__class__.__dict__.values()
                    if inspect.isclass(cls_attribute)
                    and issubclass(cls_attribute, self.default_model) and cls_attribute.__name__ != "default_model"]


    class default_model(BaseModel):
        base_prompt: ClassVar[list] = [
            ("human", "{question}"),
        ]
        prompt: ClassVar[list] = []
        models: ClassVar[list] = ['llama3-chatqa']
        question: ClassVar[str] = ""
        ressources: ClassVar[list] = []
    
    class Patient(default_model):
        '''
        This class is about patient's characteristics
        '''
        name: str = Field(description="Full name of the patient")
        age: int = Field(description="Patient's age")
        gender: Gender = Field(description="Patient gender")
        # tumor_type: str = Field(description="Type of tumor present in this patient")
        performance_status: PerformanceStatus = Field(description="ECOG ou performance status")
        cardiaovascular_disease: bool = Field(description="Cardiovascular history")
        # dossier_radiologique: RadiologicalExaminations = Field(description="Radiologic exams")
        question: ClassVar[str] = "Describe this patient's characteristics : name, age, gender, performance status, cardiovascular disease history."

    class TumorBaseCharacteristics(default_model):
        '''
        This class is about tumor caracteristics
        '''
        date_diagnosis: date = Field(description="Date of tumor diagnosis")
        tumor_type: str = Field(description="Type of tumor present or suspected")
        metastatic_deasise: bool = Field(description="Indicates whether the patient's tumor is metastatic, i.e. with secondary localizations in other organs, or non-metastatic.")
        metastatic_localisation: Optional[list[MetastaticLocalisationsEnum]] = Field(description="Indicates in which organs are located metastasis")
        # tumor_stade: str = Field(description="Tumor grade")
        question: ClassVar[str] = "Describe the tumor basics characteristics : type, date of diagnosis and metastatic state"

    # class TumeurPancreas(BaseModel):
    #     '''
    #     Cette classe permet de stocker les informations spécifiques à une tumeur pancréatique
    #     '''
    #     symptomes_initiaux: List[Symptomes initiaux] = Field(description="Liste de symptômes ayant conduit aux premiers examens")
    
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