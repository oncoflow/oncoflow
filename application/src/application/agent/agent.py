import json

from typing import ClassVar
from pydantic import ValidationError, BaseModel, Field

from langchain.agents import create_agent

from src.application.config import AppConfig
from src.infrastructure.llm.ollama import OllamaConnect
from src.application.reader import DocumentReader
from src.application.agent.tools import (
    search_on_mtd,
    search_on_ressources,
    get_mtd_markdown,
    Context,
)
from langchain.agents.structured_output import ToolStrategy
from langchain.agents.middleware import ToolRetryMiddleware, ModelRetryMiddleware


class ChatResponse(BaseModel):
    response: str = Field(description="The answer to the user question")


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
    response_language = "french"

    def __init__(
        self,
        config: AppConfig,
        mtd: DocumentReader = None,
        output_format: BaseModel = None,
    ):
        """
        Initialize the OncowflowAgent.

        Args:
            config (AppConfig): Application configuration.
            mtd (DocumentReader): The main document reader for MTDs.
            output_format (any, optional): The Pydantic model defining the expected output structure.
        """
        if output_format is None:
            self.output_format = ChatResponse
        else:
            self.output_format = output_format

        # Initialize the LLM client based on configuration
        if config.llm.type.lower() == "ollama":
            llm_client = OllamaConnect(
                config,
            )
        else:
            raise ValueError(f"{config.llm.type} not yet supported")

        # Determine the list of models to use
        if self.models is None:
            self.models = config.llm.models.split(",")

        system_prompt = f"""Answer in {self.response_language} language, not mention it in the answer.
        {self.system_prompt}
        """
        # Configure logging for the agent
        self.logger = config.set_logger(
            "OncowAgent",
            default_context={
                "model": self.models[0],
                "output_format": self.output_format,
            },
        )

        # Create the LangChain agent with specific tools and context
        self.agent = create_agent(
            model=llm_client.chat(self.models[0], output=self.output_format),
            tools=[search_on_mtd, search_on_ressources, get_mtd_markdown],
            middleware=[
                ToolRetryMiddleware(
                    max_retries=3,
                    backoff_factor=2.0,
                    initial_delay=1.0,
                ),
                ModelRetryMiddleware(
                    max_retries=3,
                    backoff_factor=2.0,
                    initial_delay=1.0,
                ),
            ],
            response_format=ToolStrategy(schema=self.output_format, handle_errors=True),
            context_schema=Context,
            system_prompt=system_prompt,
        )

        # Set up readers for the main document and additional resources
        if mtd is not None:
            self.reader = mtd
        self.additionnal_readers = [
            DocumentReader(config, ressource, document_type="ressource")
            for ressource in self.ressources
        ]

        self.logger.info(
            f"""Agent succefully created with prompt :
        {system_prompt}
        """
        )

    def ask(self, question: str = None) -> dict:
        """
        Ask a question to the agent.

        Args:
            question (str, optional): The question to ask. Defaults to self.question.

        Returns:
            dict: The parsed JSON response from the agent matching the output_format.

        Raises:
            ValueError: If the agent fails to provide a valid response matching the schema.
        """
        self.logger.info('Ask "%s" to agent ...', question)

        if question is None:
            question = self.question

        retry = 3

        for r in range(retry):
            # Invoke the agent with the user question and context (readers)
            result = self.agent.invoke(
                {"messages": [{"role": "user", "content": question}]},
                context=Context(
                    reader=self.reader,
                    additionnal_readers=self.additionnal_readers,
                    logger=self.logger,
                ),
            )

            # if langchain tools work, load the response
            if "structured_response" in result:
                if issubclass(self.output_format, BaseModel):
                    return result["structured_response"]
                return json.loads(result["structured_response"])

            # Iterate through messages to find the AI response and validate it against the schema
            for msg in result["messages"]:
                try:
                    if type(msg).__name__ == "AIMessage":
                        self.logger.debug(f"AI response : {result['messages']}")
                        # Validate the content against the Pydantic model
                        if issubclass(self.output_format, BaseModel):
                            return self.output_format.model_validate_json(msg.content)

                        return json.loads(msg.content)
                except ValidationError as e:
                    validation_error = e
                    continue
            self.logger.info(f"Retry {r + 1}/{retry} ...")

        # Raise error if no valid structured response was found
        raise ValueError(
            f"Unable to find message, latest error : {validation_error} - AI response {result}"
        )
