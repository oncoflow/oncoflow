from typing import Literal, Optional

from pydantic import BaseModel, Field


class ResourceChatRequest(BaseModel):
    message: str = Field(description="Question sur le document de référence")
    language: Optional[Literal["french", "english"]] = Field(
        default=None,
        description="Langue de réponse souhaitée pour l'agent ('french' ou 'english')",
    )


class ResourceIndexResponse(BaseModel):
    filename: str
    is_indexed: bool


class ResourceIndexedResponse(BaseModel):
    filename: str
    domain: str
    message: str
