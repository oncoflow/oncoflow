
from langchain_community.chat_models.ollama import ChatOllama

from langchain_core.prompts import ChatPromptTemplate

from config import AppConfig


class llm:
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

    def makeDefaultPrompt(self, prompt = []):
        self.default_prompt = ChatPromptTemplate.from_messages(prompt)