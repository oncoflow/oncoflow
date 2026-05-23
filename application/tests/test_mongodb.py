import unittest
from unittest.mock import MagicMock, patch

from src.application.config import AppConfig
from src.infrastructure.documents.mongodb import Mongodb


class TestMongodbDocumentStore(unittest.TestCase):
    def setUp(self):
        # Configure a mock config object
        self.mock_config = MagicMock(spec=AppConfig)
        self.mock_config.mongodb.host = "127.0.0.1"
        self.mock_config.mongodb.port = "27017"
        self.mock_config.mongodb.user = "root"
        self.mock_config.mongodb.password = "password"
        self.mock_config.mongodb.database = "TestOncoflow"

        # Mock logger
        self.mock_logger = MagicMock()
        self.mock_config.set_logger.return_value = self.mock_logger

    @patch("src.infrastructure.documents.mongodb.MongoClient")
    def test_init_success(self, mock_mongo_client_cls):
        mock_client = mock_mongo_client_cls.return_value
        db = Mongodb(self.mock_config)

        # Asserts connection string & db name
        expected_conn_str = "mongodb://root:password@127.0.0.1:27017"
        mock_mongo_client_cls.assert_called_once_with(expected_conn_str)
        self.assertEqual(db.database, mock_client[self.mock_config.mongodb.database])
        self.mock_logger.info.assert_called_with("Succefully init")

    @patch("src.infrastructure.documents.mongodb.MongoClient")
    def test_close(self, mock_mongo_client_cls):
        mock_client = mock_mongo_client_cls.return_value
        db = Mongodb(self.mock_config)
        db.close()
        mock_client.close.assert_called_once()

    @patch("src.infrastructure.documents.mongodb.MongoClient")
    def test_set_uniq_index(self, mock_mongo_client_cls):
        db = Mongodb(self.mock_config)

        mock_collection = MagicMock()
        db.database.__getitem__.return_value = mock_collection

        db.set_uniq_index("rcp_info", "file")
        db.database.__getitem__.assert_called_with("rcp_info")
        mock_collection.create_index.assert_called_once_with("file", unique=True)

    @patch("src.infrastructure.documents.mongodb.MongoClient")
    def test_get_document(self, mock_mongo_client_cls):
        db = Mongodb(self.mock_config)

        mock_collection = MagicMock()
        db.database.__getitem__.return_value = mock_collection
        mock_collection.find_one.return_value = {"file": "PDF1.pdf"}

        result = db.get_document("rcp_info", {"file": "PDF1.pdf"})
        self.assertEqual(result, {"file": "PDF1.pdf"})
        mock_collection.find_one.assert_called_once_with({"file": "PDF1.pdf"})

    @patch("src.infrastructure.documents.mongodb.MongoClient")
    def test_update_doc(self, mock_mongo_client_cls):
        db = Mongodb(self.mock_config)

        mock_collection = MagicMock()
        db.database.__getitem__.return_value = mock_collection

        db.update_doc("rcp_info", {"file": "PDF1.pdf"}, {"age": 67})
        mock_collection.update_one.assert_called_once_with(
            {"file": "PDF1.pdf"}, {"$set": {"age": 67}}, upsert=True
        )

    @patch("src.infrastructure.documents.mongodb.MongoClient")
    def test_insert_docs(self, mock_mongo_client_cls):
        mock_client = mock_mongo_client_cls.return_value
        db = Mongodb(self.mock_config)

        mock_collection = MagicMock()
        db.database.__getitem__.return_value = mock_collection

        # Prepare and insert doc
        db.prepare_insert_doc("rcp_info", {"file": "PDF1.pdf"})
        db.insert_docs()

        mock_collection.insert_many.assert_called_once_with([{"file": "PDF1.pdf"}])
        mock_client.close.assert_called_once()

    @patch("src.infrastructure.documents.mongodb.MongoClient")
    def test_delete_docs(self, mock_mongo_client_cls):
        db = Mongodb(self.mock_config)

        mock_collection1 = MagicMock()
        mock_collection2 = MagicMock()
        db.database.__getitem__.side_effect = [mock_collection1, mock_collection2]

        db.delete_docs(["rcp_info", "rcp_metadata"], {"file": "PDF1.pdf"})
        mock_collection1.delete_many.assert_called_once_with({"file": "PDF1.pdf"})
        mock_collection2.delete_many.assert_called_once_with({"file": "PDF1.pdf"})
