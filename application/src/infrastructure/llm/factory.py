from collections import OrderedDict
import threading
import time
from typing import Any

from src.application.config import AppConfig
from src.infrastructure.llm.base import CachedEmbeddingsProxy, LLMConnect
from src.infrastructure.llm.ollama import OllamaConnect
from src.infrastructure.llm.openai import OpenAIConnect
from src.infrastructure.llm.vllm import VllmConnect
from src.infrastructure.llm.litellm import LiteLLMConnect
from src.infrastructure.llm.llamacpp import LlamaCppConnect

_LLM_CLIENT_CACHE_MAXSIZE: int = 16
_LLM_CLIENT_CACHE_TTL_SECONDS: float = 60.0
_LLM_CLIENT_CACHE_LOCK = threading.Lock()
_LLM_CLIENT_CACHE: OrderedDict[tuple[Any, ...], tuple[float, LLMConnect]] = (
    OrderedDict()
)


def _extract_secret_str(val: Any) -> str:
    if val is None:
        return ""
    if hasattr(val, "get_secret_value"):
        try:
            return str(val.get_secret_value())
        except Exception:
            return ""
    return str(val)


def _build_llm_cache_key(config: AppConfig) -> tuple[Any, ...]:
    llm_cfg = getattr(config, "llm", None)
    return (
        str(getattr(llm_cfg, "type", "") or "").strip().lower(),
        str(getattr(llm_cfg, "url", "") or "").strip(),
        str(getattr(llm_cfg, "port", "") or "").strip(),
        str(getattr(llm_cfg, "uri", "") or "").strip(),
        str(getattr(llm_cfg, "embeddings_port", "") or "").strip(),
        str(getattr(llm_cfg, "embeddings", "") or "").strip(),
        str(getattr(llm_cfg, "models", "") or "").strip(),
        float(getattr(llm_cfg, "temp", 0.0) or 0.0),
        _extract_secret_str(getattr(llm_cfg, "api_key", None)),
    )


def clear_llm_client_cache() -> None:
    """Clear the process-local LLM client and embedding cache."""
    with _LLM_CLIENT_CACHE_LOCK:
        _LLM_CLIENT_CACHE.clear()


def get_llm_client(config: AppConfig) -> LLMConnect:
    """
    Factory function to return the appropriate LLM client instance
    based on the configured LLM type, using a bounded TTL/LRU cache to avoid
    repeating synchronous `/models` or `/health` connection probes across
    every agent and reader instantiation.

    Args:
        config (AppConfig): Application configuration.

    Returns:
        OllamaConnect | OpenAIConnect | VllmConnect | LiteLLMConnect | LlamaCppConnect: The resolved LLM client instance.

    Raises:
        ValueError: If config.llm.type is not supported.
    """
    llm_type = config.llm.type.lower()
    if llm_type not in ("ollama", "openai", "vllm", "litellm", "llamacpp"):
        raise ValueError(
            f"LLM type '{config.llm.type}' is not supported. "
            f"Supported types are 'Ollama', 'OpenAI', 'vLLM', 'LiteLLM', and 'LlamaCpp'."
        )

    cache_key = _build_llm_cache_key(config)
    now = time.monotonic()

    with _LLM_CLIENT_CACHE_LOCK:
        cached_entry = _LLM_CLIENT_CACHE.get(cache_key)
        if cached_entry is not None:
            created_at, cached_client = cached_entry
            if (now - created_at) < _LLM_CLIENT_CACHE_TTL_SECONDS:
                _LLM_CLIENT_CACHE.move_to_end(cache_key)
                return cached_client
            _LLM_CLIENT_CACHE.pop(cache_key, None)

    if llm_type == "ollama":
        client: LLMConnect = OllamaConnect(config)
    elif llm_type == "openai":
        client = OpenAIConnect(config)
    elif llm_type == "vllm":
        client = VllmConnect(config)
    elif llm_type == "litellm":
        client = LiteLLMConnect(config)
    else:
        client = LlamaCppConnect(config)

    raw_embedding = getattr(client, "embedding", None)
    if raw_embedding is not None and not isinstance(
        raw_embedding, CachedEmbeddingsProxy
    ):
        model_key = str(getattr(config.llm, "embeddings", "") or "")
        client.embedding = CachedEmbeddingsProxy(
            raw_embedding,
            model_key=model_key,
        )

    with _LLM_CLIENT_CACHE_LOCK:
        _LLM_CLIENT_CACHE[cache_key] = (time.monotonic(), client)
        _LLM_CLIENT_CACHE.move_to_end(cache_key)
        while len(_LLM_CLIENT_CACHE) > _LLM_CLIENT_CACHE_MAXSIZE:
            _LLM_CLIENT_CACHE.popitem(last=False)

    return client
