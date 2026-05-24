import json

from typing import ClassVar, Any
from pydantic import ValidationError, BaseModel, Field

from langchain.agents import create_agent

from src.application.config import AppConfig
from src.infrastructure.llm.factory import get_llm_client

# Legacy import to support existing patch-based unit tests
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

    model: ClassVar[str | None] = None
    system_prompt: ClassVar[str] = ""
    question: ClassVar[str] = "Nothing"
    models: list[str] | None = None
    ressources: ClassVar[list[str]] = []
    response_language: str = "french"
    output_format: type[BaseModel] | None = None
    agent: Any = None
    agent_name: str = ""

    def __init__(
        self,
        config: AppConfig,
        mtd: DocumentReader | None = None,
        output_format: type[BaseModel] | None = None,
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
        llm_client = get_llm_client(config)

        # Determine the list of models to use
        models_list = (
            self.models if self.models is not None else config.llm.models.split(",")
        )
        self.models = models_list

        system_prompt = f"""Answer in {self.response_language} language, not mention it in the answer.
        {self.system_prompt}
        """
        # Configure logging for the agent
        self.logger = config.set_logger(
            "OncowAgent",
            default_context={
                "model": models_list[0],
                "output_format": self.output_format,
            },
        )

        # Create the LangChain agent with specific tools and context
        self.agent = create_agent(
            model=llm_client.chat(
                models_list[0],
                output=self.output_format,
            ),
            tools=[search_on_mtd, search_on_ressources, get_mtd_markdown],
            middleware=[
                ToolRetryMiddleware[Any, Any](
                    max_retries=3,
                    backoff_factor=2.0,
                    initial_delay=1.0,
                ),
                ModelRetryMiddleware[Any, Any](
                    max_retries=3,
                    backoff_factor=2.0,
                    initial_delay=1.0,
                ),
            ],
            response_format=ToolStrategy(schema=self.output_format, handle_errors=True),
            # pyrefly: ignore [bad-argument-type]
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

    def ask(self, question: str | None = None) -> Any:
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
        validation_error = None
        result = None

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
                if self.output_format is not None and issubclass(
                    self.output_format, BaseModel
                ):
                    return result["structured_response"]
                return json.loads(result["structured_response"])

            # Iterate through messages to find the AI response and validate it against the schema
            for msg in result["messages"]:
                try:
                    if (
                        type(msg).__name__ in ("AIMessage", "AIMessageChunk")
                        or getattr(msg, "type", None) == "ai"
                    ):
                        self.logger.debug(f"AI response : {result['messages']}")

                        # Strip markdown wrappers if any
                        content = msg.content
                        if isinstance(content, str):
                            content = content.strip()
                            if content.startswith("```json"):
                                content = content[7:]
                            if content.endswith("```"):
                                content = content[:-3]
                            content = content.strip()

                        # Validate the content against the Pydantic model
                        if self.output_format is not None and issubclass(
                            self.output_format, BaseModel
                        ):
                            return self.output_format.model_validate_json(content)

                        return json.loads(content)
                except (ValidationError, ValueError, json.JSONDecodeError) as e:
                    validation_error = e
                    continue
            self.logger.info(f"Retry {r + 1}/{retry} ...")

        # Raise error if no valid structured response was found
        raise ValueError(
            f"Unable to find message, latest error : {validation_error} - AI response {result}"
        )
