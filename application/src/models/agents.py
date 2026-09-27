from typing import List
from pydantic import BaseModel


class AgentDetailResponse(BaseModel):
    name: str
    system_prompt: str
    models: List[str]
    resources: List[str]
