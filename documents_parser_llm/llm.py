
from langchain_community.chat_models.ollama import ChatOllama

from langchain_core.prompts import ChatPromptTemplate

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

    default_prompt = ChatPromptTemplate

    def __init__(self, config=AppConfig):
        if config.llm.type.lower() == "ollama":
            self.model = ChatOllama(
                base_url=f"{config.llm.url}:{config.llm.port}",
                format="json",
                model=config.llm.model,
                temperature=config.llm.temp
            )
        else:
            raise ValueError(f"{config.llm.type} not yet supported")

    def make_default_prompt(self, prompt = None):
        """
        This method sets the default prompt for the language model.

        Args:
            prompt: A list of messages to use for the prompt.
        """
        if prompt is None:
            prompt = []
        self.default_prompt = ChatPromptTemplate.from_messages(prompt)