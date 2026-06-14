import os
from typing import List, Any
import httpx


from langchain_litellm import ChatLiteLLM
from langchain_litellm import LiteLLMEmbeddings

from src.application.config import AppConfig
from src.infrastructure.llm.base import LLMConnect


class LiteLLMConnect(LLMConnect):
    """
    LiteLLM connection client for Chat and Embeddings using LangChain.
    """

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
            "litellm", default_context={"host": self.base_url}
        )

        # Get API key from config, falling back to environment variable, then a mock key
        self.api_key = (
            config.llm.api_key
            if config.llm.api_key
            else os.environ.get("LITELLM_API_KEY", "mock-key")
        )

        self.test_connection()

        # Initialize LiteLLM embeddings pointing to LiteLLM Proxy
        self.embedding = LiteLLMEmbeddings(
            api_base=self.base_url,
            api_key=self.api_key,
            model=config.llm.embeddings,
        )

        self.logger.info("Succesfully connected to LiteLLM proxy")

    def chat(
        self,
        model: str,
        output: Any = None,
        temperature: float | None = None,
        tools: List[Any] = [],
        reasoning: bool = False,
    ) -> Any:
        # If temperature is not provided, fallback to the config value
        temp = temperature if temperature is not None else self.config.llm.temp

        model_kwargs = {}
        if not tools and output is not None:
            model_kwargs["response_format"] = {"type": "json_object"}
        if reasoning:
            model_kwargs["reasoning"] = {"effort": "low"}

        model_instance = ChatLiteLLM(
            api_base=self.base_url,
            api_key=self.api_key,
            model=model,
            temperature=temp,
            model_kwargs=model_kwargs,
            reasoning={"effort": "low"} if reasoning else None,
            streaming=True,
        )
        # Save output schema for use in bind_tools bypassing Pydantic setattr constraints
        model_instance.__dict__["_output_schema"] = output

        return model_instance

    def get_models(self) -> List[str]:
        try:
            headers = {"Authorization": f"Bearer {self.api_key}"}
            # Query /models endpoint of LiteLLM proxy
            response = httpx.get(
                f"{self.base_url}/models", headers=headers, timeout=5.0
            )
            if response.status_code == 200:
                data = response.json()
                return [m["id"] for m in data.get("data", [])]
        except Exception as e:
            self.logger.error(f"Failed to list models: {e}")
        # Return fallback model list from configuration
        return [self.config.llm.models]

    def test_connection(self) -> None:
        try:
            # We list models (via /models) as a connection check
            headers = {"Authorization": f"Bearer {self.api_key}"}
            response = httpx.get(
                f"{self.base_url}/models", headers=headers, timeout=5.0
            )
            if response.status_code != 200:
                self.logger.warning(
                    f"LiteLLM proxy /models returned status {response.status_code}"
                )
        except Exception as e:
            self.logger.error(f"Connection error to LiteLLM proxy: {e}")
            exit(254)
