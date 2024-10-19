"""
Module containing configuration classes and logger setup for application.

This module provides configuration classes and a function to set up logging based on environment variables.
It supports configuring logging levels, types, and context; LLM system settings such as type, URL, port,
models, temperature, and embeddings; vectorial database settings like type, collection name, client type,
host, and port; RCP pipeline configuration including document paths, types, chunk sizes, overlaps, and manual prompting;
and sets up a logger for the given name with configurable levels, types, default context, and additional context.

Classes:
    AppConfig: A class to read and configure application settings from environment variables.
        It contains nested classes Log, Configllm, DatabasesVectorial, and RCP for configuring respective settings.

Functions:
    set_logger(name, default_context={}, additional_context=None): Sets up a logger with the given name based on configuration
        settings. It accepts optional `default_context` and `additional_context` parameters to customize logging context.
"""

import os
import logging
import json
from pathlib import Path

# from environ-config
import environ
import langchain


@environ.config(prefix="APP")
class AppConfig:
    """
    Class for reading and configuring application settings from environment variables.
    """

    @environ.config
    class Log:
        """
        Configuration class for logging settings.

        Attributes:
            level (str): The log level of the application. Defaults to "INFO".
                         Valid choices are any value in logging._levelToName.values().

            langchaindebug (bool): Whether to enable langchain debugging mode or not. Defaults to False.
                                   This setting controls langchain's Log level, independent of APP.Log.level.

            type (str): The log type of the application. Defaults to "text". Accepted values are "text" and "json".
        """
        level = environ.var(default="INFO", help="Log level of app")
        langchaindebug = environ.bool_var(
            default=False, help="langchain Log level of app"
        )
        type = environ.var(default="text", help="Log type (text or json) of app")

        @level.validator
        def _log_level_selector(self, var, log_level):
            if log_level not in logging._levelToName.values():
                raise ValueError(
                    f"{log_level} not valid, valid choices : {logging._levelToName.values()}"
                )

    @environ.config
    class Configllm:
        """
        Class for configuring the llm system.
        """

        type = environ.var(default="Ollama", help="Type of llm system (ex Ollama)")
        url = environ.var(default="http://127.0.0.1", help="URL of llm system")
        port = environ.var(default="11434", help="Port of llm system")
        models = environ.var(
            default="llama3.1:70b-instruct-q4_0",
            help="Model of llm system, type all for test all ollama models",
        )
        temp = environ.var(
            default="0.1", converter=float, help="Temperature of llm system"
        )
        embeddings = environ.var(default="all-minilm", help="embeddings Model to use")

    # llama3.1:70b-instruct-q4_0 mixtral:8x7b-instruct-v0.1-q8_0 llama3.1:8b-instruct-q8_0

    @environ.config
    class DatabasesVectorial:
        """
        Class for configuring the vectorial database settings.
        """

        type = environ.var(default="ChromaDB", help="type of DB")
        collection = environ.var(default="oncoflowDocs", help="Collectionname to use")
        client = environ.var(
            default="HttpClient", help="PersistentClient or HttpClient"
        )
        host = environ.var(default="localhost", help="Hostname when HttpClient used")
        port = environ.var(default="8000", help="Port when HttpClient used")

    @environ.config
    class MongoDB:
        user = environ.var(default="root", help="Mongo Username")
        password = environ.var(default="root", help="Mongo password")
        host = environ.var(default="127.0.0.1", help="Address of DB")
        port = environ.var(default="8081", help="Port of DB")
        database = environ.var(default="Oncoflow", help="Mongo database name")

    @environ.config
    class RCP:
        """
        Class for configuring the retrieval pipeline configuration.
        """

        path = environ.var(
            default=f"{os.path.dirname(os.path.realpath(__file__))}/../../ressources/PatientMDTOncologicForm",
            converter=Path,
            help="Path to find RCP files",
        )
        additional_path = environ.var(
            default=f"{os.path.dirname(os.path.realpath(__file__))}/../../ressources/TNCD",
            converter=Path,
            help="Path to additionnal files",
        )
        doc_type = environ.var(
            default="PyMuPDFLoader",
            help="Document type, see https://python.langchain.com/v0.1/docs/modules/data_connection/document_loaders/ ",
        )
        chunk_size = environ.var(
            default="2000", converter=int, help="chunk_size of document"
        )

        chunk_overlap = environ.var(
            default="200", converter=int, help="chunk_overlap of document"
        )

        manual_query = environ.bool_var(
            default=False, help="Manual prompting for debug"
        )
        
        display_type = environ.var(
            default="mongodb", help="Type opf display"
        )

        @path.validator
        def _ensure_path_exists(self, var, path):
            if not path.exists():
                raise ValueError(f"Path {var} not found.")

    llm = environ.group(Configllm)
    dbvec = environ.group(DatabasesVectorial)
    rcp = environ.group(RCP)
    logs = environ.group(Log)
    mongodb = environ.group(MongoDB)

    def set_logger(self, name, default_context={}, additional_context=None):

        logging.getLogger("langchain.retrievers.multi_query").setLevel(logging.INFO)
        context = additional_context if additional_context is not None else []

        logger = logging.getLogger(name)
        logger.setLevel(level=self.logs.level)
        logger.handlers.clear()
        ch = logging.StreamHandler()
        ch.setLevel(level=self.logs.level)

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

        langchain.debug = self.logs.langchaindebug

        return logger
