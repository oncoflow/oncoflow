
from langchain_community.chat_models.ollama import ChatOllama
from langchain_community.embeddings import OllamaEmbeddings

from langchain_core.prompts import ChatPromptTemplate, HumanMessagePromptTemplate, PromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.exceptions import OutputParserException

from langchain.schema.runnable import RunnablePassthrough

import ollama

from config import AppConfig


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

        self.default_prompt = ChatPromptTemplate

        if config.llm.type.lower() == "ollama":
            if embeddings:
                print('EMBEDDING')
                self.embeddings = OllamaEmbeddings(base_url=f"{config.llm.url}:{config.llm.port}",
                                                   model=config.llm.embeddings)
                list_models  = [config.llm.embeddings]
            else:
                if models is None or not models:
                    list_models = config.llm.models.split(",")
                else:
                    list_models = models

                if list_models == "all":
                    ocl = ollama.Client(
                        host=f"{config.llm.url}:{config.llm.port}")
                    list_models = [m["name"] for m in ocl.list()["models"] if m["name"].split(":")[0] not in [
                        "mxbai-embed-large", "nomic-embed-text", "all-minilm"]]

                for model in list_models:
                    self.model[model] = ChatOllama(
                        base_url=f"{config.llm.url}:{config.llm.port}",
                        format="json",
                        model=model,
                        temperature=config.llm.temp
                    )

        else:
            raise ValueError(f"{config.llm.type} not yet supported")
        
        
        self.logger = config.set_logger("llm", default_context={
            "llm_type": config.llm.type.lower(),
            "list_models": list_models},  additional_context=["model"])

        self.logger.debug("Class llm succesfully init", extra={"model": ""})

    def make_default_prompt(self, prompt=None):
        """
        This method sets the default prompt for the language model.

        Args:
            prompt: A list of messages to use for the prompt.
        """
        if prompt is None:
            prompt = []
        self.default_prompt = ChatPromptTemplate.from_messages(prompt)
        self.logger.debug("Default prompt = %s", self.default_prompt, extra={
                          "model": self.model.keys()})

    def create_chain(self, context, additionnal_context=None, parser=JsonOutputParser()):
        base_chain = {"context": context, "question": RunnablePassthrough()}
        # ic(base_chain)
        if additionnal_context is not None:
            for context in additionnal_context:
                base_chain |= {context["name"]: context["retriever"]}
                print("ADDITIONNAL CONTEXT")
            # ic(base_chain)
        for name, model in self.model.items():
            self.chain[name] = (
                base_chain
                | self.default_prompt
                | model
                | parser
            )
            self.logger.debug(
                "Set chain : %s", self.chain[name].get_prompts(), extra={"model": name})

    def invoke_chain(self, query, parser=JsonOutputParser()):
        """
        Asks a question about the document and returns the answer.

        Args:
            query: The question to ask about the document.

        Returns:
            The answer to the question.
        """

        prompt = HumanMessagePromptTemplate(
            prompt=PromptTemplate(
                template="Answer the user question" + "\n {format_instructions}\n question: " + query,
                input_variables=[],
                partial_variables={
                    "format_instructions": parser.get_format_instructions()}
            )
        )
        #print(f" -- PROMPT : {prompt.format().content}")
        results = {}
        for name, model in self.model.items():
            print(f"Processing {name} ...")
            #print(f" ---- {self.chain[name].get_prompts()}")
            try:
                results[name] = self.chain[name].invoke(
                    prompt.format().content)
            except OutputParserException as e:
                self.logger.exception(
                    "llm say : %s", e.llm_output, extra={"model": name})
                self.logger.exception(
                    "Observation : %s", e.observation, extra={"model": name})
        return results
