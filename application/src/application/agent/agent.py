import json

from typing import ClassVar
from pydantic import ValidationError

from langchain.agents import create_agent

from src.application.config import AppConfig
from src.application.tools import timed
from src.infrastructure.llm.ollama import OllamaConnect
from src.application.reader import DocumentReader
from src.application.agent.tools import search_on_mtd, search_on_ressources, Context
from langchain.agents.structured_output import ToolStrategy


class OncowflowAgent:
    """
    Agent responsible for handling interactions with the LLM to answer questions
    based on medical technical documents (MTD) and resources.
    """
    model: ClassVar[str] = None
    system_prompt: ClassVar[str] = ""
    question: ClassVar[str] = "Nothing"
    models: ClassVar[list[str]] = None
    ressources: ClassVar[str] = []

    def __init__(
        self,
        config: AppConfig,
        mtd: DocumentReader = None,
        output_format: any = None,
    ):
        """
        Initialize the OncowflowAgent.

        Args:
            config (AppConfig): Application configuration.
            mtd (DocumentReader): The main document reader for MTDs.
            output_format (any, optional): The Pydantic model defining the expected output structure.
        """
        self.output_format = output_format

        # Initialize the LLM client based on configuration
        if config.llm.type.lower() == "ollama":
            llm_client = OllamaConnect(config)
        else:
            raise ValueError(f"{config.llm.type} not yet supported")

        # Determine the list of models to use
        if self.models is None:
            self.models = config.llm.models.split(",")

        # Create the LangChain agent with specific tools and context
        self.agent = create_agent(
            model=llm_client.chat(self.models[0], output=output_format),
            tools=[search_on_mtd, search_on_ressources],
            # middleware=[self.dynamic_model_selection],
            # response_format=ToolStrategy(
            #     schema=output_format, handle_errors=True
            # ),
            context_schema=Context,
            system_prompt=self.system_prompt,
        )

        # Set up readers for the main document and additional resources
        if mtd is not None:
            self.reader = mtd
        self.additionnal_readers = [
            DocumentReader(config, ressource, document_type="ressource")
            for ressource in self.ressources
        ]

        # Configure logging for the agent
        self.logger = config.set_logger(
            "OncowAgent",
            default_context={
                "model": self.models[0],
                "system_prompt": self.system_prompt,
                "output_format": self.output_format,
            },
        )
        self.logger.info("Agent succefully created")

    def ask(self, question: str = None, structuredResponse: bool = True) -> dict:
        """
        Ask a question to the agent.

        Args:
            question (str, optional): The question to ask. Defaults to self.question.
            structuredResponse (bool, optional): Whether to expect a structured response. Defaults to True.

        Returns:
            dict: The parsed JSON response from the agent matching the output_format.

        Raises:
            ValueError: If the agent fails to provide a valid response matching the schema.
        """
        self.logger.info('Ask "%s" to agent ...', question)

        if question is None:
            question = self.question

        # Invoke the agent with the user question and context (readers)
        result = self.agent.invoke(
            {"messages": [{"role": "user", "content": question}]},
            context=Context(
                reader=self.reader, additionnal_readers=self.additionnal_readers
            ),
        )
        # Iterate through messages to find the AI response and validate it against the schema
        for msg in result["messages"]:
            try:
                if type(msg).__name__ == "AIMessage":
                    self.logger.info(f"AI response : {result['messages']}")
                    # Validate the content against the Pydantic model
                    self.output_format.model_validate_json(msg.content)
                    return json.loads(msg.content)
            except ValidationError:
                continue

        # Raise error if no valid structured response was found
        raise ValueError(f"AI response {result['messages']}")
