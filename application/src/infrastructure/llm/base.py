import time
from abc import ABC, abstractmethod
from typing import Any, Callable, List, Optional, Tuple, Type

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
    if port and str(port).strip() and f":{port}" not in url:
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
