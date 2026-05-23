import unittest
from unittest.mock import MagicMock
from langchain_core.documents import Document

from src.application.agent.tools import get_mtd_markdown, search_on_mtd, search_on_ressources


class TestAgentTools(unittest.TestCase):
    def setUp(self):
        # Create a mock logger
        self.mock_logger = MagicMock()

        # Create a mock reader
        self.mock_reader = MagicMock()
        self.mock_exporter_doc = MagicMock()
        self.mock_exporter_doc.page_content = "# Mock Markdown Patient Record"
        self.mock_reader.markdown_exporter = [self.mock_exporter_doc]

        # Create mock vector database client for search
        self.mock_clientdb = MagicMock()
        self.mock_reader.vecdb.clientdb = self.mock_clientdb

        # Create a mock additional reader
        self.mock_add_reader = MagicMock()
        self.mock_add_clientdb = MagicMock()
        self.mock_add_reader.vecdb.clientdb = self.mock_add_clientdb

        # Configure ToolRuntime context
        self.mock_runtime = MagicMock()
        self.mock_runtime.context = {
            "logger": self.mock_logger,
            "reader": self.mock_reader,
            "additionnal_readers": [self.mock_add_reader],
        }

    def test_get_mtd_markdown_success(self):
        result = get_mtd_markdown.func(self.mock_runtime)
        self.assertEqual(result, "# Mock Markdown Patient Record")
        self.mock_logger.info.assert_called_with("tool get_mtd_markdown called")

    def test_search_on_mtd_success(self):
        # Setup mock documents returned by search
        doc1 = Document(page_content="Tumor of the pancreas", metadata={"page": 1})
        doc2 = Document(page_content="Metastatic disease", metadata={"page": 2})
        self.mock_clientdb.max_marginal_relevance_search.return_value = [doc1, doc2]

        serialized, docs = search_on_mtd.func(
            self.mock_runtime,
            query="pancreatic tumor",
            k=2,
        )

        # Assertions
        self.mock_clientdb.max_marginal_relevance_search.assert_called_once_with(
            "pancreatic tumor",
            k=2,
            fetch_k=20,
            param=None,
            expr=None,
            timeout=None,
        )
        self.assertEqual(len(docs), 2)
        self.assertEqual(docs[0], doc1)
        self.assertEqual(docs[1], doc2)
        expected_serialized = (
            "Source: {'page': 1}\nContent: Tumor of the pancreas\n\n"
            "Source: {'page': 2}\nContent: Metastatic disease"
        )
        self.assertEqual(serialized, expected_serialized)

    def test_search_on_ressources_success(self):
        # Setup mock documents from additional reader
        doc = Document(page_content="TNCD pancreas guidelines", metadata={"section": "TNCD"})
        self.mock_add_clientdb.max_marginal_relevance_search.return_value = [doc]

        serialized, docs = search_on_ressources.func(
            self.mock_runtime,
            query="TNCD guidelines",
            k=1,
        )

        # Assertions
        self.mock_add_clientdb.max_marginal_relevance_search.assert_called_once_with(
            "TNCD guidelines",
            k=1,
            fetch_k=20,
            param=None,
            expr=None,
            timeout=None,
        )
        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0], doc)
        expected_serialized = "Source: {'section': 'TNCD'}\nContent: TNCD pancreas guidelines"
        self.assertEqual(serialized, expected_serialized)

    def test_search_on_ressources_empty(self):
        self.mock_add_clientdb.max_marginal_relevance_search.return_value = []

        serialized, docs = search_on_ressources.func(
            self.mock_runtime,
            query="non-existent info",
        )

        self.assertEqual(serialized, "No additionnal ressources provided")
        self.assertEqual(docs, [])
