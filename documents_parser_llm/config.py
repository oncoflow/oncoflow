
import os
import logging
from pythonjsonlogger import jsonlogger
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
)

class ReaderConfig():
    """
    Class for reading and configuring application settings from environment variables.
    """
    
    config_list = {
        "apiparserurl": str,
        "chromaHost": str
        ## ici on pourrait rajouter les autres parametres de config list genre chunksize= 2048, et même un chunksize : default=2048 et values =[ 1024, 2048] etc comme ca on pourrait après faire des test en faisant un for i in values
        # dans les parametres je verai bien : chunk_size, overlap, embedding model, retrieval_model : phi3, llama3, gemma2, et j'ai vu un llama3_chatqa spécial pour les questions réponses à rester j'ai installé sur mon ollama
        # je pense que temperature doit être à 0 forcémenet ? sinon pareil on peut mettre un peu d'originalité mais après il faut faire une médiane, à voir car cela va peut être dépendre du type de donnée que l'on cherche
        # et le type de loader document, je vois pour le moment soit de l'embedding direct avec pymupdf, soit en passant par un markdown avec https://pymupdf4llm.readthedocs.io/en/latest/#features
        # si les résultats sont équivalents, alors avantage à markdown pour gérer l'anonymization +++++++
        
    }

    config_keys = {}

    def __init__(self):
        """
        Initializes the readerConfig object and sets up logging and tracing.
        """
        self.logger()
   
    def setConfig(self):
        """
        Sets the configuration keys from environment variables.
        """
        for config in self.config_list:
            self.config_keys[config] = os.getenv(config.toLower(), config.toUpper())
   
    def getConfig(self, key):
        """
        Returns the value of the given configuration key.

        Args:
            key: The key of the configuration setting to retrieve.

        Returns:
            str: The value of the configuration setting.
        """
        return self.config_keys[key]
   
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