import inspect
from typing import ClassVar, Any


from src.application.config import AppConfig
from src.application.reader import DocumentReader
from src.application.agent.agent import OncowflowAgent


class Agents:
    def __init__(self) -> None:
        self.list = {
            cls_attribute.agent_name: cls_attribute
            for cls_attribute in self.__class__.__dict__.values()
            if inspect.isclass(cls_attribute) and "_model" not in cls_attribute.__name__
        }

        self.expert_agents: list[type[OncowflowAgent]] = [
            cls_attribute
            for cls_attribute in self.__class__.__dict__.values()
            if inspect.isclass(cls_attribute)
            and issubclass(cls_attribute, Agents.Expert_model)
        ]

    class Administratives_agent(OncowflowAgent):
        agent_name: str = "Administrative"
        system_prompt: ClassVar[str] = """
        You are a medical administrative assistant. Your goal is to extract precise information from the patient record without interpretation.

        Instructions:
        1. Use the `search_on_mtd` tool to retrieve relevant information from the patient record.
        2. Answer the user's question strictly using the extracted information.
        3. Do not infer missing details or provide medical opinions.
        4. If the information is not found, state clearly that it is missing from the record.
        5. You can use tools multiple time for each element. Use multiple keywords or synonyms in your search query to improve retrieval.
        6. Respect stricly the response output format.
        """

    class Coordinator_agent(OncowflowAgent):
        agent_name: str = "MDT Coordinator"
        system_prompt: ClassVar[str] = """
        You are the coordinator of a multidisciplinary team (MDT). Your role is to ensure that all necessary information is gathered from the patient record and relevant scientific literature to make a treatment decision.

        Instructions:
        1. Analyze the current MDT file and identify any missing information required for a complete treatment decision.
        2. Use the `search_on_mtd` tool to retrieve relevant information from the patient record.
        3. Use the `search_on_ressources` tool to retrieve scientific information to support your analysis.
        4. Coordinate the different specialists to ensure all aspects of the patient's case are considered.
        5. If information is missing, clearly state what is needed and why.
        6. You can use tools multiple times for each element.
        7. Respect strictly the response output format.
        """

    class Expert_model(OncowflowAgent):
        expert_type: ClassVar[str] = ""
        system_prompt: ClassVar[str] = ""

        def __init__(
            self,
            config: AppConfig,
            mtd: DocumentReader | None = None,
            output_format: Any = None,
        ) -> None:
            self.__class__.system_prompt = f"""
                You are a distinguished medical expert specializing in {self.expert_type}.
                Your task is to answer user questions by synthesizing patient data with scientific informations.

                Instructions:
                1. Use the `search_on_mtd` tool to retrieve relevant information from the patient record.
                2. Use the `search_on_ressources` tool to retrieve scientific informations to support your clinical reasoning.
                3. Answer the user's question by combining patient data and scientific evidence.
                4. Respect stricly the response output format.
                5. You can use tools multiple time for each element. Use multiple keywords or synonyms in your search query.

                Rules:
                - **Patient Record**: Use the patient record as the sole source of truth for the patient's status.
                - **Scope**: Focus strictly on {self.expert_type}. Do not provide advice outside this specialty.
                - **No Interaction**: Do not ask the user for additional information. If data is missing, note it in your response.
                """
            super(Agents.Expert_model, self).__init__(
                config=config, mtd=mtd, output_format=output_format
            )

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
