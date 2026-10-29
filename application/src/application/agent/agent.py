import json
import re

from typing import ClassVar, Any, cast
from pydantic import ValidationError, BaseModel, Field

from langchain.agents import create_agent

from src.application.config import AppConfig
from src.infrastructure.llm.factory import get_llm_client

# Legacy import to support existing patch-based unit tests
from src.application.reader import DocumentReader
from src.application.agent.tools import (
    search_on_ressources,
    get_mtd_markdown,
    get_patient_mtds_markdown,
    get_patient_ai_history,
    Context,
    PatientContext,
)
from langchain.agents.middleware import ToolRetryMiddleware, ModelRetryMiddleware


def extract_json_str(text: str) -> str:
    """
    Extract the most likely valid JSON substring from text.
    """
    # 0. Clean thinking blocks (<think>...</think>) from the text to isolate target JSON
    text_clean = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

    # 1. Try to find content inside ```json ... ``` blocks first
    json_blocks = re.findall(r"```json\s*(.*?)\s*```", text_clean, re.DOTALL)
    for block in json_blocks:
        block_clean = block.strip()
        try:
            json.loads(block_clean)
            return block_clean
        except json.JSONDecodeError:
            pass

    # 2. Try to find content inside general ``` ... ``` blocks
    code_blocks = re.findall(r"```\s*(.*?)\s*```", text_clean, re.DOTALL)
    for block in code_blocks:
        block_clean = block.strip()
        try:
            json.loads(block_clean)
            return block_clean
        except json.JSONDecodeError:
            pass

    # 3. Scan from each opening brace in O(n) using JSONDecoder.raw_decode
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", text_clean):
        start = match.start()
        try:
            _, end = decoder.raw_decode(text_clean, start)
            return text_clean[start:end]
        except json.JSONDecodeError:
            continue

    # 4. Last resort: repair malformed JSON (trailing comma, single quotes, truncated)
    if "{" in text_clean:
        candidate = text_clean[text_clean.find("{") :]
        try:
            from json_repair import repair_json

            repaired = repair_json(candidate, return_objects=False)
            if isinstance(repaired, str) and repaired.strip():
                parsed = json.loads(repaired)
                if isinstance(parsed, dict):
                    return repaired
        except Exception:
            pass

    return text_clean


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
    additionnal_readers: list[DocumentReader] = []
    patient_readers: list[DocumentReader] = []
    reasoning_budget: int | None = 1024
    # Retry prompt budget (characters, ~3.5 chars/token): keeps corrections small
    # enough for local models with a limited context window.
    RETRY_MAX_OUTPUT_CHARS: ClassVar[int] = 2000
    RETRY_MAX_ERROR_CHARS: ClassVar[int] = 800

    @classmethod
    def get_system_prompt(cls) -> str:
        """Retourne le prompt système de la classe sans instanciation."""
        return cls.system_prompt

    @classmethod
    def get_models(cls, config: AppConfig) -> list[str]:
        """Retourne les modèles configurés pour la classe sans instanciation."""
        if cls.models is not None:
            return cls.models
        return [m.strip() for m in config.llm.models.split(",") if m.strip()]

    def __init__(
        self,
        config: AppConfig,
        mtd: DocumentReader | None = None,
        output_format: type[BaseModel] | None = None,
        reasoning: bool = True,
        reasoning_budget: int | None = None,
        reader: DocumentReader | None = None,
        additionnal_readers: list[DocumentReader] | None = None,
        patient_readers: list[DocumentReader] | None = None,
    ):
        """
        Initialize the OncowflowAgent.

        Args:
            config (AppConfig): Application configuration.
            mtd (DocumentReader): The main document reader for MTDs.
            output_format (any, optional): The Pydantic model defining the expected output structure.
            patient_readers (list[DocumentReader], optional): Readers for all RCP documents of a patient dossier.
        """
        if output_format is None:
            self.output_format = ChatResponse
        else:
            self.output_format = output_format

        # Determine language dynamically from config
        self.response_language = getattr(config, "language", "french")

        # Initialize the LLM client based on configuration
        llm_client = get_llm_client(config)

        # Determine the list of models to use
        models_list = (
            self.models if self.models is not None else config.llm.models.split(",")
        )
        self.models = models_list

        if reasoning is None:
            reasoning = getattr(config.llm, "reasoning", True)

        if reasoning_budget is not None:
            self.reasoning_budget = reasoning_budget

        self.patient_readers = list(patient_readers) if patient_readers else []
        mtd_tool_name = (
            "get_patient_mtds_markdown" if self.patient_readers else "get_mtd_markdown"
        )
        history_tool_instruction = (
            "\n        - Call `get_patient_ai_history` to retrieve the chronological history of AI-extracted clinical and expert information across all RCPs of the patient dossier."
            if self.patient_readers
            else ""
        )

        system_prompt = f"""Answer in {self.response_language.capitalize()} language, not mention it in the answer.
        You are a clinical data extraction assistant operating in a live production environment.
        {self.system_prompt}

        ## STEP 1 — Gather information (use tools)
        If the required information is NOT already in your context, call the appropriate tools FIRST:
        - Call `{mtd_tool_name}` to retrieve the full patient record text.{history_tool_instruction}
        - Call `search_on_ressources` to search reference guidelines if needed.
        - You MAY call tools multiple times to find all required fields.
        - Do NOT guess, mock, or fabricate any clinical information.

        ## STEP 2 — Output your final answer (JSON only)
        Once you have collected all the needed information from the tools, output your answer as a single, valid JSON object matching the schema below.
        - All schema keys and enum values must remain strictly in English as defined by the schema.
        - Write only free-form text fields (summaries, diagnostics, recommendations) in {self.response_language}.
        - Output ONLY the raw JSON — no markdown fences, no explanation, no code blocks.

        ## STEP 3 — formatting outputs
        - You MUST respond with output JSON schema:
        {json.dumps(self.output_format.model_json_schema(), indent=2)}
        """
        # Configure logging for the agent
        self.logger = config.set_logger(
            "OncowAgent",
            default_context={
                "model": models_list[0],
                "output_format": getattr(
                    self.output_format, "__name__", str(self.output_format)
                ),
            },
        )

        # Set up readers for the main document and additional resources
        self.reader = mtd
        tools = []
        if self.patient_readers:
            tools.append(get_patient_mtds_markdown)
            tools.append(get_patient_ai_history)
        elif mtd is not None:
            tools.append(get_mtd_markdown)

        self.additionnal_readers = [
            DocumentReader(config, ressource, document_type="ressource")
            for ressource in self.ressources
        ]

        if additionnal_readers:
            self.additionnal_readers.extend(additionnal_readers)
        if len(self.additionnal_readers) > 0:
            tools.append(search_on_ressources)

        active_context_schema = (
            cast(Any, PatientContext) if self.patient_readers else cast(Any, Context)
        )

        # Create the LangChain agent with specific tools and context
        self.agent = create_agent(
            model=llm_client.chat(
                models_list[0],
                reasoning=reasoning,
                reasoning_budget=self.reasoning_budget,
                output=self.output_format,
                tools=tools,
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
            # response_format=self.output_format,
            response_format=None,
            context_schema=active_context_schema,
            system_prompt=system_prompt,
        )

        self.logger.info(
            "Agent %s created (reasoning=%s, reasoning_budget=%s)",
            self.agent_name or self.__class__.__name__,
            reasoning,
            self.reasoning_budget,
        )
        self.logger.debug("Agent system prompt:\n%s", system_prompt)
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
        self.logger.info(
            "Ask agent %s (question_len=%d)",
            self.agent_name or self.__class__.__name__,
            len(question or self.question or ""),
        )
        self.logger.debug('Ask "%s" to agent ...', question)

        if question is None:
            question = self.question

        if output_format is None:
            output_format = self.output_format

        retry = 3
        validation_error = None
        result = None
        last_failed_output = None
        original_question = question

        for r in range(retry):
            # Invoke the agent with the user question and context (readers)
            runtime_context = (
                PatientContext(
                    patient_readers=self.patient_readers,
                    additionnal_readers=self.additionnal_readers,
                    logger=self.logger,
                )
                if self.patient_readers
                else Context(
                    reader=self.reader,
                    additionnal_readers=self.additionnal_readers,
                    logger=self.logger,
                )
            )
            result = self.agent.invoke(
                {"messages": [{"role": "user", "content": question}]},
                context=runtime_context,
                config={
                    "callbacks": callbacks,
                    "tags": [self.agent_name] if self.agent_name else [],
                }
                if callbacks
                else None,
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

            # Iterate from the most recent message: the final AI answer comes last,
            # intermediate AI messages (tool calls, drafts) are only a fallback.
            self.logger.debug("AI response : %s", result)
            last_failed_output = None
            round_error = None
            for msg in reversed(result["messages"]):
                if not (
                    type(msg).__name__ in ("AIMessage", "AIMessageChunk")
                    or getattr(msg, "type", None) == "ai"
                ):
                    continue
                content = self._message_text(msg.content)
                if not content.strip():
                    continue
                content = extract_json_str(content)
                try:
                    # Validate the content against the Pydantic model
                    if self.output_format is not None and issubclass(
                        self.output_format, BaseModel
                    ):
                        return self.output_format.model_validate_json(content)
                    return json.loads(content)
                except (ValidationError, ValueError, json.JSONDecodeError) as e:
                    # Keep the error of the most recent AI message only
                    if round_error is None:
                        round_error = e
                        last_failed_output = content
            validation_error = round_error or validation_error

            self.logger.info(
                "Invalid agent output (attempt %d/%d, %d chars)",
                r + 1,
                retry,
                len(last_failed_output or ""),
            )
            question = self._build_correction_prompt(
                original_question=original_question,
                error=validation_error,
                failed_output=last_failed_output,
            )

        # Raise error if no valid structured response was found.
        # Do not embed the full agent result: it contains tool outputs (patient records)
        # and can be propagated to logs / HTTP error details.
        raise ValueError(
            "Unable to find message, latest error : "
            f"{self._truncate(str(validation_error), self.RETRY_MAX_ERROR_CHARS)} - "
            f"AI response {self._truncate(last_failed_output or '<no AI text output>', self.RETRY_MAX_OUTPUT_CHARS)}"
        )

    @staticmethod
    def _message_text(content: Any) -> str:
        """Return the textual part of a message content, ignoring thinking blocks."""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            text_parts = []
            for part in content:
                if isinstance(part, dict):
                    if part.get("type") == "text":
                        text_parts.append(part.get("text", ""))
                    # "thinking" blocks are intentionally excluded from the output
                elif isinstance(part, str):
                    text_parts.append(part)
            return "".join(text_parts)
        return str(content) if content is not None else ""

    @staticmethod
    def _truncate(text: str, limit: int) -> str:
        """Keep the head of `text` (JSON structure) within `limit` characters."""
        if len(text) <= limit:
            return text
        return f"{text[:limit]}\n[... {len(text) - limit} caractères tronqués]"

    def _build_correction_prompt(
        self,
        original_question: str,
        error: Exception | None,
        failed_output: str | None,
    ) -> str:
        """
        Build a bounded correction prompt for the retry.

        The original question is always re-sent (otherwise the agent loses its task),
        but neither the full message history nor the tool outputs are replayed: the
        previous output and the validation error are truncated so the retry fits in
        the context window of small local models (e.g. Qwen 3.6).
        """
        error_txt = self._truncate(
            str(error) if error else "No JSON answer found.",
            self.RETRY_MAX_ERROR_CHARS,
        )
        output_txt = (
            self._truncate(failed_output, self.RETRY_MAX_OUTPUT_CHARS)
            if failed_output
            else None
        )
        if self.response_language == "french":
            prompt = (
                "Answer in French language, not mention it in the answer.\n"
                f"{original_question}\n\n"
                "Votre réponse précédente ne respectait pas le schéma JSON attendu. "
                "Répondez à nouveau avec une sortie JSON correspondant exactement au schéma.\n\n"
                f"Erreur : {error_txt}"
            )
            if output_txt:
                prompt += f"\n\nSortie invalide précédente :\n{output_txt}"
        else:
            prompt = (
                f"Answer in {self.response_language.capitalize()} language, not mention it in the answer.\n"
                f"{original_question}\n\n"
                "Your previous answer did not match the expected JSON schema. "
                "Answer again with a JSON output matching the schema exactly.\n\n"
                f"Error: {error_txt}"
            )
            if output_txt:
                prompt += f"\n\nPrevious invalid output:\n{output_txt}"
        return prompt
