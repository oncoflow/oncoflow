from collections import OrderedDict
import threading
import time
from abc import ABC, abstractmethod
from typing import Any, Callable, List, Optional, Tuple, Type

from langchain_core.embeddings import Embeddings
from tenacity import (
    RetryError,
    Retrying,
    retry_if_exception_type,
    stop_after_attempt,
    stop_after_delay,
    wait_random_exponential,
)

from src.application.config import AppConfig


class LLMConnectionError(ConnectionError):
    """Raised when an LLM backend cannot be reached (replaces ``exit(254)``)."""


class LLMConfigurationError(ValueError):
    """Raised when the LLM client configuration is invalid or incomplete."""


# Default bounds for connection retries (exponential backoff with jitter).
CONNECT_RETRY_MAX_DELAY_S: float = 60.0
CONNECT_RETRY_MAX_ATTEMPTS: int = 10
CONNECT_RETRY_WAIT_MAX_S: float = 10.0


def build_base_url(url: str, port: Optional[str], uri: Optional[str]) -> str:
    """
    Build an HTTP base URL from ``url``, optional ``port`` and optional ``uri``.

    - Appends ``:port`` only if not already present in ``url``.
    - Avoids double slashes between the host part and the uri.
    """
    url = url or ""
    if port and port.strip() and f":{port}" not in url:
        base_url = f"{url}:{port}"
    else:
        base_url = url
    base_url = base_url.rstrip("/")
    uri = (uri or "").lstrip("/")
    if uri:
        base_url = f"{base_url}/{uri}"
    return base_url


def retry_connection(
    func: Callable[[], Any],
    logger: Any,
    *,
    retry_on: Tuple[Type[BaseException], ...] = (Exception,),
    max_delay: float = CONNECT_RETRY_MAX_DELAY_S,
    max_attempts: int = CONNECT_RETRY_MAX_ATTEMPTS,
    wait_max: float = CONNECT_RETRY_WAIT_MAX_S,
    sleep: Optional[Callable[[float], None]] = None,
    backend: str = "LLM",
) -> Any:
    """
    Run ``func`` with bounded retries (exponential backoff + jitter).

    Total time is bounded by ``max_delay`` seconds and ``max_attempts`` attempts.
    Raises ``LLMConnectionError`` once retries are exhausted.
    """
    kwargs: dict = {"sleep": sleep if sleep is not None else _sleep}
    retrying = Retrying(
        stop=stop_after_delay(max_delay) | stop_after_attempt(max_attempts),
        wait=wait_random_exponential(multiplier=1, max=wait_max),
        retry=retry_if_exception_type(retry_on),
        before_sleep=_before_sleep_logger(logger, backend),
        reraise=False,
        **kwargs,
    )
    try:
        return retrying(func)
    except RetryError as e:
        last = e.last_attempt.exception() if e.last_attempt else None
        _log(logger, "error", f"{backend} connection failed after retries: {last}")
        raise LLMConnectionError(
            f"Unable to connect to {backend} backend: {last}"
        ) from last


def _before_sleep_logger(logger: Any, backend: str) -> Callable:
    def _log_attempt(retry_state) -> None:
        exc = retry_state.outcome.exception() if retry_state.outcome else None
        wait = retry_state.next_action.sleep if retry_state.next_action else 0
        _log(
            logger,
            "warning",
            f"{backend} not reachable (attempt {retry_state.attempt_number}): "
            f"{exc!r}; retrying in {wait:.1f}s",
        )

    return _log_attempt


def _sleep(seconds: float) -> None:
    # Indirection so tests can patch ``src.infrastructure.llm.base.time.sleep``.
    time.sleep(seconds)


def _log(logger: Any, level: str, msg: str) -> None:
    if logger is not None:
        getattr(logger, level)(msg)


class LLMConnect(ABC):
    """
    Abstract base class defining the interface for all LLM connection clients.
    """

    config: AppConfig
    logger: Any
    embedding: Any
    client: Any

    @abstractmethod
    def __init__(self, config: AppConfig) -> None:
        """Initialize the LLM connection with application configuration."""
        pass

    @abstractmethod
    def chat(
        self,
        model: str,
        output: Any = None,
        temperature: float | None = None,
        tools: Optional[List[Any]] = None,
        reasoning: bool = True,
        reasoning_budget: int | None = None,
    ) -> Any:
        """Create and return a LangChain ChatModel instance."""
        pass

    @abstractmethod
    def get_models(self) -> List[str]:
        """Return a list of available models."""
        pass

    @abstractmethod
    def test_connection(self) -> None:
        """Test the connection to the LLM backend.

        Raises:
            LLMConnectionError: if the backend is unreachable after retries.
        """
        pass


DEFAULT_EMBEDDING_CACHE_MAXSIZE: int = 512


class CachedEmbeddingsProxy(Embeddings):
    """
    Low-footprint thread-safe LRU caching proxy around a LangChain `Embeddings` instance.

    Inherits from `langchain_core.embeddings.Embeddings` so vector stores performing
    `isinstance(..., Embeddings)` checks (such as ChromaDB, Milvus, and MongoDB Atlas)
    accept the proxy transparently. Deduplicates repeated `embed_query(text)` calls and
    returns defensive copies of cached float vectors so callers cannot mutate cached entries.
    """

    def __init__(
        self,
        underlying: Any,
        model_key: str = "",
        maxsize: int = DEFAULT_EMBEDDING_CACHE_MAXSIZE,
    ) -> None:
        self._underlying = underlying
        self._model_key = str(
            model_key or getattr(underlying, "model", "") or ""
        ).strip()
        self._maxsize = max(1, maxsize)
        self._lock = threading.Lock()
        self._cache: OrderedDict[tuple[str, str], list[float]] = OrderedDict()
        self._hits = 0
        self._misses = 0

    def embed_documents(
        self, texts: list[str], *args: Any, **kwargs: Any
    ) -> list[list[float]]:
        """Delegate document batch embedding directly to the underlying embeddings model."""
        return self._underlying.embed_documents(texts, *args, **kwargs)

    def embed_query(self, text: str, *args: Any, **kwargs: Any) -> list[float]:
        """Compute or retrieve a cached embedding vector for a single query string."""
        if args or kwargs or not isinstance(text, str):
            return list(self._underlying.embed_query(text, *args, **kwargs))

        normalized_query = " ".join(text.split())
        key = (self._model_key, normalized_query)

        with self._lock:
            cached = self._cache.get(key)
            if cached is not None:
                self._cache.move_to_end(key)
                self._hits += 1
                return list(cached)

        vector = list(self._underlying.embed_query(normalized_query))

        with self._lock:
            self._misses += 1
            self._cache[key] = list(vector)
            self._cache.move_to_end(key)
            while len(self._cache) > self._maxsize:
                self._cache.popitem(last=False)

        return list(vector)

    def cache_info(self) -> dict[str, int]:
        """Return hit/miss/size statistics for the embedding query cache."""
        with self._lock:
            return {
                "hits": self._hits,
                "misses": self._misses,
                "maxsize": self._maxsize,
                "currsize": len(self._cache),
            }

    def cache_clear(self) -> None:
        """Clear all cached query embeddings and reset statistics."""
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0

    def __getattr__(self, name: str) -> Any:
        return getattr(self._underlying, name)
