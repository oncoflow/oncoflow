from typing import Optional
from langchain_core.pydantic_v1 import BaseModel, Field, validator

class RcpFiche(BaseModel):
    
    class Patient(BaseModel):
        full_name: str = Field(description="full name of Patient")
        age: int = Field(description="Age of Patient")
        
    class Cardiologue(BaseModel):
        necessary: bool = Field(description="caridiologue est necessaire")
        reason: str = Field(description="Pourquoi")