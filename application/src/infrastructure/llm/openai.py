import os
from typing import List, Any, Optional
import openai
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from src.application.config import AppConfig


class OllamaCompatibleOpenAIEmbeddings(OpenAIEmbeddings):
    def _get_len_safe_embeddings(
        self,
        texts: List[str],
        *,
        engine: str,
        chunk_size: Optional[int] = None,
        **kwargs,
    ) -> List[List[float]]:
        # Bypass tokenization and chunking - send raw strings directly to the API
        # This fixes compatibility with local OpenAI-compatible embedding servers (like Ollama)
        # that only accept standard string lists as input.
        model_name = self.model if self.model else engine
        params = {"model": model_name} | kwargs
        response = self.client.create(input=texts, **params)
        if not isinstance(response, dict):
            response = response.model_dump()
        return [r["embedding"] for r in response["data"]]


class StrictChatOpenAI(ChatOpenAI):
    def bind_tools(
        self, tools: Any, *, strict: Optional[bool] = None, **kwargs: Any
    ) -> Any:
        # Force strict=True to prevent "ValueError: Only strict function tools can be auto-parsed"
        # which is required by OpenAI structured output completions beta parse engine.
        return super().bind_tools(tools, strict=True, **kwargs)


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

        # Avoid double slashes in base URL
        self.base_url = self.base_url.rstrip("/")
        uri = self.config.llm.uri.lstrip("/")
        if uri:
            self.base_url = f"{self.base_url}/{uri}"

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
        self.client = openai.OpenAI(
            base_url=self.base_url if self.base_url else None,
            api_key=self.api_key,
        )
        self.test_connection()

        # Initialize compatible embeddings
        self.embedding = OllamaCompatibleOpenAIEmbeddings(
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

        model_instance = StrictChatOpenAI(
            base_url=self.base_url if self.base_url else None,
            api_key=self.api_key,
            model=model,
            tools=tools,
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
