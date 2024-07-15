
from langchain_community.chat_models.ollama import ChatOllama

from langchain_core.prompts import ChatPromptTemplate, HumanMessagePromptTemplate, PromptTemplate
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
                                              model=config.llm.embeddings)
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

    def create_chain(self, context, parser = JsonOutputParser()):
        self.chain = (
            {"context": context, "question": RunnablePassthrough()}
            | self.default_prompt
            | self.model
            | parser
        )

    def invoke_chain(self, query, parser = JsonOutputParser() ):
        """
        Asks a question about the document and returns the answer.

        Args:
            query: The question to ask about the document.

        Returns:
            The answer to the question.
        """
     

        prompt = HumanMessagePromptTemplate(
            prompt=PromptTemplate(
                template=query + " \n {format_instructions} \n ",
                input_variables=[],
                partial_variables={"format_instructions": parser.get_format_instructions()}
            )
        )
        print( parser.get_format_instructions())
        print(f" -- PROMPT : {prompt.format().content}")
        print(f" ---- {self.chain.get_prompts()}")
        return self.chain.invoke(prompt.format().content)
