from abc import ABC, abstractmethod
from typing import Any, List
from src.application.config import AppConfig


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
        tools: List[Any] = [],
        reasoning: bool = True,
    ) -> Any:
        """Create and return a LangChain ChatModel instance."""
        pass

    @abstractmethod
    def get_models(self) -> List[str]:
        """Return a list of available models."""
        pass

    @abstractmethod
    def test_connection(self) -> None:
        """Test the connection to the LLM backend."""
        pass
