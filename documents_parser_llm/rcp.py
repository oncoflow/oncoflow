from typing import Optional, ClassVar
from langchain_core.pydantic_v1 import BaseModel, Field, validator
import inspect

# "Est-ce qu'une biopsie avec un résultat anatomopathologique a déja été obtenu ?",
# "Est-ce qu'il est fait mention d'un traitement par anticoagulants ?",
# "Quel sont les examens d'imagerie réalisés chez ce patient, je souhaite un format en sortie avec date de réalisation, type d'examen, résultat principal ?",
# "Quel est le stade OMS du patient ?",
# "Est-ce qu'un traitement par chimiothérapie à déja été réalisé ?"]


class RcpFiche():

    base_prompt = [
        ("system",
         "Tu es un assistant spécialiste dans le domaine de la cancérologie digestive. Tu dois répondre aux questions avec les informations qui sont présentes dans le dossier de ce patient : {context}."),
    ]

    def __init__(self) -> None:
        self.datas = {}
        self.basemodel_list = [cls_attribute for cls_attribute in self.__class__.__dict__.values()
                               if inspect.isclass(cls_attribute)
                               and issubclass(cls_attribute, self.default_model) and cls_attribute.__name__ != "default_model"]
        for basemodel in self.basemodel_list:
            self.datas[basemodel.__name__] = basemodel
            
    def set_datas(self, basemodel, datas) -> None:
        self.datas[basemodel.__name__] = datas

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
        name: str = Field(description="Nom complet du patient")
        age: int = Field(description="Age du patient")
        tumor_type: int = Field(
            description="Type de tumeur primitive présente ou suspectée chez le patient")
        performance_status: int = Field(description="Stade OMS du patient")
        cardiac_deasise: int = Field(
            description="Antécédant de maladie cardiaque présent chez ce patient")

        question: ClassVar[str] = "A partir des informations du dossier du patient, renseigne le maximum d'éléments"

    class Maladie(default_model):

        tumor_type: int = Field(
            description="Type de tumeur primitive présente ou suspectée chez le patient")

        question: ClassVar[str] = "A partir des informations du document qui concerne le patient, renseigne le maximum d'éléments"

    class Cardiologue(default_model):
        necessary: bool = Field(
            description="Est-ce que l'évaluation par un cardiologue est nécessaire pour traiter ce patient ?")
        reason: str = Field(description="Pourquoi ?")
        base_prompt: ClassVar[list] = [
            ("human", "Que vas-tu répondre si tu n'as pas tous les éléments?"),
            ("ai", "inconnu"),
            ("human", "Es tu prêt à répondre de manière brève et en francais à une question?"),
            ("ai", "Oui, quelle est la question concernant ce patient ?"),
            ("human", "{question}"),
        ]
        #models: ClassVar[list] = ["phi3"]
        ressources: ClassVar[list] = ["TNCDPANCREAS.pdf"]
        question: ClassVar[str] = "En te basant sur les traitements possibles à proposer à ce patient, est-ce qu'une évaluation par un cardiologue est nécessaire ? "

    class ChirurgienPancreatique(default_model):
        necessary: bool = Field(
            description="Est-ce que l'évaluation par un chirurgien pancréatique est nécessaire ?")
        reason: str = Field(description="Pourquoi ?")
        base_prompt: ClassVar[list] = [
            ("human", "Je vais te demander si une évaluation du dossier par un chirurgien pancréatique est nécessaire, quels éléments te permettraient de répondre correctement à la question ?"),
            ("ai", "Je dois vérifier que le patient ne présente pas de métastases ou d'envahissement artériel qui contre-indiquerai la chirurgie selon les recommandations du TNCD"),
            ("human", "Exactement, et si tu n'es pas certains de la réponse ?"),
            ("ai", "Alors je réponds qu'une évaluation par un chirurgien est souhaitable et je justifie avec les éléments du TNCD et du dossier du patient"),
            ("human", "{question}"),
        ]
        #models: ClassVar[list] = ["llama3"]
        ressources: ClassVar[list] = ["TNCDPANCREAS.pdf"]
        question: ClassVar[str] = "Alors réponds moi, est-qu'une une évaluation du dossier par un chirurgien pancréatique est nécessaire  ?"

    class ChirurgienHepatique(default_model):
        necessary: bool = Field(
            description="Est-ce que l'évaluation par un chirurgien hépatique est nécessaire ?")
        reason: str = Field(description="Pourquoi ?")
        base_prompt: ClassVar[list] = [
            ("human", "Que vas-tu répondre si tu n'as pas tous les éléments?"),
            ("ai", "inconnu"),
            ("human", "Es tu prêt à répondre de manière brève et en francais à une question?"),
            ("ai", "Oui, quelle est la question concernant ce patient ?"),
            ("human", "{question}"),
        ]
        #models: ClassVar[list] = ["phi3"]
        ressources: ClassVar[list] = ["TNCDPANCREAS.pdf"]
        question: ClassVar[str] = "En te basant sur les traitements possibles à proposer à ce patient, est-ce qu'une évaluation par un chirurgien hépatique est nécessaire ?"

    class ChirurgienColorectal(default_model):
        necessary: bool = Field(
            description="Est-ce que l'évaluation par un chirurgien colorectal est nécessaire ?")
        reason: str = Field(description="Pourquoi ?")
        base_prompt: ClassVar[list] = [
            ("human", "Que vas-tu répondre si tu n'as pas tous les éléments?"),
            ("ai", "inconnu"),
            ("human", "Es tu prêt à répondre de manière brève et en francais à une question?"),
            ("ai", "Oui, quelle est la question concernant ce patient ?"),
            ("human", "{question}"),
        ]
        #models: ClassVar[list] = ["phi3"]
        ressources: ClassVar[list] = ["TNCDPANCREAS.pdf"]
        question: ClassVar[str] = "En te basant sur les traitements possibles à proposer à ce patient, est-ce qu'une évaluation par un chirurgien colorectal est nécessaire ?"

    class EssaiClinique(default_model):
        necessary: bool = Field(
            description="Est-ce qu'un essai clinique peut être proposé au patient ?")
        reason: str = Field(description="Pourquoi ?")
        trial_name: str = Field(
            description="Nom de l'essai clinique à proposer au patient")
        base_prompt: ClassVar[list] = [
            ("human", "Que vas-tu répondre si tu n'as pas tous les éléments?"),
            ("ai", "inconnu"),
            ("human", "Es tu prêt à répondre de manière brève et en francais à une question?"),
            ("ai", "Oui, quelle est la question concernant ce patient ?"),
            ("human", "{question}"),
        ]
        #models: ClassVar[list] = ["phi3"]
        ressources: ClassVar[list] = ["TNCDPANCREAS.pdf"]
        question: ClassVar[str] = "En te basant sur les traitements possibles à proposer à ce patient, est-ce qu'une évaluation par un chirurgien colorectal est nécessaire ?"
