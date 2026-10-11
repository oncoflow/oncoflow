import unittest
from unittest.mock import MagicMock, patch
from langchain_core.documents import Document

from src.application.reader import DocumentReader


class TestReaderCache(unittest.TestCase):
    def setUp(self):
        self.mock_config = MagicMock()
        self.mock_config.rcp.path = "/tmp/rcp"
        self.mock_config.rcp.additional_path = "/tmp/rcp_add"
        self.mock_config.rcp.display_type = "mongodb"
        self.mock_config.rcp.doc_type = "docling"
        self.mock_config.llm.embeddings = "nomic-embed-text"

        self.mock_logger = MagicMock()
        self.mock_config.set_logger.return_value = self.mock_logger

    @patch("os.path.exists", return_value=True)
    @patch.object(DocumentReader, "calculate_file_hash", return_value="dummy_hash_123")
    @patch("src.infrastructure.documents.mongodb.Mongodb")
    @patch.object(DocumentReader, "_load_document")
    def test_read_document_cache_hit_and_indexed(
        self, mock_load_doc, mock_mongodb_cls, mock_hash, mock_exists
    ):
        mock_mongo = mock_mongodb_cls.return_value
        mock_mongo.get_document_cache.return_value = {
            "hash": "dummy_hash_123",
            "file": "test.pdf",
            "markdown": "# Cached Markdown",
        }

        mock_vecdb = MagicMock()
        mock_vecdb.is_indexed.return_value = True

        mock_llm = MagicMock()
        mock_llm.embedding = MagicMock()

        reader = DocumentReader(
            config=self.mock_config,
            document="test.pdf",
            vecdb_client=mock_vecdb,
            llm_client=mock_llm,
        )

        reader.read_document()

        # Check that cache hit restored markdown
        self.assertEqual(len(reader.markdown_exporter), 1)
        self.assertEqual(reader.markdown_exporter[0].page_content, "# Cached Markdown")
        self.assertEqual(
            reader.markdown_exporter[0].metadata["file_hash"], "dummy_hash_123"
        )

        # Verify loader and vecdb.add were NOT called because cache HIT and already indexed
        mock_load_doc.assert_not_called()
        mock_vecdb.add_chunked_to_collection.assert_not_called()

    @patch("os.path.exists", return_value=True)
    @patch.object(DocumentReader, "calculate_file_hash", return_value="dummy_hash_456")
    @patch("src.infrastructure.documents.mongodb.Mongodb")
    @patch.object(DocumentReader, "_load_document")
    def test_read_document_cache_miss_populates_cache(
        self, mock_load_doc, mock_mongodb_cls, mock_hash, mock_exists
    ):
        mock_mongo = mock_mongodb_cls.return_value
        mock_mongo.get_document_cache.return_value = None  # Cache MISS

        mock_doc = Document(page_content="Extracted chunk", metadata={})
        mock_load_doc.return_value = [mock_doc]

        mock_vecdb = MagicMock()
        mock_vecdb.is_indexed.return_value = False

        mock_llm = MagicMock()
        mock_llm.embedding = MagicMock()

        reader = DocumentReader(
            config=self.mock_config,
            document="test.pdf",
            vecdb_client=mock_vecdb,
            llm_client=mock_llm,
        )
        # Mock markdown_exporter populated during loader
        reader.markdown_exporter = [
            Document(page_content="# Extracted Markdown", metadata={})
        ]

        reader.read_document()

        mock_load_doc.assert_called_once_with(reader.document_path)
        mock_vecdb.add_chunked_to_collection.assert_called_once()
        mock_mongo.save_document_cache.assert_called_once_with(
            file_hash="dummy_hash_456",
            file_name="test.pdf",
            markdown="# Extracted Markdown",
            document_type="mtd",
        )

    @patch("os.path.exists", return_value=True)
    @patch.object(DocumentReader, "calculate_file_hash", return_value="dummy_hash_789")
    @patch("src.infrastructure.documents.mongodb.Mongodb")
    @patch.object(DocumentReader, "_load_document")
    def test_read_document_force_reload_bypasses_cache(
        self, mock_load_doc, mock_mongodb_cls, mock_hash, mock_exists
    ):
        mock_mongo = mock_mongodb_cls.return_value
        mock_load_doc.return_value = [Document(page_content="Chunks", metadata={})]

        mock_vecdb = MagicMock()
        mock_vecdb.is_indexed.return_value = True

        mock_llm = MagicMock()
        mock_llm.embedding = MagicMock()

        reader = DocumentReader(
            config=self.mock_config,
            document="test.pdf",
            vecdb_client=mock_vecdb,
            llm_client=mock_llm,
        )

        reader.read_document(force_reload=True)

        # When force_reload is True, get_document_cache should NOT be consulted
        mock_mongo.get_document_cache.assert_not_called()
        mock_load_doc.assert_called_once()

    @patch("os.path.exists", return_value=True)
    @patch.object(DocumentReader, "calculate_file_hash", return_value="hash_dedicated")
    @patch("src.infrastructure.documents.mongodb.Mongodb")
    def test_dedicated_cache_methods(self, mock_mongodb_cls, mock_hash, mock_exists):
        mock_mongo = mock_mongodb_cls.return_value
        mock_mongo.get_document_cache.return_value = {
            "hash": "hash_dedicated",
            "file": "sample.pdf",
            "markdown": "# Dedicated Markdown",
        }

        mock_vecdb = MagicMock()
        mock_llm = MagicMock()
        mock_llm.embedding = MagicMock()

        reader = DocumentReader(
            config=self.mock_config,
            document="sample.pdf",
            vecdb_client=mock_vecdb,
            llm_client=mock_llm,
        )

        # 1. Test _get_cached_document
        entry = reader._get_cached_document()
        self.assertIsNotNone(entry)
        self.assertEqual(entry["markdown"], "# Dedicated Markdown")
        mock_mongo.get_document_cache.assert_called_with("hash_dedicated")

        # 2. Test _restore_from_cache
        reader._restore_from_cache(entry)
        self.assertEqual(
            reader.markdown_exporter[0].page_content, "# Dedicated Markdown"
        )

        # 3. Test _save_to_cache
        reader._save_to_cache("# New Content")
        mock_mongo.save_document_cache.assert_called_with(
            file_hash="hash_dedicated",
            file_name="sample.pdf",
            markdown="# New Content",
            document_type="mtd",
        )

        # 4. Test clear_cache
        reader.clear_cache()
        mock_mongo.delete_document_cache.assert_called_with(
            file_hash="hash_dedicated", file_name="sample.pdf"
        )
