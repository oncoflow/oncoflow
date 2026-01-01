import inspect
from typing import List, Optional, ClassVar

from pydantic import BaseModel

from src.application.config import AppConfig
from src.application.reader import DocumentReader
from src.application.agent.agent import OncowflowAgent

class Agents:

    def __init__(self) -> None:
        self.list = [
            cls_attribute
            for cls_attribute in self.__class__.__dict__.values()
            if inspect.isclass(cls_attribute)
            and "_model" not in cls_attribute.__name__
        ]
    
    class Administratives_agent(OncowflowAgent):
        agent_name: str = "Administrative"
        system_prompt: ClassVar[str] = """
        You are a medical administrative assistant, read patient record and extract exact information without reflexion
        You have to answer the user question.
        use search_on_mtd to search information about patient record.
        """

    class Expert_model(OncowflowAgent):

        expert_type: ClassVar[str] = ""
        system_prompt: ClassVar[str] = ""
        
        def __init__(
            self,
            config: AppConfig,
            mtd: DocumentReader,
            output_format: any = None,
        ) -> None:
            self.system_prompt = f"""
                You are a medical expert in {self.expert_type} and only in this diseases, answer user question based with this rules :
                - All current information about the patient is in the patient record
                - you can found all the current diagnostics made in the patient record
                - you must search on ressources all scientific information to complete the response
                - Do not ask any questions to user.
                """
            super(Agents.Expert_model, self).__init__(config=config, mtd=mtd, output_format=output_format)

    class Pancreas_expert_agent(Expert_model):
        agent_name: str = "pancreas expert"
        expert_type = "pancreas diseases"

        ressources = ["TNCDPANCREAS.pdf"]

    class Oesophagus_expert_agent(Expert_model):
        agent_name: str = "oesophagus expert"
        expert_type = "oesophagus diseases"

        ressources = ["TNCDOESOPHAGE.pdf"]

    class Hepatocellular_expert_agent(Expert_model):
        agent_name: str = "hepatocellular expert"
        expert_type = "hepatocellular diseases"

        ressources = ["TNCDCHC.pdf"]