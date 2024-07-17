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
         "Tu es un spécialiste de la cancérologie digestive. Tu dois répondre aux questions concernant le dossier de ce patient : {context}."),
        ("human", "As-tu compris?"),
        ("ai", "Oui, grâce aux éléments je vais pouvoir répondre, si il me manque un élément de réponse je répondrai par : inconnu"),
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
        name: str = Field(description="full name of Patient")
        age: int = Field(description="Age of Patient")

        question: ClassVar[str] = "Donne moi les informations patient de la fiche RCP"

    class Cardiologue(default_model):
        necessary: bool = Field(description="caridiologue est necessaire")
        reason: str = Field(description="Pourquoi")
        base_prompt: ClassVar[list] = [
            ("human", "Que vas-tu répondre si tu n'as pas tous les éléments?"),
            ("ai", "inconnu"),
            ("human", "Es tu prêt à répondre de manière brève et en francais à une question?"),
            ("ai", "Oui, quelle est la question concernant ce patient ?"),
            ("human", "{question}"),
        ]
        models: ClassVar[list] = ["mistral"]
        ressources: ClassVar[list] = ["tncdchc.pdf"]
        question: ClassVar[str] = "En te basant sur les documents de références, est-ce qu'un cardialogue est nécessaire ? "

