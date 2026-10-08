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

import hashlib
import os

from langchain_community import document_loaders
from langchain_docling import DoclingLoader
from langchain_docling.loader import ExportType

from src.application.config import AppConfig
from src.application.tools import timed

from src.infrastructure.parsers.openparse import OpenParseDocumentLoader
from src.infrastructure.parsers.ollama_ocr import OllamaOcrDocumentLoader
from src.infrastructure.vectorial.client import VectorialDataBaseClient
from src.infrastructure.llm.base import LLMConnect
from src.infrastructure.llm.factory import get_llm_client
from langchain_core.vectorstores import VectorStoreRetriever
from langchain_core.documents import Document

from src.infrastructure.vectorial.database import VectorialDataBase

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

    document: str = ""
    collectionName: str = "oncoflowDocs"
    retriever = None
    additional_pdf = None
    docs_pdf: list[str] = []
    vecdb: VectorialDataBase

    _docling_converter = None
    _docling_chunker = None

    @classmethod
    def get_docling_components(cls):
        if cls._docling_converter is None:
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

            print("Preloading RapidOCR models and Docling Converter...")
            ocr_options = RapidOcrOptions()
            pipeline_options = PdfPipelineOptions(ocr_options=ocr_options)
            pipeline_options.allow_external_plugins = True

            cls._docling_converter = DocumentConverter(
                format_options={
                    InputFormat.PDF: PdfFormatOption(
                        pipeline_options=pipeline_options,
                    ),
                },
            )
            cls._docling_chunker = HybridChunker(
                tokenizer="intfloat/multilingual-e5-base"
            )
        return cls._docling_converter, cls._docling_chunker

    @staticmethod
    def calculate_file_hash(file_path: str) -> str:
        """Calculates the SHA-256 hash of a file by reading chunks."""
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    def __init__(
        self,
        config: AppConfig,
        document: str,
        document_type: str = "mtd",
        models=None,
        vecdb_client: VectorialDataBase | None = None,
        llm_client: LLMConnect | None = None,
    ):
        self.config = config
        self.document = document
        self.document_type = document_type
        self.current_model = None

        if document_type == "mtd":
            self.document_path = f"{config.rcp.path}/{document}"
        elif document_type == "ressource":
            self.document_path = f"{config.rcp.additional_path}/{document}"
        else:
            raise ValueError(f"{document_type} not yet supported")

        if vecdb_client is None:
            # pyrefly: ignore [bad-assignment]
            self.vecdb = VectorialDataBaseClient(
                config, coll_prefix=slugify(document, separator="_")
            ).vectordb
        else:
            self.vecdb = vecdb_client

        if llm_client is None:
            llm_client_instance = get_llm_client(config)
            self.embeddings = llm_client_instance.embedding
        else:
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
        self.file_hash: str | None = None
        self.markdown_exporter: list[Document] = []
        self.chunked_documents: list[Document] = []

        self.logger.debug(
            f"Class reader succesfully init, Start reading document {self.document_path}"
        )

    def _load_document(
        self, document: str, loader_type: str | None = None
    ) -> list[Document]:
        """Loads a document from the specified path using the given loader type."""
        try:
            if loader_type is None:
                loader_type = self.default_loader
            if loader_type == "openparse":
                cla = OpenParseDocumentLoader
            elif loader_type == "docling":
                converter, chunker = self.get_docling_components()

                self.markdown_exporter = DoclingLoader(
                    file_path=document,
                    export_type=ExportType.MARKDOWN,
                    converter=converter,
                    chunker=chunker,
                ).load()
                return DoclingLoader(
                    file_path=document,
                    export_type=ExportType.DOC_CHUNKS,
                    converter=converter,
                    chunker=chunker,
                ).load()
            elif loader_type == "ollamaOcr":
                return OllamaOcrDocumentLoader(document, self.config).load()
            else:
                cla = getattr(document_loaders, loader_type)

                if isinstance(cla, document_loaders.UnstructuredPDFLoader):
                    # pyrefly: ignore [not-callable]
                    return cla(
                        document,
                        chunking_strategy="by_title",
                        max_characters=1000000,
                        include_orig_elements=False,
                    ).load()

            return cla(document).load()
            # return self.text_splitter.split_documents(docs)
        except Exception as e:
            self.logger.exception("Error in document load: %s", e)
            raise

    def get_retriever(self) -> VectorStoreRetriever:
        # pyrefly: ignore [missing-attribute, not-callable]
        return self.vecdb.get_retriever()

    def is_indexed(self) -> bool:
        """
        Checks if the document is indexed in the VectorStore.
        """
        # pyrefly: ignore [missing-attribute]
        return self.vecdb.is_indexed()

    def _get_file_hash(self) -> str | None:
        """Computes or returns the cached SHA-256 hash of the document file."""
        if self.file_hash is not None:
            return self.file_hash

        if os.path.exists(self.document_path):
            try:
                self.file_hash = self.calculate_file_hash(self.document_path)
            except Exception as e:
                self.logger.warning(
                    "Could not compute hash for %s: %s", self.document_path, e
                )
        return self.file_hash

    def _get_cached_document(self) -> dict | None:
        """Retrieves cached document parsing result from MongoDB using the file hash."""
        if self.config.rcp.display_type != "mongodb":
            return None

        file_hash = self._get_file_hash()
        if not file_hash:
            return None

        try:
            from src.infrastructure.documents.mongodb import Mongodb

            client = Mongodb(self.config)
            cached_entry = client.get_document_cache(file_hash)
            client.close()
            return cached_entry
        except Exception as e:
            self.logger.warning("Error querying document cache from MongoDB: %s", e)
            return None

    def _restore_from_cache(self, cached_entry: dict) -> None:
        """Restores reader Markdown exporter from a cached MongoDB entry."""
        markdown_content = cached_entry.get("markdown", "")
        self.logger.info(
            "Cache HIT for document %s (hash: %s...)",
            self.document,
            self.file_hash[:8] if self.file_hash else "",
        )
        self.markdown_exporter = [
            Document(
                page_content=markdown_content,
                metadata={
                    "source": self.document_path,
                    "file": self.document,
                    "file_hash": self.file_hash,
                },
            )
        ]

    def _save_to_cache(self, markdown: str) -> None:
        """Saves document markdown to MongoDB document_cache collection."""
        if self.config.rcp.display_type != "mongodb" or not markdown:
            return

        file_hash = self._get_file_hash()
        if not file_hash:
            return

        try:
            from src.infrastructure.documents.mongodb import Mongodb

            client = Mongodb(self.config)
            client.save_document_cache(
                file_hash=file_hash,
                file_name=self.document,
                markdown=markdown,
                document_type=getattr(self, "document_type", "mtd"),
            )
            client.close()
            self.logger.info(
                "Saved document %s to MongoDB document_cache (hash: %s...)",
                self.document,
                file_hash[:8],
            )
        except Exception as e:
            self.logger.warning("Error saving to document cache in MongoDB: %s", e)

    def clear_cache(self) -> None:
        """Deletes the cache entry for this document from MongoDB."""
        if self.config.rcp.display_type != "mongodb":
            return

        try:
            from src.infrastructure.documents.mongodb import Mongodb

            client = Mongodb(self.config)
            client.delete_document_cache(
                file_hash=self.file_hash, file_name=self.document
            )
            client.close()
            self.logger.info("Cleared document cache for %s", self.document)
        except Exception as e:
            self.logger.warning("Error clearing document cache in MongoDB: %s", e)

    @timed
    def read_document(self, force_reload: bool = False):
        """
        Reads a document from the specified loader and splits it into chunks.
        Then, adds the chunks to a VectorStore.
        Finally, creates a retrieval chain that allows users to ask questions about the document.

        If the document hash is already cached in MongoDB and the vector store is indexed,
        avoids re-running Docling and re-indexing.
        """
        self.logger.debug(f"Start reading document {self.document_path}")

        cached_entry = None if force_reload else self._get_cached_document()

        # Cache HIT:
        if cached_entry is not None and cached_entry.get("markdown"):
            self._restore_from_cache(cached_entry)

            is_vecdb_indexed = False
            try:
                is_vecdb_indexed = self.is_indexed()
            except Exception as e:
                self.logger.warning("Error checking if vecdb is indexed: %s", e)

            if is_vecdb_indexed and not force_reload:
                self.logger.info(
                    "Vector DB already indexed for %s, skipping Docling & re-indexing.",
                    self.document,
                )
                self.current_model = self.config.llm.embeddings
                return

            self.logger.info(
                "Vector DB not indexed for %s, parsing chunks to index vector store...",
                self.document,
            )

        # Cache MISS or Vector DB needs indexing:
        self.logger.info(
            "Running document loader for %s (doc_type: %s)...",
            self.document,
            self.default_loader,
        )
        self.chunked_documents = self._load_document(self.document_path)

        # pyrefly: ignore [missing-attribute]
        self.vecdb.add_chunked_to_collection(self.chunked_documents, flush_before=True)
        self.current_model = self.config.llm.embeddings

        # Save to cache if markdown was produced
        markdown_content = ""
        if (
            hasattr(self, "markdown_exporter")
            and self.markdown_exporter
            and len(self.markdown_exporter) > 0
        ):
            markdown_content = self.markdown_exporter[0].page_content

        if markdown_content:
            self._save_to_cache(markdown_content)
