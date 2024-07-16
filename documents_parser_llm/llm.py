
from langchain_community.chat_models.ollama import ChatOllama
from langchain_community.embeddings import OllamaEmbeddings

from langchain_core.prompts import ChatPromptTemplate, HumanMessagePromptTemplate, PromptTemplate
from langchain_core.output_parsers import JsonOutputParser

from langchain.schema.runnable import RunnablePassthrough
from langchain.schema.output_parser import StrOutputParser

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
    model = {}
    chain = {}
    embeddings = None

    default_prompt = ChatPromptTemplate

    def __init__(self, config=AppConfig, embeddings=False):
        if config.llm.type.lower() == "ollama":
            if embeddings:
                self.embeddings = OllamaEmbeddings(base_url=f"{config.llm.url}:{config.llm.port}",
                                                   model=config.llm.embeddings)
            else:
                if config.llm.models == "all":
                    ocl = ollama.Client(
                        host=f"{config.llm.url}:{config.llm.port}")
                    models = [m["name"] for m in ocl.list()["models"] if m["name"].split(":")[0] not in [
                        "mxbai-embed-large", "nomic-embed-text", "all-minilm"]]
                else:
                    models = config.llm.models.split(",")
                for model in models:
                    self.model[model] = ChatOllama(
                        base_url=f"{config.llm.url}:{config.llm.port}",
                        format="json",
                        model=model,
                        temperature=config.llm.temp
                    )
        else:
            raise ValueError(f"{config.llm.type} not yet supported")

    def make_default_prompt(self, prompt=None):
        """
        This method sets the default prompt for the language model.

        Args:
            prompt: A list of messages to use for the prompt.
        """
        if prompt is None:
            prompt = []
        self.default_prompt = ChatPromptTemplate.from_messages(prompt)

    def create_chain(self, context, additionnal_context = None, parser=JsonOutputParser()):
        base_chain = {"context": context, "question": RunnablePassthrough()}
        if additionnal_context is not None:
            for context in additionnal_context:
                base_chain |= {context["name"]: context["retriever"]}
        print(base_chain)
        for name, model in self.model.items():
            self.chain[name] = (
                base_chain
                | self.default_prompt
                | model
                | parser
            )

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
                template=query + "\n {format_instructions}",
                input_variables=[],
                partial_variables={
                    "format_instructions": parser.get_format_instructions()}
            )
        )
        #print(f" -- PROMPT : {prompt.format().content}")
        results = {}
        for name, model in self.model.items():
            print(f"Processing {name} ...")
            # print(f" ---- {self.chain[name].get_prompts()}")
            results[name] = self.chain[name].invoke(prompt.format().content)
        return results
