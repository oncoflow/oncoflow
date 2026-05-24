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


class DebateTurn(BaseModel):
    response: str = Field(
        description="Votre avis clinique, arguments et recommandations basés sur votre spécialité."
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

    @classmethod
    def collaborative_debate(
        cls,
        agents_classes: list[type["OncowflowAgent"]],
        question: str,
        output_format: type[BaseModel],
        config: AppConfig,
        mtd: DocumentReader,
        logger: Any,
    ) -> dict:
        logger.info("Running collaborative debate mode...")

        # Step 1: Initial Turn (Parallel Reasoning with DebateTurn format)
        opinions = {}
        for magent in agents_classes:
            a = magent(config=config, mtd=mtd, output_format=DebateTurn)
            logger.info(f"Debate: Requesting initial analysis from {a.agent_name}...")

            opinion_prompt = (
                f"En tant qu'expert en {a.expert_type if hasattr(a, 'expert_type') else a.agent_name}, "
                f"analysez le dossier du patient et donnez vos arguments initiaux concernant la question suivante :\n{question}"
            )
            try:
                res = a.ask(opinion_prompt)
                opinions[a.agent_name] = res.response
            except Exception as e:
                logger.error(f"Error getting opinion from {a.agent_name}: {e}")
                opinions[a.agent_name] = "Erreur ou pas d'avis fourni."
            del a

        # Step 2: Cross-Review & Debate Turn
        compiled_opinions = "\n".join(
            f"- **{name}** : {text}" for name, text in opinions.items()
        )
        logger.debug(f"Debate: Compiled initial opinions:\n{compiled_opinions}")

        updated_opinions = {}
        for magent in agents_classes:
            a = magent(config=config, mtd=mtd, output_format=DebateTurn)
            logger.info(f"Debate: Requesting cross-review from {a.agent_name}...")

            debate_prompt = (
                f"Nous menons un débat d'équipe multidisciplinaire (RCP). Voici les avis et arguments initiaux de tous les experts participants :\n\n"
                f"{compiled_opinions}\n\n"
                f"La question globale est : {question}\n\n"
                f"Veuillez examiner les avis des autres experts. Donnez votre évaluation clinique finale affinée, en répondant aux points d'accord ou de désaccord, afin d'aider à dégager un consensus collectif."
            )
            try:
                res = a.ask(debate_prompt)
                updated_opinions[a.agent_name] = res.response
            except Exception as e:
                logger.error(f"Error getting updated opinion from {a.agent_name}: {e}")
                updated_opinions[a.agent_name] = opinions.get(
                    a.agent_name, "Pas d'avis fourni."
                )
            del a

        # Step 3: Synthesis & Final Structured Consensus
        final_compiled_opinions = "\n".join(
            f"- **{name}** : {text}" for name, text in updated_opinions.items()
        )
        logger.debug(f"Debate: Compiled final opinions:\n{final_compiled_opinions}")

        # Use the first agent as coordinator to generate final structured pydantic format
        coordinator_agent_cls = agents_classes[0]
        coordinator = coordinator_agent_cls(
            config=config, mtd=mtd, output_format=output_format
        )
        logger.info(
            f"Debate: Synthesizing final structured consensus using {coordinator.agent_name}..."
        )

        synthesis_prompt = (
            f"Vous êtes le coordinateur du comité multidisciplinaire (RCP). Les experts ont terminé leur débat. "
            f"Voici le résumé de leurs avis finaux :\n\n"
            f"{final_compiled_opinions}\n\n"
            f"La question globale est : {question}\n\n"
            f"Veuillez synthétiser l'ensemble de la discussion, résoudre les éventuels désaccords pour parvenir à un consensus unique et remplir le format de réponse structuré attendu."
        )

        try:
            datas = json.loads(coordinator.ask(synthesis_prompt).json())
            return datas
        except Exception as e:
            logger.error(f"Error during debate synthesis: {e}")
            raise e
        finally:
            del coordinator
