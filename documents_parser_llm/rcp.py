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
class TypeImagerie(str, Enum):
    scanner = 'scanner'
    MRI = 'MRI'
    TEP = 'TEP'

class Gender(str, Enum):
    male = 'male'
    female = 'female'
    other = 'other'
    not_given = 'not_given'

class PerformanceStatus(IntEnum):
    '''
    Cette classe liste les différentes valeurs que doit prendre le stade OMS ou Performance Status
    '''
    ecog0 = '0'
    ecog1 = '1'
    ecog2 = '2'
    ecog3 = '3'
    ecog4 = '4'

class ExamenImagerie(BaseModel):
    '''
    Cette classe contient les informations concernant un seul examen d'imagerie
    '''
    date: datetime = Field(description="Contient la date de realisation de l'examen d'imagerie") 
    type:  TypeImagerie= Field(description="Contient le type d'examen d'imagerie")  #to do : valider que cela soit soit IRM/TDM/TEP
    centre: Optional[str]= Field(description="Contient le nom de la structure médicale ou a été réalisé l'examen d'imagerie")
    centre_expert: bool= Field(description="Décrit si l'imagerie a ete realisee en centre expert")
    radiologue: Optional[str]= Field(description="Contient le nom du radiologue ayant interprete l'examen d'imagerie")
    interpretationfull: Optional[str]= Field(description="Contient le compte rendu complet de l'examen d'imagerie")
    interpretationcut: Optional[str]= Field(description="Contient un résumé de l'examen d'imagerie")
    relecture: Optional[bool]= Field(description="Indique si une relecture de l'examen d'imagerie en centre expert a ete realisee")
    relecteur: Optional[str]= Field(description="Contient le nom du radiologue en centre expert ayant realise la relecture de l'examen d'imagerie")
    reinterpretation: Optional[str]= Field(description="Contient le cCompte rendu de la relecture de l'examen d'imagerie en centre expert")

class ExamenAnapath(BaseModel):
    '''
    Cette classe contient les informations concernant un seul examen d'histologie
    '''
    date: datetime = Field(description="Contient la date de realisation de l'examen d'imagerie")
    contributif: bool = Field(description="Determine si le resultat de l'examen est contributif")

class ExamensImagerie(BaseModel):
    '''
    Cette classe contient les informations d'une liste d'examens d'imagerie
    '''
    examensall: list[ExamenImagerie]= Field(description="Contient la liste de tous les examens d'imagerie du patient")
    scanAll: list[ExamenImagerie]= Field(description="Contient la liste de tous les examens d'imagerie par scanner du patient")
    MRIAll: list[ExamenImagerie]= Field(description="Contient la liste de tous les examens d'imagerie par IRM du patient")
    TEPAll: list[ExamenImagerie]= Field(description="Contient la liste de tous les examens d'imagerie par TEP du patient")
class RcpFiche():   # pourquoi RCPFiche n'est pas un basemodel ?
    '''
    Cette classe contient les informations d'une fiche de reunion de concertation pluridisciplinaire
    '''

    base_prompt = [
        ("system",
         "Tu es un assistant specialiste dans le domaine de la cancérologie digestive. Tu dois répondre aux questions avec les informations présentes dans le dossier de ce patient : {context}."),
    ]

    def __init__(self) -> None:
        self.basemodel_list = [cls_attribute for cls_attribute in self.__class__.__dict__.values()
                               if inspect.isclass(cls_attribute)
                               and issubclass(cls_attribute, self.default_model) and cls_attribute.__name__ != "default_model"]


    class default_model(BaseModel):
        base_prompt: ClassVar[list] = [
            # ("human", "Que vas-tu répondre si tu n'as pas tous les éléments?"),
            # ("ai", "inconnu"),
            # ("human", "Es tu prêt à répondre de manière brève et en francais à une question?"),
            # ("ai", "Oui, quelle est la question concernant ce patient ?"),
            ("human", "{question}"),
        ]
        prompt: ClassVar[list] = []
        models: ClassVar[list] = []
        question: ClassVar[str] = ""
        ressources: ClassVar[list] = []

    class Patient(default_model):
        '''
        Cette classe permet de stocker les informations médicales générales du dossier oncologique
        '''
        name: str = Field(description="Nom complet du patient")
        age: int = Field(description="Age du patient")
        gender: Gender = Field(description="Genre du patient")
        tumor_type: int = Field(description="Type de tumeur primitive présente ou suspectée chez le patient")
        performance_status: PerformanceStatus = Field(description="Stade OMS du patient")
        cardiac_deasise: bool = Field(description="Presence d'un antecedant de maladie cardio-vasculaire")
        dossier_radiologique: ExamensImagerie = Field(description="Ensemble des examens radiologiques du patient")
        base_prompt: ClassVar[list] = [
        
   
        ]
        question: ClassVar[str] = "Quelles sont les caractéristiques suivantes du patient : nom, âge, genre, type de tumeur, présence d'un antécédant cardiovasculaire et dossier radiologique"

    class Maladie(default_model):
        '''
        Cette classe permet de stocker les informations spécifiques à la tumeur
        '''
        date_diagnostic: date = Field(description="Date du diagnostic de la tumeur")
        tumor_type: str = Field(description="Type de tumeur primitive présente ou suspectée")
        tumor_stade: str = Field(description="Stade de la tumeur")
        base_prompt: ClassVar[list] = [
   
        ]
        question: ClassVar[str] = "Quelles sont les caractéristiques de la tumeur"

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