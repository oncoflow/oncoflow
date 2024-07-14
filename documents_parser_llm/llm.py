
from langchain_community.chat_models.ollama import ChatOllama

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser

from langchain.schema.runnable import RunnablePassthrough
from langchain.schema.output_parser import StrOutputParser

from langchain_community.embeddings import OllamaEmbeddings

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
    model = None
    chain = None

    default_prompt = ChatPromptTemplate

    def __init__(self, config=AppConfig, embeddings=False):
        if config.llm.type.lower() == "ollama":
            if embeddings:
                self.model = OllamaEmbeddings(base_url=f"{config.llm.url}:{config.llm.port}",
                                              model="all-minilm")
            else:
                self.model = ChatOllama(
                    base_url=f"{config.llm.url}:{config.llm.port}",
                    format="json",
                    model=config.llm.model,
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

    def create_chain(self, context):
        self.chain = (
            {"context": context, "question": RunnablePassthrough()}
            | self.default_prompt
            | self.model
            | JsonOutputParser()
        )

    def invoke_chain(self, query):
        """
        Asks a question about the document and returns the answer.

        Args:
            query: The question to ask about the document.

        Returns:
            The answer to the question.
        """
        print(f" -- {query}")
        print(f" ---- {self.chain.get_prompts()}")
        return self.chain.invoke(query)
