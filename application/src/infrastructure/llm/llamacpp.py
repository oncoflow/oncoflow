import os
import time
from typing import List, Any, Optional
import httpx

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from src.application.config import AppConfig
from src.infrastructure.llm.base import LLMConnect


class LlamaCppCompatibleEmbeddings(OpenAIEmbeddings):
    """
    OpenAI-compatible embeddings adapter for llama.cpp server.

    Bypasses LangChain's default tiktoken-based tokenization and chunking,
    which is incompatible with llama.cpp's /v1/embeddings endpoint.
    Sends raw text strings directly to the API.
    """

    def _get_len_safe_embeddings(
        self,
        texts: List[str],
        *,
        engine: str,
        chunk_size: Optional[int] = None,
        **kwargs,
    ) -> List[List[float]]:
        model_name = self.model if self.model else engine
        params = {"model": model_name} | kwargs
        response = self.client.create(input=texts, **params)
        if not isinstance(response, dict):
            response = response.model_dump()
        return [r["embedding"] for r in response["data"]]


class LlamaCppChatOpenAI(ChatOpenAI):
    """
    OpenAI-compatible chat model for llama.cpp server that preserves reasoning_content
    tokens both during streaming chunks and in final generation messages.
    """

    def _convert_chunk_to_generation_chunk(
        self,
        chunk: dict,
        default_chunk_class: type,
        base_generation_info: dict | None,
    ):
        gen_chunk = super()._convert_chunk_to_generation_chunk(
            chunk, default_chunk_class, base_generation_info
        )
        if gen_chunk and gen_chunk.message:
            choices = chunk.get("choices", []) or chunk.get("chunk", {}).get(
                "choices", []
            )
            if choices:
                delta = choices[0].get("delta", {})
                reasoning = delta.get("reasoning_content") or delta.get("reasoning")
                if reasoning:
                    gen_chunk.message.additional_kwargs["reasoning_content"] = reasoning
                    setattr(gen_chunk.message, "reasoning_content", reasoning)
        return gen_chunk

    def _create_chat_result(
        self,
        response: dict | Any,
        generation_info: dict | None = None,
    ):
        chat_result = super()._create_chat_result(response, generation_info)
        response_dict = (
            response if isinstance(response, dict) else response.model_dump()
        )
        choices = response_dict.get("choices", [])
        for i, gen in enumerate(chat_result.generations):
            if i < len(choices):
                msg_data = choices[i].get("message", {})
                reasoning = msg_data.get("reasoning_content") or msg_data.get(
                    "reasoning"
                )
                if reasoning:
                    gen.message.additional_kwargs["reasoning_content"] = reasoning
                    setattr(gen.message, "reasoning_content", reasoning)
        return chat_result


class LlamaCppConnect(LLMConnect):
    """
    Direct connection client for llama.cpp server(s) using their OpenAI-compatible API.

    This client connects directly to llama.cpp server instances, bypassing
    intermediate proxies like LiteLLM. It expects two separate servers:
      - A chat/completion server (config port, e.g. 8081)
      - An embeddings server (config embeddings_port, e.g. 8082)

    Both servers expose OpenAI-compatible REST APIs (/v1/chat/completions, /v1/embeddings).

    Uses langchain-openai's ChatOpenAI and OpenAIEmbeddings as recommended by
    the official LangChain documentation for llama.cpp in server mode.
    """

    def __init__(self, config: AppConfig) -> None:
        self.config = config

        # Build base URL for the chat server.
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
            "llamacpp", default_context={"host": self.base_url}
        )

        # llama.cpp server does not require an API key, but the OpenAI client expects one
        self.api_key = (
            config.llm.api_key
            if config.llm.api_key
            else os.environ.get("LLAMACPP_API_KEY", "not-needed")
        )

        self.test_connection()

        # Build the embeddings server URL from config.llm.embeddings_port
        embeddings_url = self._build_embeddings_url()

        self.embedding = LlamaCppCompatibleEmbeddings(
            base_url=embeddings_url,
            api_key=self.api_key,
            model=config.llm.embeddings,
        )

        self.logger.info("Successfully connected to llama.cpp server")

    def _build_embeddings_url(self) -> str:
        """
        Build the embeddings server URL from config.

        Uses config.llm.embeddings_port to construct the URL for the
        dedicated embeddings llama.cpp server instance.
        """
        url = self.config.llm.url
        embeddings_port = self.config.llm.embeddings_port

        if embeddings_port and embeddings_port.strip():
            # Check if port is already in the URL
            port = self.config.llm.port
            if port and f":{port}" in url:
                embeddings_base = url.replace(f":{port}", f":{embeddings_port}")
            else:
                embeddings_base = f"{url}:{embeddings_port}"
        else:
            embeddings_base = url

        embeddings_base = embeddings_base.rstrip("/")
        uri = self.config.llm.uri.lstrip("/")
        if uri:
            embeddings_base = f"{embeddings_base}/{uri}"

        return embeddings_base

    def chat(
        self,
        model: str,
        output: Any = None,
        temperature: float | None = None,
        tools: List[Any] = [],
        reasoning: bool = True,
        reasoning_budget: int | None = None,
    ) -> Any:
        # Set JSON mode if output is specified and no tools are provided.
        # When tools are present, JSON mode conflicts with tool calling.
        model_kwargs = {}
        if not tools and output is not None:
            model_kwargs["response_format"] = {"type": "json_object"}

        chat_kwargs = {
            "base_url": self.base_url if self.base_url else None,
            "api_key": self.api_key,
            "model": model,
            "temperature": (
                temperature if temperature is not None else self.config.llm.temp
            ),
            "max_tokens": 4096,
            "model_kwargs": model_kwargs,
            "streaming": True,
        }
        if reasoning and reasoning_budget is not None:
            chat_kwargs["extra_body"] = {"thinking_budget_tokens": reasoning_budget}

        model_instance = LlamaCppChatOpenAI(**chat_kwargs)

        if tools:
            model_instance = model_instance.bind_tools(tools)

        return model_instance

    def get_models(self) -> List[str]:
        try:
            headers = {"Authorization": f"Bearer {self.api_key}"}
            response = httpx.get(
                f"{self.base_url}/models", headers=headers, timeout=30.0
            )
            if response.status_code == 200:
                data = response.json()
                return [m["id"] for m in data.get("data", [])]
        except Exception as e:
            self.logger.error(f"Failed to list llama.cpp models: {e}")
        # Return fallback model list from configuration
        return [self.config.llm.models]

    def test_connection(
        self,
        max_retries: int = 15,
        retry_delay: float = 3.0,
        timeout: float = 10.0,
    ) -> None:
        """
        Verify that the llama.cpp server is reachable and ready.
        Supports cold starts (e.g. Cloud Run, model loading) by retrying on timeouts and connect errors.
        """
        health_url = self.base_url.rsplit("/v1", 1)[0]
        headers = {"Authorization": f"Bearer {self.api_key}"}

        for attempt in range(1, max_retries + 1):
            try:
                # llama.cpp exposes a /health endpoint for readiness checks
                response = httpx.get(f"{health_url}/health", timeout=timeout)
                if response.status_code == 200:
                    return
                # Fall back to listing models if /health is not available
                response = httpx.get(
                    f"{self.base_url}/models", headers=headers, timeout=timeout
                )
                if response.status_code == 200:
                    return
                self.logger.warning(
                    f"llama.cpp server returned status {response.status_code} (attempt {attempt}/{max_retries})"
                )
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                if attempt < max_retries:
                    self.logger.info(
                        f"Waiting for llama.cpp server to respond ({e})... "
                        f"(attempt {attempt}/{max_retries}, retrying in {retry_delay}s)"
                    )
                    time.sleep(retry_delay)
                else:
                    self.logger.error(
                        f"Connection error to llama.cpp server after {max_retries} attempts: {e}"
                    )
                    exit(254)
            except Exception as e:
                self.logger.error(f"Connection error to llama.cpp server: {e}")
                exit(254)
