import unittest
from unittest.mock import MagicMock
from langchain_core.documents import Document

from src.application.agent.tools import (
    get_mtd_markdown,
    get_patient_ai_history,
    get_patient_mtds_markdown,
    search_on_mtd,
    search_on_patient_mtds,
    search_on_ressources,
)


class TestAgentTools(unittest.TestCase):
    def setUp(self):
        # Create a mock logger
        self.mock_logger = MagicMock()

        # Create a mock reader
        self.mock_reader = MagicMock()
        self.mock_reader.document = "rcp1.pdf"
        self.mock_reader.sections = {
            "file": "rcp1.pdf",
            "PatientAdministrative": {
                "first_name": "Jean",
                "last_name": "Dupont",
                "date_rcp": "2025-01-15T00:00:00",
            },
            "TumorLocation": {"tumor_location": "Pancreas"},
        }
        self.mock_exporter_doc = MagicMock()
        self.mock_exporter_doc.page_content = "# Mock Markdown Patient Record"
        self.mock_reader.markdown_exporter = [self.mock_exporter_doc]

        # Create a second mock reader for patient record tests
        self.mock_reader2 = MagicMock()
        self.mock_reader2.document = "rcp2.pdf"
        self.mock_reader2.sections = {
            "file": "rcp2.pdf",
            "PatientAdministrative": {
                "first_name": "Jean",
                "last_name": "Dupont",
                "date_rcp": "2026-03-18T00:00:00",
            },
            "isInterventionRequiered": {
                "intervention_required": True,
                "intervention_type": "Chirurgie",
            },
        }
        self.mock_exporter_doc2 = MagicMock()
        self.mock_exporter_doc2.page_content = "# Follow-up Patient Record"
        self.mock_reader2.markdown_exporter = [self.mock_exporter_doc2]

        # Create mock vector database client for search
        self.mock_clientdb = MagicMock()
        self.mock_reader.vecdb.clientdb = self.mock_clientdb

        self.mock_clientdb2 = MagicMock()
        self.mock_reader2.vecdb.clientdb = self.mock_clientdb2

        # Create a mock additional reader
        self.mock_add_reader = MagicMock()
        self.mock_add_clientdb = MagicMock()
        self.mock_add_reader.vecdb.clientdb = self.mock_add_clientdb

        # Configure ToolRuntime context for single RCP
        self.mock_runtime = MagicMock()
        self.mock_runtime.context = {
            "logger": self.mock_logger,
            "reader": self.mock_reader,
            "additionnal_readers": [self.mock_add_reader],
        }

        # Configure ToolRuntime context for PatientContext
        self.mock_patient_runtime = MagicMock()
        self.mock_patient_runtime.context = {
            "logger": self.mock_logger,
            "patient_readers": [self.mock_reader, self.mock_reader2],
            "additionnal_readers": [self.mock_add_reader],
        }

    def test_get_mtd_markdown_success(self):
        result = get_mtd_markdown.func(self.mock_runtime)
        self.assertEqual(result, "# Mock Markdown Patient Record")
        self.mock_logger.info.assert_called_with("tool get_mtd_markdown called")

    def test_get_mtd_markdown_lazy_reads_document_when_exporter_empty(self):
        """Ensure get_mtd_markdown calls reader.read_document() if markdown_exporter is initially empty."""
        unloaded_reader = MagicMock()
        unloaded_reader.document = "unloaded.pdf"
        unloaded_reader.markdown_exporter = []

        def _populate_exporter():
            doc = MagicMock()
            doc.page_content = "# Lazily Loaded PatientMDTForm Content"
            unloaded_reader.markdown_exporter = [doc]

        unloaded_reader.read_document.side_effect = _populate_exporter
        self.mock_runtime.context["reader"] = unloaded_reader

        result = get_mtd_markdown.func(self.mock_runtime)
        unloaded_reader.read_document.assert_called_once()
        self.assertEqual(result, "# Lazily Loaded PatientMDTForm Content")

    def test_get_patient_mtds_markdown_lazy_reads_documents_when_exporter_empty(self):
        """Ensure get_patient_mtds_markdown calls read_document() on any reader whose markdown_exporter is empty."""
        unloaded_reader = MagicMock()
        unloaded_reader.document = "rcp_lazy.pdf"
        unloaded_reader.markdown_exporter = []

        def _populate_exporter():
            doc = MagicMock()
            doc.page_content = "# Lazily Loaded PatientRecord Entry"
            unloaded_reader.markdown_exporter = [doc]

        unloaded_reader.read_document.side_effect = _populate_exporter
        self.mock_patient_runtime.context["patient_readers"] = [unloaded_reader]

        result = get_patient_mtds_markdown.func(self.mock_patient_runtime)
        unloaded_reader.read_document.assert_called_once()
        self.assertEqual(
            result,
            "=== FICHE RCP : rcp_lazy.pdf ===\n# Lazily Loaded PatientRecord Entry",
        )

    def test_get_patient_mtds_markdown_success(self):
        result = get_patient_mtds_markdown.func(self.mock_patient_runtime)
        expected = (
            "=== FICHE RCP : rcp1.pdf ===\n# Mock Markdown Patient Record\n\n"
            "=== FICHE RCP : rcp2.pdf ===\n# Follow-up Patient Record"
        )
        self.assertEqual(result, expected)
        self.mock_logger.info.assert_called_with(
            "tool get_patient_mtds_markdown called"
        )

    def test_get_patient_ai_history_success(self):
        result = get_patient_ai_history.func(self.mock_patient_runtime)
        self.assertIn(
            "=== HISTORIQUE IA — FICHE RCP : rcp1.pdf (Date RCP : 2025-01-15) ===",
            result,
        )
        self.assertIn('"tumor_location": "Pancreas"', result)
        self.assertIn(
            "=== HISTORIQUE IA — FICHE RCP : rcp2.pdf (Date RCP : 2026-03-18) ===",
            result,
        )
        self.assertIn('"intervention_type": "Chirurgie"', result)
        self.mock_logger.info.assert_called_with("tool get_patient_ai_history called")

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

    def test_search_on_patient_mtds_success(self):
        doc1 = Document(page_content="Initial diagnosis", metadata={"file": "rcp1.pdf"})
        doc2 = Document(page_content="Second line chemo", metadata={"file": "rcp2.pdf"})
        self.mock_clientdb.max_marginal_relevance_search.return_value = [doc1]
        self.mock_clientdb2.max_marginal_relevance_search.return_value = [doc2]

        serialized, docs = search_on_patient_mtds.func(
            self.mock_patient_runtime,
            query="chemotherapy",
            k=1,
        )

        self.assertEqual(len(docs), 2)
        self.assertIn("Initial diagnosis", serialized)
        self.assertIn("Second line chemo", serialized)

    def test_search_on_ressources_success(self):
        # Setup mock documents from additional reader
        doc = Document(
            page_content="TNCD pancreas guidelines", metadata={"section": "TNCD"}
        )
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
        expected_serialized = (
            "Source: {'section': 'TNCD'}\nContent: TNCD pancreas guidelines"
        )
        self.assertEqual(serialized, expected_serialized)

    def test_search_on_ressources_empty(self):
        self.mock_add_clientdb.max_marginal_relevance_search.return_value = []

        serialized, docs = search_on_ressources.func(
            self.mock_runtime,
            query="non-existent info",
        )

        self.assertEqual(serialized, "No additionnal ressources provided")
        self.assertEqual(docs, [])
