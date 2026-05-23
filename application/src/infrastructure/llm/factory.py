from src.application.config import AppConfig
from src.infrastructure.llm.ollama import OllamaConnect
from src.infrastructure.llm.openai import OpenAIConnect


def get_llm_client(config=AppConfig):
    """
    Factory function to return the appropriate LLM client instance
    based on the configured LLM type.
    
    Args:
        config (AppConfig): Application configuration.
        
    Returns:
        OllamaConnect | OpenAIConnect: The resolved LLM client instance.
        
    Raises:
        ValueError: If config.llm.type is not supported.
    """
    llm_type = config.llm.type.lower()
    if llm_type == "ollama":
        return OllamaConnect(config)
    elif llm_type == "openai":
        return OpenAIConnect(config)
    else:
        raise ValueError(
            f"LLM type '{config.llm.type}' is not supported. "
            f"Supported types are 'Ollama' and 'OpenAI'."
        )
