from typing import Iterator

from langchain_core.document_loaders import BaseLoader
from langchain_core.documents import Document

from ollama_ocr import OCRProcessor
from src.application.config import AppConfig

class OllamaOcrDocumentLoader(BaseLoader):
    """An example document loader that reads a file line by line."""

    def __init__(self, file_path: str, config: AppConfig ) -> None:
        """Initialize the loader with a file path.

        Args:
            file_path: The path to the file to load.
        """
        self.file_path = file_path
        self.model = config.llm.ocrmodels
        self.base_url = f"{config.llm.url}:{config.llm.port}/api/generate"


    def load(self) -> list[Document]:  # <-- Does not take any arguments
        ocr = OCRProcessor(model_name=self.model, base_url=self.base_url)

        result = ocr.process_image(
            image_path=self.file_path,
            format_type="text", # Options: markdown, text, json, structured, key_value, table
            language="fr",
        )

        print(result)

        return [ 
            Document(
             page_content=result,
             metadata={
                "source": self.file_path,
             }
            )
        ]