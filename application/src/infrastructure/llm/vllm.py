from typing import List, Optional
import openai
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_ollama import OllamaEmbeddings
from src.application.config import AppConfig
from src.infrastructure.llm.base import (
    LLMConfigurationError,
    LLMConnect,
    LLMConnectionError,
    build_base_url,
    retry_connection,
)


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

        # Build base URL (url[:port][/uri]).
        self.base_url = build_base_url(
            config.llm.url, config.llm.port, self.config.llm.uri
        )
        if not self.base_url:
            raise LLMConfigurationError(
                "vLLM backend requires an explicit base URL (APP_CONFIGLLM_URL)."
            )

        self.logger = config.set_logger("vllm", default_context={"host": self.base_url})

        # Get API key resolved natively via pydantic-settings (APP_CONFIGLLM_API_KEY / OPENAI_API_KEY)
        self.api_key = config.llm.api_key if config.llm.api_key else "vllm-mock-key"

        # Initialize the official openai client for utility calls like listing models and connection testing
        self.client = openai.OpenAI(
            base_url=self.base_url,
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

    def chat(
        self,
        model,
        output=None,
        temperature=None,
        tools=None,
        reasoning=True,
        reasoning_budget=None,
    ):
        tools = tools or []
        model_kwargs = {}
        if output is not None and not tools:
            model_kwargs["response_format"] = {"type": "json_object"}

        chat_kwargs = {
            "base_url": self.base_url,
            "api_key": self.api_key,
            "model": model,
            "reasoning": {"effort": "medium"} if reasoning else None,
            "temperature": (
                temperature if temperature is not None else self.config.llm.temp
            ),
            "model_kwargs": model_kwargs,
            "streaming": True,
        }
        if reasoning and reasoning_budget is not None:
            chat_kwargs["extra_body"] = {"thinking_budget_tokens": reasoning_budget}

        model_instance = ChatOpenAI(**chat_kwargs)

        if tools:
            model_instance = model_instance.bind_tools(tools)

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
        def _probe():
            # We list models as a fast connection test
            self.client.models.list()

        try:
            retry_connection(
                _probe,
                self.logger,
                retry_on=(openai.APIConnectionError, openai.APITimeoutError),
                backend="vLLM",
            )
        except LLMConnectionError:
            raise
        except Exception as e:
            self.logger.error(f"vLLM Connection error: {e}")
            raise LLMConnectionError(f"vLLM backend error: {e}") from e
