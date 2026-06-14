from src.application.config import AppConfig
from src.infrastructure.llm.base import LLMConnect
from src.infrastructure.llm.ollama import OllamaConnect
from src.infrastructure.llm.openai import OpenAIConnect
from src.infrastructure.llm.vllm import VllmConnect
from src.infrastructure.llm.litellm import LiteLLMConnect
from src.infrastructure.llm.llamacpp import LlamaCppConnect


def get_llm_client(config: AppConfig) -> LLMConnect:
    """
    Factory function to return the appropriate LLM client instance
    based on the configured LLM type.

    Args:
        config (AppConfig): Application configuration.

    Returns:
        OllamaConnect | OpenAIConnect | VllmConnect | LiteLLMConnect | LlamaCppConnect: The resolved LLM client instance.

    Raises:
        ValueError: If config.llm.type is not supported.
    """
    llm_type = config.llm.type.lower()
    if llm_type == "ollama":
        return OllamaConnect(config)
    elif llm_type == "openai":
        return OpenAIConnect(config)
    elif llm_type == "vllm":
        return VllmConnect(config)
    elif llm_type == "litellm":
        return LiteLLMConnect(config)
    elif llm_type == "llamacpp":
        return LlamaCppConnect(config)
    else:
        raise ValueError(
            f"LLM type '{config.llm.type}' is not supported. "
            f"Supported types are 'Ollama', 'OpenAI', 'vLLM', 'LiteLLM', and 'LlamaCpp'."
        )
