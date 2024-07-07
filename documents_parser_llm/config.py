
import os
import logging
from pathlib import Path
# from environ-config
import environ
from pythonjsonlogger import jsonlogger
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
)


@environ.config(prefix="APP")
class AppConfig():
    """
    Class for reading and configuring application settings from environment variables.
    """

    @environ.config
    class Configllm:
        type = environ.var(default="Ollama", help="Type of llm system (ex Ollama)")
        url = environ.var(default="http://127.0.0.1", help="URL of llm system")
        port = environ.var(default="11434", help="Port of llm system")
        model = environ.var(default="llama3", help="Model of llm system")
        temp = environ.var(default="0", converter=int, help="Temperature of llm system")

    @environ.config
    class Databases_vectorial:
        type = environ.var(default="ChromaDB", help="type of DB")
        collection = environ.var(default="oncoflowDocs", help="Collectionname to use")
        client = environ.var(default="PersistentClient", help="PersistentClient or HttpClient")
        host = environ.var(default="localhost", help="Hostname when HttpClient used" )
        port = environ.var(default="8000", help="Port when HttpClient used")
        model = environ.var(default="all-MiniLM-L6-v2", help="embeddings Model to use")

    @environ.config
    class RCP:
        path = environ.var(
            default=f"{os.path.dirname(os.path.realpath(__file__))}/rcp", converter=Path, help="Path to find RCP files")

        doc_type = environ.var(default="PyMuPDFLoader", help="Document type, see https://python.langchain.com/v0.1/docs/modules/data_connection/document_loaders/ ")
        chunk_size = environ.var(default="1000", converter=int, help="chunk_size of document")
        chunk_overlap = environ.var(default="10", converter=int, help="chunk_overlap of document")
        
        manual_query = environ.bool_var(default=True, help="Manual prompting for debug")

        @path.validator
        def _ensure_path_exists(self, var, path):
            if not path.exists():
                raise ValueError(f"Path {var} not found.")

    llm = environ.group(Configllm)
    dbvec = environ.group(Databases_vectorial)
    rcp = environ.group(RCP)


class AppLogger():
    def __init__(self):
        """
        Initializes the readerConfig object and sets up logging and tracing.
        """
        self.logger()

    def otel(self):
        """
        Initializes OpenTelemetry tracing.
        """
        provider = TracerProvider()
        processor = BatchSpanProcessor(ConsoleSpanExporter())
        provider.add_span_processor(processor)

        # Sets the global default tracer provider
        trace.set_tracer_provider(provider)

    def logger(self):
        """
        Initializes and returns a logging object using the `jsonlogger` formatter.

        Returns:
            logging.Logger: A logger object configured to use the `jsonlogger` formatter.
        """
        logger = logging.getLogger()
        logHandler = logging.StreamHandler()
        formatter = jsonlogger.JsonFormatter()
        logHandler.setFormatter(formatter)
        logger.addHandler(logHandler)

        return logger
