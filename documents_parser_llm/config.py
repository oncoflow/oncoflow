
import os
import logging
import json
from pathlib import Path
# from environ-config
import environ
import langchain


@environ.config(prefix="APP")
class AppConfig():
    """
    Class for reading and configuring application settings from environment variables.
    """
    
    @environ.config
    class Log:
        level = environ.var(
            default="INFO", help="Log level of app")
        langchain_debug = environ.var(
            default=True, converter=bool, help="langchain Log level of app")
        type = environ.var(
            default="text", help="Log type (text or json) of app")

        @level.validator
        def _log_level_selctor(self, var, log_level):
            if log_level not in logging._levelToName.values():
                raise ValueError(
                    f"{log_level} not valid, valid choices : {logging._levelToName.values()}")

    @environ.config
    class Configllm:
        """
        Class for configuring the llm system.
        """
        type = environ.var(
            default="Ollama", help="Type of llm system (ex Ollama)")
        url = environ.var(default="http://127.0.0.1", help="URL of llm system")
        port = environ.var(default="11434", help="Port of llm system")
        models = environ.var(default="llama3",
                             help="Model of llm system, type all for test all ollama models")
        temp = environ.var(default="0", converter=int,
                           help="Temperature of llm system")
        embeddings = environ.var(default="all-minilm",
                                 help="embeddings Model to use")

    @environ.config
    class DatabasesVectorial:
        """
        Class for configuring the vectorial database settings.
        """
        type = environ.var(default="ChromaDB", help="type of DB")
        collection = environ.var(
            default="oncoflowDocs", help="Collectionname to use")
        client = environ.var(default="PersistentClient",
                             help="PersistentClient or HttpClient")
        host = environ.var(default="localhost",
                           help="Hostname when HttpClient used")
        port = environ.var(default="8000", help="Port when HttpClient used")

    @environ.config
    class RCP:
        """
        Class for configuring the retrieval pipeline configuration.
        """
        path = environ.var(
            default=f"{os.path.dirname(os.path.realpath(__file__))}/rcp", converter=Path, help="Path to find RCP files")
        additional_path = environ.var(
            default=f"{os.path.dirname(os.path.realpath(__file__))}/ressources", converter=Path, help="Path to additionnal files")
        doc_type = environ.var(
            default="PyMuPDFLoader", help="Document type, see https://python.langchain.com/v0.1/docs/modules/data_connection/document_loaders/ ")
        chunk_size = environ.var(
            default="1000", converter=int, help="chunk_size of document")
        chunk_overlap = environ.var(
            default="10", converter=int, help="chunk_overlap of document")

        manual_query = environ.bool_var(
            default=False, help="Manual prompting for debug")

        @path.validator
        def _ensure_path_exists(self, var, path):
            if not path.exists():
                raise ValueError(f"Path {var} not found.")

    llm = environ.group(Configllm)
    dbvec = environ.group(DatabasesVectorial)
    rcp = environ.group(RCP)
    logs = environ.group(Log)
        
         
    def set_logger(self, name, default_context = {}, additional_context=None):
        
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
            formatter = logging.Formatter(f'{formatlog} - %(message)s')
        elif self.logs.type == "json":
            formatlog = {
                "time":  '%(asctime)s',
                "level": '%(levelname)s',
                "name": '%(name)s',
                "message":  '%(message)s',
                "context": default_context | {k: f'%({k})s' for k in context}
            }
            formatter = logging.Formatter(json.dumps(formatlog))
        else:
            raise ValueError(f"log type : {self.logs.type} not yet available")
        ch.setFormatter(formatter)
        logger.addHandler(ch)
        
        langchain.debug = self.logs.langchain_debug    
        
        return logger
