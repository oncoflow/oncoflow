import os
from typing import List, Optional
import openai
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_ollama import OllamaEmbeddings
from src.application.config import AppConfig
from src.infrastructure.llm.base import LLMConnect


class VllmCompatibleEmbeddings(OpenAIEmbeddings):
    def _get_len_safe_embeddings(
        self,
        texts: List[str],
        *,
        engine: str,
        chunk_size: Optional[int] = None,
        **kwargs,
    ) -> List[List[float]]:
        # Bypass tokenization and chunking - send raw strings directly to the API
        # This fixes compatibility with local OpenAI-compatible embedding servers (like vLLM)
        # that only accept standard string lists as input.
        model_name = self.model if self.model else engine
        params = {"model": model_name} | kwargs
        response = self.client.create(input=texts, **params)
        if not isinstance(response, dict):
            response = response.model_dump()
        return [r["embedding"] for r in response["data"]]


class VllmConnect(LLMConnect):
    def __init__(self, config: AppConfig) -> None:
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

        self.logger = config.set_logger("vllm", default_context={"host": self.base_url})

        # Get API key from config, falling back to environment variable, then a mock key
        self.api_key = (
            config.llm.api_key
            if config.llm.api_key
            else os.environ.get("OPENAI_API_KEY", "vllm-mock-key")
        )

        # Initialize the official openai client for utility calls like listing models and connection testing
        self.client = openai.OpenAI(
            base_url=self.base_url if self.base_url else None,
            api_key=self.api_key,
        )
        self.test_connection()

        # In Oncoflow's local-first architecture, the vLLM engine on port 8080 is
        # dedicated solely to text generation to maximize performance and conserve GPU VRAM.
        # Embedding models are offloaded to the local Ollama instance running on port 11434.
        import urllib.parse

        ollama_url = config.llm.url
        if ":11434" not in ollama_url:
            parsed = urllib.parse.urlparse(ollama_url)
            if parsed.netloc:
                host = parsed.netloc.split(":")[0]
                ollama_url = f"{parsed.scheme}://{host}:11434"
            else:
                host = ollama_url.split(":")[0]
                ollama_url = f"{host}:11434"

        self.logger.info(
            f"Routing embeddings to local Ollama on {ollama_url} (model: {config.llm.embeddings})"
        )
        self.embedding = OllamaEmbeddings(
            base_url=ollama_url,
            model=config.llm.embeddings,
        )

        self.logger.info("Successfully connected to vLLM server")

    def chat(self, model, output=None, temperature=None, tools=[], reasoning=True):
        model_kwargs = {}
        if output is not None and not tools:
            model_kwargs["response_format"] = {"type": "json_object"}

        model_instance = ChatOpenAI(
            base_url=self.base_url if self.base_url else None,
            api_key=self.api_key,
            model=model,
            tools=tools,
            reasoning={"effort": "medium"} if reasoning else None,
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
            self.logger.error(f"Failed to list vLLM models: {e}")
            # Return a default model list from config as fallback
            return [self.config.llm.models]

    def test_connection(self):
        try:
            # We list models as a fast connection test
            self.client.models.list()
        except Exception as e:
            self.logger.error(f"vLLM Connection error: {e}")
            exit(254)
