import unittest
from unittest.mock import MagicMock, patch

from src.infrastructure.parsers.ollama_ocr import OllamaOcrDocumentLoader
from src.infrastructure.parsers.openparse import OpenParseDocumentLoader


class TestParsers(unittest.TestCase):
    def setUp(self):
        self.mock_config = MagicMock()
        self.mock_config.llm.ocrmodels = "granite3.2-vision"
        self.mock_config.llm.url = "http://127.0.0.1"
        self.mock_config.llm.port = "11434"

    @patch("src.infrastructure.parsers.ollama_ocr.OCRProcessor")
    def test_ollama_ocr_loader_load(self, mock_ocr_processor_cls):
        mock_ocr = mock_ocr_processor_cls.return_value
        mock_ocr.process_image.return_value = "Extracted OCR text content"

        loader = OllamaOcrDocumentLoader("/path/to/image.png", self.mock_config)
        self.assertEqual(loader.model, "granite3.2-vision")
        self.assertEqual(loader.base_url, "http://127.0.0.1:11434/api/generate")

        docs = loader.load()

        mock_ocr.process_image.assert_called_once_with(
            image_path="/path/to/image.png",
            format_type="text",
            language="fr",
        )
        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0].page_content, "Extracted OCR text content")
        self.assertEqual(docs[0].metadata["source"], "/path/to/image.png")

    @patch("src.infrastructure.parsers.openparse.openparse.Pdf")
    @patch("src.infrastructure.parsers.openparse.openparse.DocumentParser")
    def test_openparse_loader_lazy_load(self, mock_doc_parser_cls, mock_pdf_cls):
        mock_parser = mock_doc_parser_cls.return_value

        # Mock parsed document nodes
        mock_node1 = MagicMock()
        mock_node1.text = "Node 1 text"
        mock_node1.tokens = 5
        mock_node1.num_pages = 1
        mock_node1.node_id = 101
        mock_node1.start_page = 0
        mock_node1.end_page = 0

        mock_parsed_doc = MagicMock()
        mock_parsed_doc.nodes = [mock_node1]
        mock_parser.parse.return_value = mock_parsed_doc

        loader = OpenParseDocumentLoader("/path/to/doc.pdf")
        docs_iterator = loader.lazy_load()
        docs = list(docs_iterator)

        # Assertions
        mock_doc_parser_cls.assert_called_once_with(
            table_args={
                "parsing_algorithm": "pymupdf",
                "table_output_format": "markdown",
            }
        )
        mock_parser.parse.assert_called_once_with("/path/to/doc.pdf", ocr=True)
        mock_pdf_cls.assert_called_once_with("/path/to/doc.pdf")

        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0].page_content, "Node 1 text")
        self.assertEqual(docs[0].metadata["tokens"], 5)
        self.assertEqual(docs[0].metadata["node_id"], 101)
        self.assertEqual(docs[0].metadata["source"], "/path/to/doc.pdf")
