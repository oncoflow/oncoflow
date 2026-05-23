import unittest
from unittest.mock import MagicMock, patch

from langchain_core.embeddings import Embeddings
from src.application.config import AppConfig
from src.infrastructure.vectorial.client import VectorialDataBaseClient
from src.infrastructure.vectorial.chromadb import Chromadb
from src.infrastructure.vectorial.milvus import MilvusDB
from src.infrastructure.vectorial.mongodb import Mongodb as MongoDBVectorDB


class TestVectorialDatabases(unittest.TestCase):
    def setUp(self):
        # Configure a generic mock config
        self.mock_config = MagicMock(spec=AppConfig)
        self.mock_config.dbvec.type = "milvus"
        self.mock_config.dbvec.collection = "oncoflowDocs"
        self.mock_config.llm.type = "ollama"
        self.mock_config.llm.embeddings = "all-MiniLM-L6-v2"
        self.mock_config.set_logger.return_value = MagicMock()

        # Chroma config
        self.mock_config.chromadb.client = "PersistentClient"
        self.mock_config.chromadb.host = "localhost"
        self.mock_config.chromadb.port = "8000"

        # Milvus config
        self.mock_config.milvus.host = "localhost"
        self.mock_config.milvus.port = "19530"
        self.mock_config.milvus.token = "root:Milvus"
        self.mock_config.milvus.database = "oncowflow"

        # MongoDB config
        self.mock_config.mongodb.user = "root"
        self.mock_config.mongodb.password = "password"
        self.mock_config.mongodb.host = "127.0.0.1"
        self.mock_config.mongodb.port = "27017"
        self.mock_config.mongodb.vectordatabase = "OncoflowVector"

        # Mock Ollama embedding (spec=Embeddings resolves Chroma isinstance checking)
        self.mock_embeddings = MagicMock(spec=Embeddings)
        self.mock_llm_client = MagicMock()
        self.mock_llm_client.embedding = self.mock_embeddings

    @patch("src.infrastructure.vectorial.database.get_llm_client")
    @patch("src.infrastructure.vectorial.milvus.Milvus")
    @patch("src.infrastructure.vectorial.milvus.db")
    @patch("src.infrastructure.vectorial.milvus.connections")
    @patch("src.infrastructure.vectorial.milvus.utility")
    def test_milvus_db_initialization(
        self,
        mock_utility,
        mock_connections,
        mock_db,
        mock_milvus_cls,
        mock_get_llm_client,
    ):
        mock_get_llm_client.return_value = self.mock_llm_client
        mock_db.list_database.return_value = ["oncowflow"]
        mock_utility.get_server_version.return_value = "2.5.0"

        self.mock_config.dbvec.type = "milvus"
        db_wrapper = MilvusDB(self.mock_config)

        # Assert correct collection name and client parameters
        self.assertEqual(db_wrapper.coll_name, "oncoflowDocs_all_MiniLM_L6_v2")
        mock_connections.connect.assert_called_once_with(host="localhost", port="19530")
        mock_milvus_cls.assert_called_once()
        self.assertEqual(db_wrapper.embeddings, self.mock_embeddings)

    @patch("src.infrastructure.vectorial.database.get_llm_client")
    @patch("src.infrastructure.vectorial.chromadb.Chroma")
    @patch("src.infrastructure.vectorial.chromadb.chromadb.PersistentClient")
    def test_chroma_db_initialization(
        self, mock_chroma_client_cls, mock_chroma_cls, mock_get_llm_client
    ):
        mock_get_llm_client.return_value = self.mock_llm_client

        self.mock_config.dbvec.type = "chromadb"
        db_wrapper = Chromadb(self.mock_config, coll_prefix="test")

        self.assertEqual(db_wrapper.coll_name, "test_oncoflowDocs_all_MiniLM_L6_v2")
        mock_chroma_client_cls.assert_called_once()
        mock_chroma_cls.assert_called_once()

    @patch("src.infrastructure.vectorial.database.get_llm_client")
    @patch("src.infrastructure.vectorial.mongodb.MongoDBAtlasVectorSearch")
    @patch("src.infrastructure.vectorial.mongodb.MongoClient")
    def test_mongodb_vector_db_initialization(
        self, mock_mongo_client_cls, mock_vector_search_cls, mock_get_llm_client
    ):
        mock_get_llm_client.return_value = self.mock_llm_client

        self.mock_config.dbvec.type = "mongodb"
        db_wrapper = MongoDBVectorDB(self.mock_config)

        self.assertEqual(db_wrapper.coll_name, "oncoflowDocs_all_MiniLM_L6_v2")
        mock_mongo_client_cls.assert_called_once_with(
            "mongodb://root:password@127.0.0.1:27017"
        )
        mock_vector_search_cls.assert_called_once()

    @patch("src.infrastructure.vectorial.database.get_llm_client")
    @patch("src.infrastructure.vectorial.client.MilvusDB")
    def test_vectorial_database_client_factory(
        self, mock_milvus_db_cls, mock_get_llm_client
    ):
        self.mock_config.dbvec.type = "milvus"

        client = VectorialDataBaseClient(self.mock_config)

        mock_milvus_db_cls.assert_called_once_with(self.mock_config, None)
        self.assertEqual(client.vectordb, mock_milvus_db_cls.return_value)
