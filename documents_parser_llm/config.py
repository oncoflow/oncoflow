
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