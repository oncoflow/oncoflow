from langchain_community.chat_models.ollama import ChatOllama
from langchain_community.embeddings import OllamaEmbeddings

import ollama

from httpx import ConnectError

from src.application.config import AppConfig


class OllamaConnect:

    def __init__(self, config=AppConfig) -> None:
        self.config = config
        self.logger = config.set_logger(
            "ollama", default_context={"host": config.llm.url, "port": config.llm.port}
        )
        self.client = ollama.Client(host=f"{config.llm.url}:{config.llm.port}")
        self.test_connection()
        self.embedding = self.Embedding(
            base_url=f"{config.llm.url}:{config.llm.port}",
            model=config.llm.embeddings,
        )
        self.logger.info("Succesfully connected")

    def chat(self, model, temperature=None):
        return ChatOllama(
            base_url=f"{self.config.llm.url}:{self.config.llm.port}",
            format="json",
            model=model,
            temperature=(
                temperature if temperature is not None else self.config.llm.temp
            ),
        )

    def get_models(self):
        return [
            m["name"]
            for m in self.client.list()["models"]
            if m["name"].split(":")[0] not in ["all-minilm"]
        ]

    def test_connection(self):
        try:
            self.client.list()
        except (ollama.ResponseError, ConnectError) as e:
            self.logger.error(f"Connection error : {e.args}")
            exit(254)

    class Embedding(OllamaEmbeddings):
        """
        A subclass of OllamaEmbeddings that defines methods for embedding documents.

        This class is a thin wrapper around the Ollama embeddings functionality,
        providing convenience methods and custom docstrings.
        """

        def _embed_documents(self, texts):
            return super().embed_documents(texts)

        def __call__(self, input):
            return self._embed_documents(input)
