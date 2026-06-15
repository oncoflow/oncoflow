import json
import re

from typing import ClassVar, Any
from pydantic import ValidationError, BaseModel, Field

from langchain.agents import create_agent

from src.application.config import AppConfig
from src.infrastructure.llm.factory import get_llm_client

# Legacy import to support existing patch-based unit tests
from src.application.reader import DocumentReader
from src.application.agent.tools import (
    search_on_ressources,
    get_mtd_markdown,
    Context,
)
from langchain.agents.middleware import ToolRetryMiddleware, ModelRetryMiddleware


def extract_json_str(text: str) -> str:
    """
    Extract the most likely valid JSON substring from text.
    """
    # 1. Try to find content inside ```json ... ``` blocks first
    json_blocks = re.findall(r"```json\s*(.*?)\s*```", text, re.DOTALL)
    for block in json_blocks:
        block_clean = block.strip()
        try:
            json.loads(block_clean)
            return block_clean
        except json.JSONDecodeError:
            pass

    # 2. Try to find content inside general ``` ... ``` blocks
    code_blocks = re.findall(r"```\s*(.*?)\s*```", text, re.DOTALL)
    for block in code_blocks:
        block_clean = block.strip()
        try:
            json.loads(block_clean)
            return block_clean
        except json.JSONDecodeError:
            pass

    # 3. Try to scan all braces to find the first valid JSON object
    open_braces = [m.start() for m in re.finditer(r"\{", text)]
    close_braces = [m.start() for m in re.finditer(r"\}", text)]

    for start in open_braces:
        for end in reversed(close_braces):
            if end > start:
                candidate = text[start : end + 1]
                try:
                    json.loads(candidate)
                    return candidate
                except json.JSONDecodeError:
                    pass

    return text.strip()


class ChatResponse(BaseModel):
    response: str = Field(description="The answer to the user question")


class DebateTurn(BaseModel):
    response: str = Field(
        description="Your clinical opinion, arguments, and recommendations based on your specialty."
    )


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
        reasoning: bool = True,
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

        if reasoning is None:
            reasoning = getattr(config.llm, "reasoning", True)

        system_prompt = f"""Answer in {self.response_language} language, not mention it in the answer.
        {self.system_prompt}
        You MUST respond with valid JSON and nothing else.
        No markdown, no explanation, no code blocks — just raw JSON.
        Respond with JSON matching this exact schema:
        {json.dumps(self.output_format.model_json_schema(), indent=2)}
        """
        # Configure logging for the agent
        self.logger = config.set_logger(
            "OncowAgent",
            default_context={
                "model": models_list[0],
                "output_format": self.output_format,
            },
        )

        # Set up readers for the main document and additional resources
        if mtd is not None:
            self.reader = mtd
        self.additionnal_readers = [
            DocumentReader(config, ressource, document_type="ressource")
            for ressource in self.ressources
        ]
        tools = [get_mtd_markdown]
        if len(self.additionnal_readers) > 0:
            tools.append(search_on_ressources)

        # Create the LangChain agent with specific tools and context
        self.agent = create_agent(
            model=llm_client.chat(
                models_list[0],
                reasoning=reasoning,
                # output=self.output_format,
                # tools=[search_on_mtd, search_on_ressources, get_mtd_markdown],
            ),
            tools=tools,
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
            # response_format=ToolStrategy(schema=self.output_format, handle_errors=True),
            response_format=self.output_format,
            # pyrefly: ignore [bad-argument-type]
            context_schema=Context,
            system_prompt=system_prompt,
        )

        self.logger.info(
            f"""Agent succefully created with prompt :
        {system_prompt}
        """
        )
        self.latest_thinking = ""

    def extract_thinking(self, messages: list) -> str:
        thinking_parts = []
        for msg in messages:
            if (
                type(msg).__name__ in ("AIMessage", "AIMessageChunk")
                or getattr(msg, "type", None) == "ai"
            ):
                # 1. Check reasoning_content attribute/kwargs
                reasoning = getattr(msg, "reasoning_content", None)
                if not reasoning and isinstance(
                    getattr(msg, "additional_kwargs", None), dict
                ):
                    reasoning = msg.additional_kwargs.get("reasoning_content")
                if reasoning:
                    thinking_parts.append(reasoning.strip())
                    continue

                content = msg.content
                # 2. Check block list
                if isinstance(content, list):
                    for part in content:
                        if isinstance(part, dict):
                            if part.get("type") == "thinking":
                                think_text = (
                                    part.get("thinking") or part.get("text") or ""
                                )
                                if think_text:
                                    thinking_parts.append(think_text.strip())
                # 3. Check string with <think> tags
                elif isinstance(content, str):
                    matches = re.findall(
                        r"<think>(.*?)(?:</think>|$)", content, re.DOTALL
                    )
                    for m in matches:
                        if m.strip():
                            thinking_parts.append(m.strip())
        return "\n\n".join(thinking_parts)

    def ask(
        self,
        question: str | None = None,
        output_format: type[BaseModel] | str | None = None,
        callbacks: list | None = None,
    ) -> Any:
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

        if output_format is None:
            output_format = self.output_format

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
                config={"callbacks": callbacks} if callbacks else None,
            )
            # Extract and store the thinking process from the execution history
            self.latest_thinking = self.extract_thinking(result.get("messages", []))
            # if langchain tools work, load the response
            if "structured_response" in result:
                if self.output_format is not None and issubclass(
                    self.output_format, BaseModel
                ):
                    return result["structured_response"]
                return json.loads(result["structured_response"])

            # Iterate through messages to find the AI response and validate it against the schema
            self.logger.info(f"AI response : {result}")
            for msg in result["messages"]:
                try:
                    if (
                        type(msg).__name__ in ("AIMessage", "AIMessageChunk")
                        or getattr(msg, "type", None) == "ai"
                    ):
                        self.logger.debug(f"AI response : {result['messages']}")

                        content = msg.content
                        # Handle list of blocks (e.g. thinking / text parts)
                        if isinstance(content, list):
                            text_parts = []
                            for part in content:
                                if isinstance(part, dict):
                                    if part.get("type") == "text":
                                        text_parts.append(part.get("text", ""))
                                elif isinstance(part, str):
                                    text_parts.append(part)
                            content = "".join(text_parts)

                        if isinstance(content, str):
                            content = extract_json_str(content)

                        # Validate the content against the Pydantic model
                        if self.output_format is not None and issubclass(
                            self.output_format, BaseModel
                        ):
                            return self.output_format.model_validate_json(content)

                        return json.loads(content)
                except (ValidationError, ValueError, json.JSONDecodeError) as e:
                    validation_error = e
                    continue
            self.logger.info(f"Error, previous result : {result}")
            question = f"""You made a mistake, correct the outpout\n\n
                        Error : {validation_error}\n\n
                        Here is the previous result:\n{result}"""

        # Raise error if no valid structured response was found
        raise ValueError(
            f"Unable to find message, latest error : {validation_error} - AI response {result}"
        )
