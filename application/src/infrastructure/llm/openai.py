import os
from typing import List, Any
import openai
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from src.application.config import AppConfig


class OpenAIConnect:
    def __init__(self, config=AppConfig) -> None:
        self.config = config
        
        # Build base URL. If port is empty or none, just use url.
        url = config.llm.url
        port = config.llm.port
        if port and port.strip():
            if f":{port}" not in url:
                self.base_url = f"{url}:{port}"
            else:
                self.base_url = url
        else:
            self.base_url = url

        self.logger = config.set_logger(
            "openai", default_context={"host": self.base_url}
        )

        # Get API key from config, falling back to environment variable, then a mock key
        self.api_key = (
            config.llm.api_key
            if config.llm.api_key
            else os.environ.get("OPENAI_API_KEY", "mock-key")
        )

        # Initialize the official openai client for utility calls like listing models and connection testing
        # If base_url looks like default loopback without specific OpenAI path, or is empty,
        # we check if it is public OpenAI and let it default if base_url is not customized.
        self.client = openai.OpenAI(
            base_url=self.base_url if self.base_url else None,
            api_key=self.api_key,
        )
        self.test_connection()
        
        # Initialize embeddings
        self.embedding = OpenAIEmbeddings(
            base_url=self.base_url if self.base_url else None,
            api_key=self.api_key,
            model=config.llm.embeddings,
        )

        self.logger.info("Succesfully connected")

    def chat(self, model, output=None, temperature=None, tools=[]):
        # We set JSON mode if output is specified (matching the Ollama behavior)
        model_kwargs = {}
        if output is not None:
            model_kwargs["response_format"] = {"type": "json_object"}

        model_instance = ChatOpenAI(
            base_url=self.base_url if self.base_url else None,
            api_key=self.api_key,
            model=model,
            temperature=(
                temperature if temperature is not None else self.config.llm.temp
            ),
            model_kwargs=model_kwargs,
        )

        return model_instance

    def get_models(self):
        try:
            models_list = self.client.models.list()
            return [m.id for m in models_list.data]
        except Exception as e:
            self.logger.error(f"Failed to list models: {e}")
            # Return a default model list from config as fallback
            return [self.config.llm.models]

    def test_connection(self):
        try:
            # We list models as a fast connection test
            self.client.models.list()
        except Exception as e:
            self.logger.error(f"Connection error : {e}")
            exit(254)
