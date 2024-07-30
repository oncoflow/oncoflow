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
    male = 'male'
    female = 'female'
    other = 'other'
    not_given = 'not_given'

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

class PerformanceStatus(IntEnum):
    '''
    This class enumerates WHO (World Health Organisation, i.e. OMS in French) performance index or ECOG performance status values.
    '''
    ecog0 = '0'
    ecog1 = '1'
    ecog2 = '2'
    ecog3 = '3'
    ecog4 = '4'

class CancerTypesEnum(str, Enum):
    oesophagus_junction = 'cancer of the oesophagus and oesogastric junction'
    gastric = 'gastric cancer'
    colon_metafree = 'non-metastatic colon cancer'
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
    This class contains all informations about one histologic analysis
    '''
    date: datetime = Field(description="Contains the date when the biopsy or resection was performed")
    contributive: bool = Field(description="Indicates whether the results are conclusive or not")
    result: str = Field(description='Contains the full histological result')

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
         "You're a medical assistant skilled at investigating complex digestive oncology cases. Your objective is to extract medical informations."),
    ]

    def __init__(self) -> None:
        self.basemodel_list = [cls_attribute for cls_attribute in self.__class__.__dict__.values()
                               if inspect.isclass(cls_attribute)
                               and issubclass(cls_attribute, self.default_model) and cls_attribute.__name__ != "default_model"]


    class default_model(BaseModel):
        base_prompt: ClassVar[list] = [
            ("ai", "How can i help you ?"),
            ("human" ,  "You must base your answers only on this patient record: {context}."),
            ("ai" , "What is the question a have to answer and how should I format the answer ?"),
            ("human", "{question}"),
        ]
        prompt: ClassVar[list] = []
        models: ClassVar[list] = []
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
        performance_status: PerformanceStatus = Field(description="Patient's WHO performance index or ECOG performance status")
        cardiovascular_disease: bool = Field(description="Cardiovascular history")
        clinical_trial_involvment: bool = Field(description="Whether the patient is included in a clinical trial")
        clinical_trial_name: str = Field(description="Name of the clinical trial")
        # dossier_radiologique: RadiologicalExaminations = Field(description="Radiologic exams")
        question: ClassVar[str] = "Extract these patient's characteristics : name, age, gender, performance status i.e. OMS status , cardiovascular disease history."

    class TumorBaseCharacteristics(default_model):
        '''
        This class is about tumor caracteristics
        '''
        revelation_mode : RevealingMode = Field(description="How the tumor is revealed")
        date_diagnosis: date = Field(description="Date of tumor diagnosis")
        cancer_type: CancerTypesEnum = Field(description="The type of cancer")
        cancer_type_justification: str = Field(description="Justification of the type of cancer found")
        histologic_results: Optional[List[HistologicAnalysis]] = Field(description='Contains all histological results')
        metastatic_disease: bool = Field(description="Indicates whether the patient's tumor is metastatic, i.e. with secondary localizations in other organs, or non-metastatic.")
        metastatic_location: Optional[list[MetastaticLocationsEnum]] = Field(description="Indicates in which organs are located metastasis")
        # tumor_stade: str = Field(description="Tumor grade")
        question: ClassVar[str] = "Extract and justify the tumor characteristics : revelation's mode, date of diagnosis, cancer type, histologic results and metastatic state"

    class PancreaticTumor(BaseModel):
        '''
        This class contains pancreatic tumor specific items
        '''
        
        onset_symptoms: Optional[List[PancreaticSymptomsEnum]] = Field(description="Contains initials symptoms")
        actual_symptoms: Optional[List[PancreaticSymptomsEnum]] = Field(description="Contains actual symptoms")

    class LiverTumor(BaseModel):
        '''
        This class contains pancreatic tumor specific items
        '''
        
        onset_symptoms: Optional[List[LiverSymptomsEnum]] = Field(description="Contains initials symptoms")
        actual_symptoms: Optional[List[LiverSymptomsEnum]] = Field(description="Contains actual symptoms")
    
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