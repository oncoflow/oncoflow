import os
from typing import List, Any, Optional
import openai
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from src.application.config import AppConfig
from src.infrastructure.llm.base import LLMConnect


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
        # Check if the API endpoint is official OpenAI or a local/custom OpenAI-compatible layer (like Ollama/vLLM)
        is_openai_official = True
        base_url = (
            getattr(self, "openai_api_base", None)
            or getattr(self, "base_url", None)
            or ""
        )
        base_url_str = str(base_url)

        api_key_obj = getattr(self, "openai_api_key", None) or getattr(
            self, "api_key", None
        )
        api_key_str = ""
        if api_key_obj is not None:
            if hasattr(api_key_obj, "get_secret_value"):
                api_key_str = api_key_obj.get_secret_value()
            else:
                api_key_str = str(api_key_obj)

        if "api.openai.com" not in base_url_str and (
            base_url_str
            or api_key_str == "ollama"
            or "localhost" in base_url_str
            or "127.0.0.1" in base_url_str
        ):
            is_openai_official = False

        if not is_openai_official:
            # For non-official OpenAI backends (Ollama, vLLM, etc.):
            # 1. Strip response_format if present to prevent conflicting with tool calling in Ollama
            if "response_format" in self.model_kwargs:
                self.model_kwargs = self.model_kwargs.copy()
                self.model_kwargs.pop("response_format", None)
            kwargs.pop("response_format", None)

            # 2. Call standard bind_tools without forcing strict=True (which local endpoints don't support)
            return super().bind_tools(tools, strict=False, **kwargs)

        # Force strict=True to prevent "ValueError: Only strict function tools can be auto-parsed"
        # which is required by OpenAI structured output completions beta parse engine.
        # Also remove conflicting response_format if tools are being bound.
        if "response_format" in self.model_kwargs:
            self.model_kwargs = self.model_kwargs.copy()
            self.model_kwargs.pop("response_format", None)

        # Natively pass response_format to bind_tools for OpenAI Structured Outputs
        output_schema = self.__dict__.get("_output_schema", None)
        if output_schema is not None and "response_format" not in kwargs:
            kwargs["response_format"] = output_schema

        return super().bind_tools(tools, strict=True, **kwargs)


class OpenAIConnect(LLMConnect):
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

    def chat(self, model, output=None, temperature=None, tools=[], reasoning=True):
        # We set JSON mode if output is specified (matching the Ollama behavior)
        # However, if tools are provided, we must not force JSON mode to avoid conflicts with tool calling.
        model_kwargs = {}
        if not tools and output is not None:
            model_kwargs["response_format"] = {"type": "json_object"}

        model_instance = StrictChatOpenAI(
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
        # Save output schema for use in bind_tools bypassing Pydantic setattr constraints
        model_instance.__dict__["_output_schema"] = output

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
