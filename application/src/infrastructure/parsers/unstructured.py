from typing import Iterator

from langchain_core.document_loaders import BaseLoader
from langchain_core.documents import Document


class UnstructuredDocumentLoader(BaseLoader):
    """Document loader using the unstructured library to parse PDFs."""

    def __init__(
        self,
        file_path: str,
        chunking_strategy: str = "by_title",
        max_characters: int = 1000000,
        include_orig_elements: bool = False,
    ) -> None:
        """Initialize the loader with a file path and partition options.

        Args:
            file_path: The path to the PDF file to load.
            chunking_strategy: Strategy for chunking (default: "by_title").
            max_characters: Maximum characters per chunk (default: 1000000).
            include_orig_elements: Whether to include original elements.
        """
        self.file_path = file_path
        self.chunking_strategy = chunking_strategy
        self.max_characters = max_characters
        self.include_orig_elements = include_orig_elements

    def lazy_load(self) -> Iterator[Document]:
        """A lazy loader that partitions the PDF and yields LangChain Document objects."""
        from unstructured.partition.pdf import partition_pdf

        elements = partition_pdf(
            filename=self.file_path,
            chunking_strategy=self.chunking_strategy,
            max_characters=self.max_characters,
            include_orig_elements=self.include_orig_elements,
        )

        for element in elements:
            metadata = (
                element.metadata.to_dict()
                if hasattr(element, "metadata") and hasattr(element.metadata, "to_dict")
                else {}
            )
            metadata["source"] = self.file_path
            yield Document(
                page_content=str(element),
                metadata=metadata,
            )


# Alias for backwards compatibility
UnstructuredPDFLoader = UnstructuredDocumentLoader
