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

import contextvars
import ipaddress
import sys
import logging
from logging.handlers import RotatingFileHandler
import json
from typing import Any
from urllib.parse import urlparse
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

from pydantic import (  # noqa: E402
    AliasChoices,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)
from pydantic_settings import (  # noqa: E402
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)


def _detect_runtime_service(logger_name: str = "") -> str:
    """
    Automatically detect whether the current Python process is running
    Streamlit ('ui') or FastAPI/Uvicorn ('api') by inspecting `sys.argv`
    and `sys.modules` (without importing streamlit outside `src/ui/`).
    """
    argv_str = " ".join(sys.argv).lower()
    if "app-ui" in argv_str or "streamlit" in argv_str:
        return "ui"
    if "app-api" in argv_str or "uvicorn" in argv_str or "fastapi" in argv_str:
        return "api"

    st_runtime = sys.modules.get("streamlit.runtime")
    if st_runtime is not None and getattr(st_runtime, "exists", lambda: False)():
        return "ui"

    has_st = "streamlit" in sys.modules
    has_fastapi = "fastapi" in sys.modules or "uvicorn" in sys.modules
    if has_st and not has_fastapi:
        return "ui"
    if has_fastapi and not has_st:
        return "api"

    lname = (logger_name or "").lower()
    if lname == "ui" or lname.startswith("oncoflow.ui"):
        return "ui"
    if lname == "api" or lname.startswith(("oncoflow.api", "oncoflow.queue")):
        return "api"
    return "ui" if has_st else ("api" if has_fastapi else "app")


class LogSettings(BaseSettings):
    """
    Configuration for logging settings.

    Environment variables: APP_LOG_LEVEL, APP_LOG_LANGCHAINDEBUG, APP_LOG_TYPE,
    APP_LOG_SERVICE, APP_LOG_FILE, APP_LOG_MAX_BYTES, APP_LOG_BACKUP_COUNT
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
    service: str = Field(
        default_factory=_detect_runtime_service,
        description="Runtime service identifier ('ui', 'api', 'app'). Automatically detected from Streamlit/FastAPI runtime if APP_LOG_SERVICE is not set.",
    )
    file: str | None = Field(
        default=None,
        description="Optional path to a log file (e.g. /var/log/oncoflow/oncoflow.log). Enables RotatingFileHandler.",
    )
    max_bytes: int = Field(
        default=10 * 1024 * 1024,
        description="Maximum size in bytes before rotating the log file (default: 10 MB).",
    )
    backup_count: int = Field(
        default=5,
        description="Number of rotated log files to retain (default: 5).",
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
        default="openai/agents",
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
        default="openai/embeddings",
        description="Embedding model identifier for vector representation of documents.",
    )
    embeddings_port: str = Field(
        default="4000",
        description="Port number of the embeddings LLM server.",
    )
    api_key: str = Field(
        default="ollama",
        validation_alias=AliasChoices(
            "APP_CONFIGLLM_API_KEY",
            "LITELLM_API_KEY",
            "OPENAI_API_KEY",
            "LLAMACPP_API_KEY",
        ),
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
    port: int = Field(
        default=8000,
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


class QueueSettings(BaseSettings):
    """
    Configuration for the background task queue and hardware batch sizing.

    Environment variables: APP_QUEUE_ENABLED, APP_QUEUE_HARDWARE_PROFILE,
    APP_QUEUE_BATCH_SIZE, APP_QUEUE_MAX_RETRIES, APP_QUEUE_API_URL
    """

    model_config = SettingsConfigDict(env_prefix="APP_QUEUE_")

    enabled: bool = Field(
        default=True,
        description="Enable asynchronous processing queue via standard library queue.PriorityQueue.",
    )
    hardware_profile: str = Field(
        default="l4_24gb",
        description="Hardware profile preset (l4_24gb -> 1, a100_80gb -> 4, cpu_only -> 1, custom).",
    )
    batch_size: int = Field(
        default=1,
        ge=1,
        description="Maximum number of RCP files processed concurrently by the worker pool (e.g. 1 for NVIDIA L4 24GB).",
    )
    max_retries: int = Field(
        default=2,
        ge=0,
        description="Maximum automatic retry attempts when a queued task fails.",
    )
    api_url: str = Field(
        default="http://127.0.0.1:8000",
        description="URL of the cross-domain FastAPI service hosting the central PriorityQueue (e.g. http://127.0.0.1:8000 in dev, http://oncoflow-api:8000 in prod). Falls back to in-process PriorityQueue if unreachable.",
    )


class RCPSettings(BaseSettings):
    """
    Configuration for the RCP (Réunion de Concertation Pluridisciplinaire) pipeline.

    Environment variables: APP_RCP_PATH, APP_RCP_ADDITIONAL_PATH, APP_RCP_DOC_TYPE,
    APP_RCP_DOCLING_DEVICE, APP_RCP_CHUNK_SIZE, APP_RCP_CHUNK_OVERLAP,
    APP_RCP_MANUAL_QUERY, APP_RCP_DISPLAY_TYPE
    """

    model_config = SettingsConfigDict(env_prefix="APP_RCP_")

    path: Path = Field(
        default=Path(__file__).resolve().parent / "../../ressources/PatientMDTForm",
        description="Filesystem path to the directory containing patient MDT/RCP files.",
    )
    additional_path: Path = Field(
        default=Path(__file__).resolve().parent / "../../ressources/documents",
        description="Filesystem path to the directory containing additional reference files (e.g. TNCD guidelines).",
    )
    doc_type: str = Field(
        default="docling",
        description="Document parser type. See https://python.langchain.com/v0.1/docs/modules/data_connection/document_loaders/",
    )
    docling_device: str = Field(
        default="cpu",
        validation_alias=AliasChoices("APP_RCP_DOCLING_DEVICE", "DOCLING_DEVICE"),
        description="Hardware device for Docling model inference ('cpu', 'cuda', 'mps', 'auto').",
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


_LOCAL_HOST_SUFFIXES = (".localhost", ".local", ".lan", ".internal", ".home.arpa")


def is_local_host(url_or_host: str) -> bool:
    """
    Return True when the host is loopback, private (RFC 1918 / ULA), link-local,
    a single-label name (Docker service / LAN host such as `litellm`, `mongod`)
    or uses a local-only suffix (`.local`, `.lan`, `.internal`...).
    """
    value = (url_or_host or "").strip()
    host = urlparse(value).hostname if "://" in value else value.split(":")[0]
    host = (host or "").strip("[]").lower()
    if not host:
        return False
    if host == "localhost" or host.endswith(_LOCAL_HOST_SUFFIXES):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return "." not in host
    return ip.is_loopback or ip.is_private or ip.is_link_local


# Per-execution-context overrides (one Streamlit session = one script thread).
# A ContextVar instead of a class-level dict: an override set by one user session
# must never leak into other sessions or background worker threads.
_RUNTIME_OVERRIDES: contextvars.ContextVar[dict[str, Any] | None] = (
    contextvars.ContextVar("oncoflow_runtime_overrides", default=None)
)

_LOGGING_GLOBALS_CONFIGURED = False


class _JsonFormatter(logging.Formatter):
    """Serialize log records as valid JSON (messages are escaped by json.dumps)."""

    def __init__(self, default_context: dict[str, Any], context_keys: list[str]):
        super().__init__()
        self.default_context = default_context
        self.context_keys = context_keys

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "time": self.formatTime(record),
            "level": record.levelname,
            "service": getattr(record, "service", None),
            "name": record.name,
            "message": record.getMessage(),
            "context": {"service": getattr(record, "service", None)}
            | self.default_context
            | {k: getattr(record, k, None) for k in self.context_keys},
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, ensure_ascii=False)


class _RuntimeServiceFilter(logging.Filter):
    """Injects `record.service` and `record.service_upper` from `LogSettings.service` (or runtime auto-detection)."""

    def __init__(self, log_settings: LogSettings) -> None:
        super().__init__()
        self.log_settings = log_settings

    def filter(self, record: logging.LogRecord) -> bool:
        configured = (self.log_settings.service or "").strip().lower()
        if configured and configured not in ("auto", "app"):
            svc = configured
        else:
            svc = _detect_runtime_service(record.name)
            self.log_settings.service = svc
        record.service = svc
        record.service_upper = svc.upper()
        return True


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

    @classmethod
    def set_runtime_override(cls, **kwargs: Any) -> None:
        """
        Register pydantic-settings runtime overrides for the current execution context
        only (current Streamlit session thread), without mutating os.environ nor
        affecting other sessions / worker threads.
        """
        current = dict(_RUNTIME_OVERRIDES.get() or {})
        current.update(kwargs)
        _RUNTIME_OVERRIDES.set(current)

    @classmethod
    def clear_runtime_overrides(cls) -> None:
        """Remove all runtime overrides of the current execution context."""
        _RUNTIME_OVERRIDES.set(None)

    @classmethod
    def get_runtime_overrides(cls) -> dict[str, Any]:
        """Return a copy of the runtime overrides of the current execution context."""
        return dict(_RUNTIME_OVERRIDES.get() or {})

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        def _runtime_source() -> dict[str, Any]:
            return dict(_RUNTIME_OVERRIDES.get() or {})

        return (
            init_settings,
            _runtime_source,
            env_settings,
            dotenv_settings,
            file_secret_settings,
        )

    domain: str = Field(
        default="oncology",
        description="Default domain of the application. Valid values: oncology, sma.",
    )

    allowed_domains: str = Field(
        default="oncology,sma",
        description="Comma-separated list of active domains supported by the cross-domain API and Queue (APP_ALLOWED_DOMAINS).",
    )

    language: str = Field(
        default="french",
        description="Language of the application. Valid values: french, english.",
    )

    dev_mode: bool = Field(
        default=True,
        description="Enable development mode. When True, uses development configurations.",
    )

    auth_mode: str = Field(
        default="local",
        description="Authentication mode for the UI. Valid values: 'local' (streamlit-authenticator) or 'oauth_proxy' (HTTP headers injected by oauth2-proxy).",
    )

    api_token: SecretStr | None = Field(
        default=None,
        description="Shared secret required by the REST API (`Authorization: Bearer <token>` or `X-API-Key`). Mandatory when APP_DEV_MODE=false (APP_API_TOKEN).",
    )

    proxy_secret: SecretStr | None = Field(
        default=None,
        description="Shared secret injected by the reverse proxy (header `X-Oncoflow-Proxy-Secret`) in auth_mode=oauth_proxy. Identity headers are ignored when it does not match (APP_PROXY_SECRET).",
    )

    admin_users: str = Field(
        default="",
        description="Comma-separated usernames/emails allowed to use admin features (queue admin page, global cache purge). Empty = every authenticated user is admin (APP_ADMIN_USERS).",
    )

    api_host: str = Field(
        default="127.0.0.1",
        description="Bind address of the REST API when started with `python app-api.py` (APP_API_HOST). Use 0.0.0.0 only inside a private container network.",
    )

    allow_remote_llm: bool = Field(
        default=False,
        description="Allow LLM endpoints outside the local / private network (APP_ALLOW_REMOTE_LLM). Patient data must stay local: keep False except for explicit test deployments.",
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
    queue: QueueSettings = Field(
        default_factory=QueueSettings,
        description="Background processing queue and hardware batching settings.",
    )

    def model_post_init(self, __context) -> None:
        super().model_post_init(__context)
        # Dynamically isolate paths, databases, and collections by domain (e.g., oncology, sma)
        if self.domain:
            self.rcp.additional_path = self.rcp.additional_path / self.domain
            try:
                self.rcp.additional_path.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass

            self.rcp.path = self.rcp.path / self.domain
            try:
                self.rcp.path.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass

            self.mongodb.database = f"{self.mongodb.database}_{self.domain}"
            self.mongodb.vectordatabase = f"{self.mongodb.vectordatabase}_{self.domain}"
            self.dbvec.collection = f"{self.dbvec.collection}_{self.domain}"
            self.milvus.database = f"{self.milvus.database}_{self.domain}"

    @model_validator(mode="after")
    def _enforce_local_llm(self) -> "AppConfig":
        """Refuse to send patient data to non-local LLM endpoints unless explicitly allowed."""
        if not self.allow_remote_llm and not is_local_host(self.llm.url):
            raise ValueError(
                f"LLM endpoint '{self.llm.url}' is not a local/private host. Patient data "
                "must stay local: use a local endpoint or set APP_ALLOW_REMOTE_LLM=true "
                "explicitly (test deployments only)."
            )
        return self

    def is_admin(self, *identities: str | None) -> bool:
        """Return True if one of the user identities (username, email) is an admin."""
        admins = {u.strip().lower() for u in self.admin_users.split(",") if u.strip()}
        if not admins:
            return True
        return any(i and i.strip().lower() in admins for i in identities)

    @property
    def enabled_domains_list(self) -> list[str]:
        """Return normalized list of enabled domains configured in APP_ALLOWED_DOMAINS."""
        domains = [
            d.strip().lower() for d in self.allowed_domains.split(",") if d.strip()
        ]
        if self.domain and self.domain.lower() not in domains:
            domains.append(self.domain.lower())
        return domains or ["oncology"]

    def for_domain(self, domain: str | None = None) -> "AppConfig":
        """Return an AppConfig instance scoped to the requested domain after validating it."""
        target = (domain or self.domain or "oncology").strip().lower()
        if target not in self.enabled_domains_list:
            raise ValueError(
                f"Domain '{target}' is not enabled. Allowed domains: {self.enabled_domains_list}"
            )
        if target == self.domain:
            return self
        return AppConfig(
            domain=target,
            allowed_domains=self.allowed_domains,
            language=self.language,
            dev_mode=self.dev_mode,
            auth_mode=self.auth_mode,
            api_token=self.api_token,
            proxy_secret=self.proxy_secret,
            admin_users=self.admin_users,
            api_host=self.api_host,
            allow_remote_llm=self.allow_remote_llm,
            llm=self.llm.model_copy(deep=True),
            logs=self.logs.model_copy(deep=True),
            chromadb=self.chromadb.model_copy(deep=True),
            queue=self.queue.model_copy(deep=True),
        )

    @property
    def auth_config_path(self) -> Path:
        base_dir = Path(__file__).resolve().parent.parent.parent
        if self.dev_mode:
            return base_dir / "config/auth_config_dev.yaml"
        else:
            return base_dir / "config/auth_config.yaml"

    @staticmethod
    def _configure_logging_globals() -> None:
        """Process-wide logging tweaks, applied once (not on every `set_logger` call)."""
        global _LOGGING_GLOBALS_CONFIGURED
        if _LOGGING_GLOBALS_CONFIGURED:
            return
        _LOGGING_GLOBALS_CONFIGURED = True

        # --- Suppress noisy third-party loggers ---
        logging.getLogger("langchain.retrievers.multi_query").setLevel(logging.INFO)
        logging.getLogger("transformers").setLevel(logging.ERROR)
        logging.getLogger("pymilvus").setLevel(logging.ERROR)
        logging.getLogger("streamlit.runtime.scriptrunner").setLevel(logging.DEBUG)

        # Suppress HuggingFace transformers internal logging if available
        try:
            from transformers import logging as transformers_logging

            transformers_logging.set_verbosity_error()
        except ImportError:
            pass

    def set_logger(
        self,
        name: str,
        default_context: dict[str, Any] | None = None,
        additional_context: list[str] | None = None,
    ) -> logging.Logger:
        self._configure_logging_globals()
        default_context = default_context or {}

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

        service_filter = _RuntimeServiceFilter(self.logs)
        ch.addFilter(service_filter)

        if self.logs.type == "text":
            formatlog = "%(asctime)s - [%(service_upper)s] - %(levelname)s - %(name)s"
            for k, v in default_context.items():
                formatlog = f"{formatlog} - {k}: {v}"
            for k in context:
                formatlog = f"{formatlog} - {k}: %({k})s"
            formatter = logging.Formatter(f"{formatlog} - %(message)s")
        elif self.logs.type == "json":
            formatter = _JsonFormatter(default_context, list(context))
        else:
            raise ValueError(f"log type : {self.logs.type} not yet available")
        ch.setFormatter(formatter)
        logger.addHandler(ch)

        if self.logs.file:
            try:
                log_path = Path(self.logs.file)
                log_path.parent.mkdir(parents=True, exist_ok=True)
                fh = RotatingFileHandler(
                    log_path,
                    maxBytes=self.logs.max_bytes,
                    backupCount=self.logs.backup_count,
                    encoding="utf-8",
                )
                fh.setLevel(level=self.logs.level)
                fh.addFilter(service_filter)
                fh.setFormatter(formatter)
                logger.addHandler(fh)
            except Exception as e:
                logger.warning(
                    f"Failed to initialize file log handler ({self.logs.file}): {e}"
                )

        return logger
