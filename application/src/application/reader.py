"""
This code defines a DocumentReader class that performs the following tasks:

- Loads a document from a specified path.
- Splits the document into chunks using a CharacterTextSplitter.
- Adds the chunks to a VectorStore.
- Creates a retrieval chain that allows users to ask questions about the document.

The code also defines a configuration class (AppConfig) and an Llm class (which is not shown in the code).

Usage:

1. Create an instance of the DocumentReader class.
2. Call the askInDocument() method to ask a question about the document.

Example:

```python
# Create an instance of the DocumentReader class
reader = DocumentReader(pdf="patient_file.pdf")

# Ask a question about the document
answer = reader.askInDocument("What is the patient's age?")

# Print the answer
print(answer)
"""

from langchain_community import document_loaders
from langchain_docling import DoclingLoader
from langchain_docling.loader import ExportType

from src.application.config import AppConfig
from src.application.tools import timed

from src.infrastructure.parsers.openparse import OpenParseDocumentLoader
from src.infrastructure.parsers.ollama_ocr import OllamaOcrDocumentLoader
from src.infrastructure.vectorial.client import VectorialDataBaseClient
from src.infrastructure.llm.ollama import OllamaConnect
from langchain_core.vectorstores import VectorStoreRetriever
from langchain_core.documents import Document

from slugify import slugify


class DocumentReader:
    """
    A class that reads documents and enables querying them using an LLM.

    Attributes:
        document_path (str): The path to the document.
        llm (Llm): An instance of the Llm class for performing language tasks.
        vecdb (VectorialDataBase): An instance of VectorialDataBase for vector storage and retrieval.
        default_loader (callable): The default loader type for documents.
        logger (Logger): A logger for tracking progress and errors.
    """

    document = str
    collectionName = "oncoflowDocs"
    retriever = None
    additional_pdf = None
    docs_pdf = {}

    def __init__(
        self,
        config=AppConfig,
        document=str,
        document_type="mtd",
        models=None,
    ):
        self.config = config
        self.document = document
        self.current_model = None

        if document_type == "mtd":
            self.document_path = f"{config.rcp.path}/{document}"
        elif document_type == "ressource":
            self.document_path = f"{config.rcp.additional_path}/{document}"
        else:
            raise ValueError(f"{document_type} not yet supported")

        self.vecdb = VectorialDataBaseClient(
            config, coll_prefix=slugify(document, separator="_")
        ).vectordb

        if config.llm.type.lower() == "ollama":
            llm_client = OllamaConnect(config)
        else:
            raise ValueError(f"{config.llm.type} not yet supported")
        self.embeddings = llm_client.embedding

        self.logger = config.set_logger(
            "reader",
            default_context={
                "document": document,
                "embeddings": self.embeddings,
                "parser": config.rcp.doc_type,
            },
        )

        self.metadata = {}

        self.default_loader = config.rcp.doc_type

        self.logger.info(
            f"Class reader succesfully init, Start reading document {self.document_path}"
        )

    def _load_document(self, document=str, loader_type=None) -> list[Document]:
        """Loads a document from the specified path using the given loader type."""
        try:
            if loader_type is None:
                loader_type = self.default_loader
            if loader_type == "openparse":
                cla = OpenParseDocumentLoader
            elif loader_type == "docling":
                from docling.chunking import HybridChunker
                from docling.datamodel.base_models import InputFormat
                from docling.datamodel.pipeline_options import (
                    PdfPipelineOptions,
                    RapidOcrOptions,
                )
                from docling.document_converter import (
                    DocumentConverter,
                    PdfFormatOption,
                )

                print("Downloading RapidOCR models")

                ocr_options = RapidOcrOptions()

                pipeline_options = PdfPipelineOptions(
                    ocr_options=ocr_options,
                )

                # Convert the document
                converter = DocumentConverter(
                    format_options={
                        InputFormat.PDF: PdfFormatOption(
                            pipeline_options=pipeline_options,
                        ),
                    },
                )
                self.markdown_exporter = DoclingLoader(
                    file_path=document,
                    export_type=ExportType.MARKDOWN,
                    converter=converter,
                    chunker=HybridChunker(tokenizer="intfloat/multilingual-e5-base"),
                ).load()
                return DoclingLoader(
                    file_path=document,
                    export_type=ExportType.DOC_CHUNKS,
                    converter=converter,
                    chunker=HybridChunker(tokenizer="intfloat/multilingual-e5-base"),
                ).load()
            elif loader_type == "ollamaOcr":
                return OllamaOcrDocumentLoader(document, self.config).load()
            else:
                cla = getattr(document_loaders, loader_type)

                if isinstance(cla, document_loaders.UnstructuredPDFLoader):
                    return cla(
                        document,
                        chunking_strategy="by_title",
                        max_characters=1000000,
                        include_orig_elements=False,
                    ).load()

            return cla(document).load()
            # return self.text_splitter.split_documents(docs)
        except Exception:
            self.logger.error("Error in llm read")
            raise

    def get_retriever(self) -> VectorStoreRetriever:
        return self.vecdb.get_retriever()

    @timed
    def read_document(self):
        """
        Reads a document from the specified loader and splits it into chunks.
        Then, adds the chunks to a VectorStore.
        Finally, creates a retrieval chain that allows users to ask questions about the document.
        """
        self.logger.info(f"Start reading document {self.document_path}")

        self.chunked_documents = self._load_document(self.document_path)

        self.vecdb.add_chunked_to_collection(self.chunked_documents, flush_before=True)

        self.current_model = self.config.llm.embeddings
