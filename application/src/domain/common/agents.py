import inspect
from typing import ClassVar, Any


from src.application.config import AppConfig
from src.application.reader import DocumentReader
from src.application.agent.agent import OncowflowAgent


class Agents:
    def __init__(self) -> None:
        self.list = {}
        for name in dir(self.__class__):
            if name.startswith("__"):
                continue
            cls_attribute = getattr(self.__class__, name)
            if (
                inspect.isclass(cls_attribute)
                and "_model" not in cls_attribute.__name__
            ):
                if hasattr(cls_attribute, "agent_name"):
                    self.list[cls_attribute.agent_name] = cls_attribute

        self.expert_agents: list[type[OncowflowAgent]] = []
        for name in dir(self.__class__):
            if name.startswith("__"):
                continue
            cls_attribute = getattr(self.__class__, name)
            if inspect.isclass(cls_attribute) and issubclass(
                cls_attribute, Agents.Expert_model
            ):
                self.expert_agents.append(cls_attribute)

    class Ressource_agent(OncowflowAgent):
        agent_name: str = "Ressource Assistant"
        system_prompt: ClassVar[str] = """
        You are a clinical resource assistant. Your goal is to retrieve relevant scientific and medical guidelines from the resource documents to answer the user's request.

        Instructions:
        1. If the user asks for a summary, table of contents, or overall structure of the document, use the `get_mtd_markdown` tool to read the full document content.
        2. If the user asks specific questions or searches for particular medical facts/guidelines, use the `search_on_ressources` tool. Formulate precise queries containing key medical terms, symptoms, or keywords from the user's prompt.
        3. You can combine both tools and run them multiple times if needed to ensure you gather all relevant context from the document.
        4. Synthesize your final answer strictly using the retrieved evidence. Do not extrapolate, assume, or provide medical opinions not documented in the text.
        5. If the information cannot be found in the resource after searching, clearly state that the resource does not contain information to answer the question.
        6. Respect strictly the required JSON output format.
        """

    class Administratives_agent(OncowflowAgent):
        agent_name: str = "Administrative"
        system_prompt: ClassVar[str] = """
        You are a medical administrative assistant. Your goal is to extract precise information from the patient record without interpretation.

        Instructions:
        1. Use the `get_mtd_markdown` tool to retrieve relevant information from the patient record.
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
        2. Use the `get_mtd_markdown` tool to retrieve relevant information from the patient record.
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
                1. Use the `get_mtd_markdown` tool to retrieve relevant information from the patient record.
                2. Use the `search_on_ressources` tool to retrieve scientific informations to support your clinical reasoning.
                3. Answer the user's question by combining patient data and scientific evidence.
                4. Respect stricly the response output format.
                5. You can use tools multiple time for each element. Use multiple keywords or synonyms in your search query.

                Rules:
                - **Patient Record**: Use the patient record as the sole source of truth for the patient's status.
                - **Scope**: Focus strictly on {self.expert_type}. Do not provide advice outside this specialty.
                - **No Interaction**: Do not ask the user for additional information. If data is missing, note it in your response.
                - If a value is not found, set it to null in the JSON.
                """
            super(Agents.Expert_model, self).__init__(
                config=config, mtd=mtd, output_format=output_format
            )
