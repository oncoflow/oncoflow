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


def _build_llm_cache_key(
    config: AppConfig,
    target_cls: type[LLMConnect],
) -> tuple[Any, ...]:
    llm_cfg = config.llm
    raw_temp = llm_cfg.temp
    try:
        temp_val: float | str = float(raw_temp or 0.0)
    except (TypeError, ValueError):
        temp_val = str(raw_temp)
    return (
        id(target_cls),
        (llm_cfg.type or "").strip().lower(),
        (llm_cfg.url or "").strip(),
        (llm_cfg.port or "").strip(),
        (llm_cfg.uri or "").strip(),
        (llm_cfg.embeddings_port or "").strip(),
        (llm_cfg.embeddings or "").strip(),
        (llm_cfg.models or "").strip(),
        temp_val,
        _extract_secret_str(llm_cfg.api_key),
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
    if llm_type == "ollama":
        target_cls: type[LLMConnect] = OllamaConnect
    elif llm_type == "openai":
        target_cls = OpenAIConnect
    elif llm_type == "vllm":
        target_cls = VllmConnect
    elif llm_type == "litellm":
        target_cls = LiteLLMConnect
    elif llm_type == "llamacpp":
        target_cls = LlamaCppConnect
    else:
        raise ValueError(
            f"LLM type '{config.llm.type}' is not supported. "
            f"Supported types are 'Ollama', 'OpenAI', 'vLLM', 'LiteLLM', and 'LlamaCpp'."
        )

    cache_key = _build_llm_cache_key(config, target_cls)
    now = time.monotonic()

    with _LLM_CLIENT_CACHE_LOCK:
        cached_entry = _LLM_CLIENT_CACHE.get(cache_key)
        if cached_entry is not None:
            created_at, cached_client = cached_entry
            if (now - created_at) < _LLM_CLIENT_CACHE_TTL_SECONDS:
                _LLM_CLIENT_CACHE.move_to_end(cache_key)
                return cached_client
            _LLM_CLIENT_CACHE.pop(cache_key, None)

    client: LLMConnect = target_cls(config)

    raw_embedding = getattr(client, "embedding", None)
    if raw_embedding is not None and not isinstance(
        raw_embedding, CachedEmbeddingsProxy
    ):
        model_key = config.llm.embeddings or ""
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
