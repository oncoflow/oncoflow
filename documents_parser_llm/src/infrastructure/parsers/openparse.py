from typing import Iterator

from langchain_core.document_loaders import BaseLoader
from langchain_core.documents import Document

import openparse


class OpenParseDocumentLoader(BaseLoader):
    """An example document loader that reads a file line by line."""

    def __init__(self, file_path: str) -> None:
        """Initialize the loader with a file path.

        Args:
            file_path: The path to the file to load.
        """
        self.file_path = file_path

    def lazy_load(self) -> Iterator[Document]:  # <-- Does not take any arguments
        """A lazy loader that reads a file line by line.

        When you're implementing lazy load methods, you should use a generator
        to yield documents one by one.
        """

        parser = openparse.DocumentParser(
            table_args={
                "parsing_algorithm": "pymupdf",
                "table_output_format": "markdown"
            },
            # table_args={
            #     "parsing_algorithm": "unitable",
            #     "min_table_confidence": 0.8,
            # }
        )
        parsed_basic_doc = parser.parse(
            self.file_path, 
            ocr=True
        )
        pdf = openparse.Pdf(self.file_path)
        pdf.export_with_bboxes(
            parsed_basic_doc.nodes, output_pdf=f"{self.file_path}.bbox"
        )

        for node in parsed_basic_doc.nodes:
            yield Document(
                page_content=node.text,
                metadata={
                    "tokens": node.tokens,
                    "num_pages": node.num_pages,
                    "node_id": node.node_id,
                    "start_page": node.start_page,
                    "end_page": node.end_page,
                    "source": self.file_path,
                },
            )
        return None
