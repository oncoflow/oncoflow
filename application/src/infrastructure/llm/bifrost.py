"""
Bifrost LLM gateway client.

Bifrost (https://github.com/maximhq/bifrost) exposes an OpenAI-compatible API
(``/v1/chat/completions``, ``/v1/embeddings``, ``/v1/models``) in front of
several providers. Models are addressed as ``<provider>/<model>``
(e.g. ``ollama/qwen3:14b``, ``ollama/bge-m3``).

Patient data privacy: Bifrost must only route Oncoflow traffic to providers
hosted locally (Ollama, vLLM, llama.cpp...). Never configure a public cloud
provider on the virtual key used by Oncoflow.
"""

import os
from typing import Any, List

import openai

from src.application.config import AppConfig
from src.infrastructure.llm.base import LLMConnect
from src.infrastructure.llm.openai import (
    OllamaCompatibleOpenAIEmbeddings,
    StrictChatOpenAI,
)


class BifrostConnect(LLMConnect):
    """
    Bifrost gateway connection client for Chat and Embeddings using LangChain.
    """

    def __init__(self, config: AppConfig) -> None:
        self.config = config

        # Build base URL. If port is empty or none, just use url.
        url = config.llm.url
        port = config.llm.port
        if port and port.strip() and f":{port}" not in url:
            self.base_url = f"{url}:{port}"
        else:
            self.base_url = url

        # Avoid double slashes in base URL, Bifrost serves the OpenAI API under /v1
        self.base_url = self.base_url.rstrip("/")
        uri = self.config.llm.uri.strip("/") or "v1"
        self.base_url = f"{self.base_url}/{uri}"

        self.logger = config.set_logger(
            "bifrost", default_context={"host": self.base_url}
        )

        # Get API key from config, falling back to environment variable, then a dummy key
        # (Bifrost ignores it when governance is disabled).
        self.api_key = (
            config.llm.api_key
            if config.llm.api_key
            else os.environ.get("BIFROST_API_KEY", "bifrost")
        )

        # Bifrost governance: virtual keys are sent with the x-bf-vk header
        virtual_key = getattr(config.llm, "virtual_key", None)
        self.default_headers = (
            {"x-bf-vk": virtual_key}
            if isinstance(virtual_key, str) and virtual_key
            else None
        )

        # Official openai client for utility calls (listing models, connection testing)
        self.client = openai.OpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
            default_headers=self.default_headers,
        )
        self.test_connection()

        self.embedding = OllamaCompatibleOpenAIEmbeddings(
            base_url=self.base_url,
            api_key=self.api_key,
            model=config.llm.embeddings,
            default_headers=self.default_headers,
        )

        self.logger.info("Succesfully connected to Bifrost gateway")

    def chat(
        self,
        model: str,
        output: Any = None,
        temperature: float | None = None,
        tools: List[Any] = [],
        reasoning: bool = True,
        reasoning_budget: int | None = None,
    ) -> Any:
        # JSON mode only when no tools are bound, to avoid conflicts with tool calling
        model_kwargs = {}
        if not tools and output is not None:
            model_kwargs["response_format"] = {"type": "json_object"}

        chat_kwargs = {
            "base_url": self.base_url,
            "api_key": self.api_key,
            "default_headers": self.default_headers,
            "model": model,
            # Stay on /v1/chat/completions: the Responses API is not available
            # for every provider routed by Bifrost (e.g. Ollama).
            "use_responses_api": False,
            "reasoning_effort": "low" if reasoning else None,
            "temperature": (
                temperature if temperature is not None else self.config.llm.temp
            ),
            "model_kwargs": model_kwargs,
            "streaming": True,
        }
        if reasoning and reasoning_budget is not None:
            chat_kwargs["extra_body"] = {"thinking_budget_tokens": reasoning_budget}

        model_instance = StrictChatOpenAI(**chat_kwargs)
        # Save output schema for use in bind_tools bypassing Pydantic setattr constraints
        model_instance.__dict__["_output_schema"] = output

        if tools:
            model_instance = model_instance.bind_tools(tools)

        return model_instance

    def get_models(self) -> List[str]:
        try:
            return [m.id for m in self.client.models.list().data]
        except Exception as e:
            self.logger.error(f"Failed to list models: {e}")
            # Return fallback model list from configuration
            return [self.config.llm.models]

    def test_connection(self) -> None:
        try:
            self.client.models.list()
        except Exception as e:
            self.logger.error(f"Connection error to Bifrost gateway: {e}")
            exit(254)
