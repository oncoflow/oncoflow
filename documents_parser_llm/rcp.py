from typing import Optional
from langchain_core.pydantic_v1 import BaseModel, Field, validator

class RcpFiche(BaseModel):
    
    class Patient(BaseModel):
        first_name: Optional[str] = Field(description="first name of Patient")
        last_name: str = Field(description="last name of Patient")
        age: int = Field(description="Age of Patient")
        