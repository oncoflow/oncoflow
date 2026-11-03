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
    size_bytes: int = 0
    updated_at: Optional[str] = None


class ResourceIndexedResponse(BaseModel):
    filename: str
    domain: str
    message: str


class ResourceDeleteResponse(BaseModel):
    deleted: str
