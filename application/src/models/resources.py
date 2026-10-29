from pydantic import BaseModel, Field


class ResourceChatRequest(BaseModel):
    message: str = Field(description="Question sur le document de référence")


class ResourceIndexResponse(BaseModel):
    filename: str
    is_indexed: bool


class ResourceIndexedResponse(BaseModel):
    filename: str
    domain: str
    message: str
