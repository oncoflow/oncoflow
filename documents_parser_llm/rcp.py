from typing import List, Optional, ClassVar
from datetime import date
from langchain_core.pydantic_v1 import BaseModel, Field, validator
import inspect


    # "Est-ce qu'une biopsie avec un résultat anatomopathologique a déja été obtenu ?",
    # "Est-ce qu'il est fait mention d'un traitement par anticoagulants ?",
    # "Quel sont les examens d'imagerie réalisés chez ce patient, je souhaite un format en sortie avec date de réalisation, type d'examen, résultat principal ?",
    # "Quel est le stade OMS du patient ?",
    # "Est-ce qu'un traitement par chimiothérapie à déja été réalisé ?"]

class ExamenImagerie(BaseModel):
    '''
    Cette classe permet de stocker les informations d'un examen d'imagerie present dans le dossier medical
    '''
    date_imagerie: date = Field(description="Date de realisation de l'examen d'imagerie") 
    type_imagerie:  str= Field(description="Type d'examen d'imagerie")  #to do : valider que cela soit soit IRM/TDM/TEP
    centre_imagerie: str= Field(description="Lieu de realisation de l'examen d'imagerie")
    radiologue: str= Field(description="Radiologue ayant interprete l'examen d'imagerie")
    interpretation: str= Field(description="Compte rendu de l'examen d'imagerie")
    relecture: bool= Field(description="Relecture de l'examen d'imagerie")
    relectureur: str= Field(description="Radiologue ayant realise la relecture de l'examen d'imagerie")
    reinterpretation: str= Field(description="Compte rendu de la relecture de l'examen d'imagerie")

class ExamensImagerie(BaseModel):
    '''
    Cette classe permet de stocker une liste d'examens d'imagerie presents dans le dossier medical
    '''
    examens: list[ExamenImagerie]= Field(description="Liste des examens d'imagerie")
class RcpFiche():   # pourquoi RCPFiche n'est pas un basemodel ?
    '''
    Cette classe permet de stocker toutes les informations d'une fiche de reunion de concertation pluridisciplinaire
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
            ("human", "Que vas-tu répondre si tu n'as pas tous les éléments?"),
            ("ai", "inconnu"),
            ("human", "Es tu prêt à répondre de manière brève et en francais à une question?"),
            ("ai", "Oui, quelle est la question concernant ce patient ?"),
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
        tumor_type: int = Field(description="Type de tumeur primitive présente ou suspectée chez le patient")
        performance_status: int = Field(description="Stade OMS du patient")
        cardiac_deasise: bool = Field(description="Presence d'un antecedant de maladie cardio-vasculaire")
        dossier_radiologique: ExamensImagerie = Field(description="Ensemble des examens radiologiques du patient")
        base_prompt: ClassVar[list] = [
        
   
        ]
        question: ClassVar[str] = "Quelles sont les caractéristiques medicales presentes dans ce dossier ? "

    class Maladie(default_model):
        '''
        Cette classe permet de stocker les informations spécifiques à la tumeur
        '''
        date_diagnostic: date = Field(description="Date du diagnostic de la tumeur")
        tumor_type: str = Field(description="Type de tumeur primitive présente ou suspectée")
        tumor_stade: str = Field(description="Stade de la tumeur")
        base_prompt: ClassVar[list] = [
   
        ]
        question: ClassVar[str] = "Quel est le type de tumeur et de quand date le diagnostic de la tumeur dans ce dossier ? "

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