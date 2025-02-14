from langchain_core.prompts import ChatPromptTemplate, HumanMessagePromptTemplate, PromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.exceptions import OutputParserException

from langchain_core.runnables import RunnablePassthrough

from pydantic.v1 import error_wrappers

from src.application.config import AppConfig
from src.application.tools import timed
from src.infrastructure.llm.ollama import OllamaConnect


class Llm:
    """
    A class to handle interacting with language models.

    Attributes:
        model: The language model to use. Can be either an Ollama or a different model type.
        default_prompt: The default prompt to use for the language model.

    Methods:
        __init__(self, config=AppConfig): Initializes the llm object with the configuration.
    """

    def __init__(self, config=AppConfig, embeddings=False, models=None):
        self.model = {}
        self.chain = {}
        self.embeddings = None
        self.current_model = None

        self.default_prompt = ChatPromptTemplate

        if config.llm.type.lower() == "ollama":
            llm_client = OllamaConnect(config)
        else:
            raise ValueError(f"{config.llm.type} not yet supported")

        if embeddings:

            self.embeddings = llm_client.embedding
            print(self.embeddings)

            list_models = [config.llm.embeddings]
            self.logger = config.set_logger(
                "embeddings",
                default_context={
                    "llm_type": config.llm.type.lower(),
                    "list_models": list_models,
                },
                additional_context=["model"],
            )
        else:
            if models is None or not models:
                list_models = config.llm.models.split(",")
            else:
                list_models = models

            if list_models == "all":
                list_models = llm_client.get_models()

            for model in list_models:
                self.model[model] = llm_client.chat(model)
            self.logger = config.set_logger(
                "llm",
                default_context={
                    "llm_type": config.llm.type.lower(),
                    "list_models": list_models,
                },
                additional_context=["model"],
            )
        self.logger_default_extra={"model": "Unknow"}
        self.logger.debug("Class llm succesfully init", extra={"model": ""})

    def make_default_prompt(self, prompt=None):
        """
        This method sets the default prompt for the language model.

        Args:
            prompt: A list of messages to use for the prompt.
        """
        if prompt is None:
            prompt = []
        self.default_prompt = prompt

        # print("MAKING DEFAUT PROMPT")
        # ic(self.default_prompt)
        self.logger.debug(
            "Default prompt = %s",
            self.default_prompt,
            extra={"model": self.model.keys()},
        )

    def create_chain(
        self, context, additionnal_context=None, parser=JsonOutputParser()
    ):
        """
        Creates a chain for the language model using the provided context and additional context.

        This method initializes the base chain with the given context, format instructions,
        and question. If additional context is provided, it adds retrievers to the chain.
        The default prompt is then merged into the chain, followed by the language model
        and output parser for each supported model.

        Args:
            context: The main context to use in the chain.
            additionnal_context (optional): A list of dictionaries containing additional contexts
                with their respective names and retrievers. Defaults to None.
            parser (optional): The output parser to use. Defaults to JsonOutputParser().
        """
        base_chain = {
            "context": context,
            "question": RunnablePassthrough(),
            #"format_instructions": lambda x : parser.get_format_instructions()
        }
        
        prompt = HumanMessagePromptTemplate(
            prompt=PromptTemplate(
                template='{format_instructions}',
                input_variables=[],
                partial_variables={"format_instructions":  parser.get_format_instructions()}    
            )
        )

        parserChat = ChatPromptTemplate.from_messages(self.default_prompt + [prompt])

        if additionnal_context is not None:
            for context in additionnal_context:
                base_chain |= {context["name"]: context["retriever"]}
        chain = base_chain | parserChat

        for name, model in self.model.items():
            self.chain[name] = chain | model | parser
            # print(completion)
            # retry_parser = RetryOutputParser.from_llm(parser=parser, llm=model)
            # self.chain[name] = RunnableParallel(
            #     completion = completion,
            #     prompt_value = chain
            # ) | RunnableLambda(lambda x: retry_parser.parse_with_prompt(**x))
            # self.logger.debug(
            #     "Set chain : %s", self.chain[name].get_prompts(), extra={"model": name})

    @timed
    def invoke_multimodels_chain(self, query, parser=JsonOutputParser()):
        """
        Asks a question about the document and returns the answer.

        Args:
            query: The question to ask about the document.

        Returns:
            The answer to the question.
        """

        self.logger.debug(
            "Set human prompt : %s", query, extra={"model": self.model.keys()}
        )
        results = {}
        for name, model in self.model.items():
            self.current_model = model
            self.logger.info("Asking LLM .... ", extra={"model": name})
            try:
                results = self.invoke_chain(query=query, model_name=name, parser=parser)
                return results
            except (OutputParserException, error_wrappers.ValidationError) as e:
                self.logger.exception(
                    "llm say : %s", e.llm_output, extra={"model": name}
                )
                self.logger.exception(
                    "Observation : %s", e.observation, extra={"model": name}
                )
        return {}

    @timed
    def invoke_chain(self, query, model_name, parser):
        """
        Invokes the chain for the given model with the provided question and returns the result.

        This method attempts to invoke the chain for the specified model with the given question.
        If an `OutputParserException` is raised, it retries up to `max_retry` times. If all
        retries fail, it raises the exception.

        Args:
            query: The question to ask about the document.
            model_name: The name of the model to use for the chain invocation.
            parser (optional): The output parser to use during the invocation. Defaults to the provided parser in the create_chain method.

        Returns:
            The result of invoking the chain with the given question and model.
        """
        max_retry = 5
        curr_retry = 0
        while curr_retry < max_retry:
            try:
                self.logger.debug(
                    "Full prompt : %s",
                    str(self.chain[model_name]),
                    extra={"model": model_name},
                )
                result = self.chain[model_name].invoke(query)
                # result = self.chain[model_name].invoke(
                #     {
                #         "format_instructions": parser.get_format_instructions(),
                #         "question": query,
                #     }, 
                # )
                self.logger.debug(
                    "LLM say correct result : %s", result, extra={"model": model_name}
                )
                return result
            except OutputParserException as e:
                self.logger.exception(
                    "llm say : %s", e.llm_output, extra={"model": model_name}
                )
                self.logger.exception(
                    "Observation : %s", e.observation, extra={"model": model_name}
                )
                curr_retry += 1
                if curr_retry >= max_retry:
                    raise
        return {}
