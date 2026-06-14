"""
Module containing configuration classes and logger setup for application.

This module provides configuration classes and a function to set up logging based on environment variables.
It supports configuring logging levels, types, and context; LLM system settings such as type, URL, port,
models, temperature, and embeddings; vectorial database settings like type, collection name, client type,
host, and port; RCP pipeline configuration including document paths, types, chunk sizes, overlaps, and manual prompting;
and sets up a logger for the given name with configurable levels, types, default context, and additional context.

Classes:
    AppConfig: A class to read and configure application settings from environment variables.
        It contains nested settings classes for Log, LLM, DatabasesVectorial, MilvusDB, ChromaDB,
        MongoDB, and RCP configuration.

Functions:
    AppConfig.set_logger(name, default_context={}, additional_context=None): Sets up a logger with the given name
        based on configuration settings. It accepts optional `default_context` and `additional_context` parameters
        to customize logging context.
"""

import os
import logging
import json
import warnings
from pathlib import Path

# --- Suppress noisy third-party warnings globally on module load ---
# Hugging Face __path__ access deprecation
warnings.filterwarnings("ignore", message=".*Accessing.*__path__.*")
# PyMilvus async client init failure (non-critical)
warnings.filterwarnings("ignore", message=".*Failed to initialize AsyncMilvusClient.*")
# PyMilvus ORM-style deprecation warnings
warnings.filterwarnings("ignore", message=".*ORM-style.*")
# Streamlit PDF viewer compatibility warnings
warnings.filterwarnings("ignore", message=".*streamlit-pdf-viewer.*")

from pydantic import Field, field_validator  # noqa: E402
from pydantic_settings import BaseSettings, SettingsConfigDict  # noqa: E402


class LogSettings(BaseSettings):
    """
    Configuration for logging settings.

    Environment variables: APP_LOG_LEVEL, APP_LOG_LANGCHAINDEBUG, APP_LOG_TYPE
    """

    model_config = SettingsConfigDict(env_prefix="APP_LOG_")

    level: str = Field(
        default="INFO",
        description="Log level of the application. Valid values: DEBUG, INFO, WARNING, ERROR, CRITICAL.",
    )
    langchaindebug: bool = Field(
        default=False,
        description="Enable LangChain debug mode. Controls LangChain's internal log level independently of APP_LOG_LEVEL.",
    )
    type: str = Field(
        default="text",
        description="Log output format. 'text' for human-readable logs, 'json' for structured JSON logs.",
    )

    @field_validator("level")
    @classmethod
    def validate_log_level(cls, v):
        if v not in logging._levelToName.values():
            raise ValueError(
                f"{v} not valid, valid choices : {logging._levelToName.values()}"
            )
        return v


class ConfigllmSettings(BaseSettings):
    """
    Configuration for the LLM (Large Language Model) system.

    Environment variables: APP_CONFIGLLM_TYPE, APP_CONFIGLLM_URL, APP_CONFIGLLM_URI,
    APP_CONFIGLLM_PORT, APP_CONFIGLLM_MODELS, APP_CONFIGLLM_OCRMODELS, APP_CONFIGLLM_TEMP,
    APP_CONFIGLLM_EMBEDDINGS, APP_CONFIGLLM_API_KEY
    """

    model_config = SettingsConfigDict(env_prefix="APP_CONFIGLLM_")

    type: str = Field(
        default="LiteLLM",
        description="Type of LLM backend system. Supported values: Ollama, OpenAI, vLLM, LiteLLM.",
    )
    url: str = Field(
        default="http://127.0.0.1",
        description="Base URL of the LLM server (e.g. http://127.0.0.1).",
    )
    uri: str = Field(
        default="/",
        description="URI path for OpenAI-style API endpoints on the LLM server.",
    )
    port: str = Field(
        default="4000",
        description="Port number of the LLM server.",
    )
    models: str = Field(
        default="openai/qwen3:14b",
        description="Model identifier to use for reasoning. Use 'all' to test all available Ollama models.",
    )
    ocrmodels: str = Field(
        default="granite3.2-vision",
        description="Model identifier for OCR tasks within the Ollama LLM system.",
    )
    temp: float = Field(
        default=1,
        description="Temperature parameter for LLM generation. Higher values produce more random output.",
    )
    embeddings: str = Field(
        default="openai/bge-m3",
        description="Embedding model identifier for vector representation of documents.",
    )
    api_key: str = Field(
        default="ollama",
        description="API key for the LLM backend (required for OpenAI/vLLM, defaults to 'ollama' for local Ollama).",
    )


class DatabasesVectorialSettings(BaseSettings):
    """
    Configuration for the vectorial database selection.

    Environment variables: APP_DATABASESVECTORIAL_TYPE, APP_DATABASESVECTORIAL_COLLECTION
    """

    model_config = SettingsConfigDict(env_prefix="APP_DATABASESVECTORIAL_")

    type: str = Field(
        default="milvus",
        description="Type of vectorial database to use. Supported values: milvus, chroma.",
    )
    collection: str = Field(
        default="oncoflowDocs",
        description="Name of the vector collection for document storage and retrieval.",
    )


class MilvusDBSettings(BaseSettings):
    """
    Configuration for the Milvus vector database connection.

    Environment variables: APP_MILVUSDB_TOKEN, APP_MILVUSDB_DATABASE, APP_MILVUSDB_PORT, APP_MILVUSDB_HOST
    """

    model_config = SettingsConfigDict(env_prefix="APP_MILVUSDB_")

    token: str = Field(
        default="root:Milvus",
        description="Authentication token for Milvus in the format 'username:password'.",
    )
    database: str = Field(
        default="oncowflow",
        description="Name of the Milvus database instance.",
    )
    port: str = Field(
        default="19530",
        description="Port number for the Milvus server connection.",
    )
    host: str = Field(
        default="localhost",
        description="Hostname or IP address of the Milvus server.",
    )


class ChromaDBSettings(BaseSettings):
    """
    Configuration for the ChromaDB vector database connection.

    Environment variables: APP_CHOMADB_CLIENT, APP_CHOMADB_HOST, APP_CHOMADB_PORT
    """

    model_config = SettingsConfigDict(env_prefix="APP_CHOMADB_")

    client: str = Field(
        default="HttpClient",
        description="ChromaDB client type. 'PersistentClient' for local file storage, 'HttpClient' for remote server.",
    )
    host: str = Field(
        default="localhost",
        description="Hostname of the ChromaDB server (used when client is 'HttpClient').",
    )
    port: str = Field(
        default="8000",
        description="Port number of the ChromaDB server (used when client is 'HttpClient').",
    )


class MongoDBSettings(BaseSettings):
    """
    Configuration for the MongoDB database connection.

    Environment variables: APP_MONGODB_USER, APP_MONGODB_PASSWORD, APP_MONGODB_HOST,
    APP_MONGODB_PORT, APP_MONGODB_DATABASE, APP_MONGODB_VECTORDATABASE
    """

    model_config = SettingsConfigDict(env_prefix="APP_MONGODB_")

    user: str = Field(
        default="root",
        description="MongoDB authentication username.",
    )
    password: str = Field(
        default="root",
        description="MongoDB authentication password.",
    )
    host: str = Field(
        default="127.0.0.1",
        description="Hostname or IP address of the MongoDB server.",
    )
    port: str = Field(
        default="27017",
        description="Port number of the MongoDB server.",
    )
    database: str = Field(
        default="Oncoflow",
        description="Name of the primary MongoDB database for document metadata.",
    )
    vectordatabase: str = Field(
        default="OncoflowVector",
        description="Name of the MongoDB database used for vector storage.",
    )


class RCPSettings(BaseSettings):
    """
    Configuration for the RCP (Réunion de Concertation Pluridisciplinaire) pipeline.

    Environment variables: APP_RCP_PATH, APP_RCP_ADDITIONAL_PATH, APP_RCP_DOC_TYPE,
    APP_RCP_CHUNK_SIZE, APP_RCP_CHUNK_OVERLAP, APP_RCP_MANUAL_QUERY, APP_RCP_DISPLAY_TYPE
    """

    model_config = SettingsConfigDict(env_prefix="APP_RCP_")

    path: Path = Field(
        default=Path(os.path.dirname(os.path.realpath(__file__)))
        / "../../ressources/PatientMDTOncologicForm",
        description="Filesystem path to the directory containing patient MDT/RCP files.",
    )
    additional_path: Path = Field(
        default=Path(os.path.dirname(os.path.realpath(__file__)))
        / "../../ressources/TNCD",
        description="Filesystem path to the directory containing additional reference files (e.g. TNCD guidelines).",
    )
    doc_type: str = Field(
        default="docling",
        description="Document parser type. See https://python.langchain.com/v0.1/docs/modules/data_connection/document_loaders/",
    )
    chunk_size: int = Field(
        default=1000,
        description="Maximum number of characters per document chunk for text splitting.",
    )
    chunk_overlap: int = Field(
        default=150,
        description="Number of overlapping characters between consecutive document chunks.",
    )
    manual_query: bool = Field(
        default=False,
        description="Enable manual interactive prompting mode for debugging purposes.",
    )
    display_type: str = Field(
        default="mongodb",
        description="Display backend type for the UI dashboard. Supported values: mongodb.",
    )

    @field_validator("path")
    @classmethod
    def validate_path_exists(cls, v):
        if not v.exists():
            raise ValueError(f"Path {v} not found.")
        return v


class AppConfig(BaseSettings):
    """
    Main application configuration class.

    Reads settings from environment variables with the APP_ prefix.
    Also supports loading from a .env file at the project root.

    Each nested settings group maps to a set of environment variables:
    - APP_LOG_*        : Logging configuration
    - APP_CONFIGLLM_*  : LLM system configuration
    - APP_DATABASESVECTORIAL_* : Vectorial database selection
    - APP_MILVUSDB_*   : Milvus database connection
    - APP_CHOMADB_*    : ChromaDB connection
    - APP_MONGODB_*    : MongoDB connection
    - APP_RCP_*        : RCP pipeline settings
    """

    model_config = SettingsConfigDict(
        env_prefix="APP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    llm: ConfigllmSettings = Field(
        default_factory=ConfigllmSettings,
        description="LLM system configuration (model, URL, port, temperature, embeddings).",
    )
    dbvec: DatabasesVectorialSettings = Field(
        default_factory=DatabasesVectorialSettings,
        description="Vectorial database type and collection name.",
    )
    rcp: RCPSettings = Field(
        default_factory=RCPSettings,
        description="RCP pipeline settings (paths, parser, chunking, display).",
    )
    logs: LogSettings = Field(
        default_factory=LogSettings,
        description="Logging configuration (level, format, LangChain debug).",
    )
    mongodb: MongoDBSettings = Field(
        default_factory=MongoDBSettings,
        description="MongoDB connection settings (host, port, credentials, databases).",
    )
    chromadb: ChromaDBSettings = Field(
        default_factory=ChromaDBSettings,
        description="ChromaDB vector database connection settings.",
    )
    milvus: MilvusDBSettings = Field(
        default_factory=MilvusDBSettings,
        description="Milvus vector database connection settings.",
    )

    def set_logger(self, name, default_context={}, additional_context=None):

        # --- Suppress noisy third-party loggers ---
        logging.getLogger("langchain.retrievers.multi_query").setLevel(logging.INFO)
        logging.getLogger("transformers").setLevel(logging.ERROR)
        logging.getLogger("pymilvus").setLevel(logging.ERROR)
        logging.getLogger("streamlit.runtime.scriptrunner").setLevel(logging.DEBUG)

        # --- Suppress noisy third-party warnings ---
        # Hugging Face __path__ access deprecation
        warnings.filterwarnings("ignore", message=".*Accessing.*__path__.*")
        # PyMilvus async client init failure (non-critical)
        warnings.filterwarnings(
            "ignore", message=".*Failed to initialize AsyncMilvusClient.*"
        )
        # PyMilvus ORM-style deprecation warnings
        warnings.filterwarnings("ignore", message=".*ORM-style.*")
        # Streamlit PDF viewer compatibility warnings
        warnings.filterwarnings("ignore", message=".*streamlit-pdf-viewer.*")

        # Suppress HuggingFace transformers internal logging if available
        try:
            from transformers import logging as transformers_logging

            transformers_logging.set_verbosity_error()
        except ImportError:
            pass

        context = additional_context if additional_context is not None else []

        logger = logging.getLogger(name)
        logger.setLevel(level=self.logs.level)
        logger.handlers.clear()
        ch = logging.StreamHandler()
        ch.setLevel(level=self.logs.level)
        # Configure LangChain global logs
        from langchain_core.globals import set_verbose, set_debug

        if self.logs.langchaindebug:
            set_debug(True)
            set_verbose(True)
        elif self.logs.level == "DEBUG":
            set_verbose(True)
        if self.logs.type == "text":
            formatlog = "%(asctime)s - %(levelname)s - %(name)s"
            for k, v in default_context.items():
                formatlog = f"{formatlog} - {k}: {v}"
            for k in context:
                formatlog = f"{formatlog} - {k}: %({k})s"
            formatter = logging.Formatter(f"{formatlog} - %(message)s")
        elif self.logs.type == "json":
            formatlog = {
                "time": "%(asctime)s",
                "level": "%(levelname)s",
                "name": "%(name)s",
                "message": "%(message)s",
                "context": default_context | {k: f"%({k})s" for k in context},
            }
            formatter = logging.Formatter(json.dumps(formatlog))
        else:
            raise ValueError(f"log type : {self.logs.type} not yet available")
        ch.setFormatter(formatter)
        logger.addHandler(ch)

        return logger
