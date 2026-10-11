import unittest
from unittest.mock import MagicMock, patch

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from pymilvus import MilvusException, connections
from src.infrastructure.vectorial.milvus import MilvusDB


class TestMilvusVectorialDB(unittest.TestCase):
    def setUp(self):
        self.mock_config = MagicMock()
        self.mock_config.dbvec.type = "milvus"
        self.mock_config.dbvec.collection = "oncoflowDocs"
        self.mock_config.llm.type = "ollama"
        self.mock_config.llm.embeddings = "all-MiniLM-L6-v2"
        self.mock_config.milvus.host = "localhost"
        self.mock_config.milvus.port = "19530"
        self.mock_config.milvus.token = "root:Milvus"
        self.mock_config.milvus.database = "oncowflow"

        self.mock_logger = MagicMock()
        self.mock_config.set_logger.return_value = self.mock_logger

        self.mock_embeddings = MagicMock(spec=Embeddings)
        self.mock_llm_client = MagicMock()
        self.mock_llm_client.embedding = self.mock_embeddings

    @patch("src.infrastructure.vectorial.database.get_llm_client")
    @patch("src.infrastructure.vectorial.milvus.Milvus")
    @patch("src.infrastructure.vectorial.milvus.db")
    @patch("src.infrastructure.vectorial.milvus.connections")
    @patch("src.infrastructure.vectorial.milvus.utility")
    def test_milvus_db_creates_database_if_not_exists(
        self,
        mock_utility,
        mock_connections,
        mock_db,
        mock_milvus_cls,
        mock_get_llm_client,
    ):
        mock_get_llm_client.return_value = self.mock_llm_client
        mock_db.list_database.return_value = ["default"]

        db_wrapper = MilvusDB(self.mock_config)

        mock_connections.connect.assert_called_once_with(
            host="localhost", port="19530", token="root:Milvus"
        )
        mock_db.create_database.assert_called_once_with("oncowflow")
        mock_db.using_database.assert_called_once_with("oncowflow", using="default")
        self.assertEqual(db_wrapper.database, "oncowflow")
        self.assertEqual(db_wrapper.coll_name, "oncoflowDocs_all_MiniLM_L6_v2")

    @patch("src.infrastructure.vectorial.database.get_llm_client")
    @patch("src.infrastructure.vectorial.milvus.Milvus")
    @patch("src.infrastructure.vectorial.milvus.db")
    @patch("src.infrastructure.vectorial.milvus.connections")
    @patch("src.infrastructure.vectorial.milvus.utility")
    def test_milvus_db_skips_create_database_if_already_exists(
        self,
        mock_utility,
        mock_connections,
        mock_db,
        mock_milvus_cls,
        mock_get_llm_client,
    ):
        mock_get_llm_client.return_value = self.mock_llm_client
        mock_db.list_database.return_value = ["default", "oncowflow"]

        MilvusDB(self.mock_config)

        mock_db.create_database.assert_not_called()
        mock_db.using_database.assert_called_once_with("oncowflow", using="default")

    @patch("src.infrastructure.vectorial.database.get_llm_client")
    @patch("src.infrastructure.vectorial.milvus.Milvus")
    @patch("src.infrastructure.vectorial.milvus.db")
    @patch("src.infrastructure.vectorial.milvus.connections")
    @patch("src.infrastructure.vectorial.milvus.utility")
    @patch("src.infrastructure.vectorial.milvus.time.sleep")
    def test_milvus_db_init_retry_on_milvus_exception(
        self,
        mock_sleep,
        mock_utility,
        mock_connections,
        mock_db,
        mock_milvus_cls,
        mock_get_llm_client,
    ):
        mock_get_llm_client.return_value = self.mock_llm_client
        mock_db.list_database.return_value = ["oncowflow"]

        # Fail once, then succeed
        mock_connections.connect.side_effect = [
            MilvusException("Milvus starting"),
            None,
        ]

        MilvusDB(self.mock_config)

        self.assertEqual(mock_connections.connect.call_count, 2)
        mock_sleep.assert_called_once_with(5)

    def test_monkeypatch_fetch_handler_fallback(self):
        mock_handler = MagicMock()
        connections._alias_handlers["default"] = mock_handler

        # Unknown alias should fall back to default
        result = connections._fetch_handler("cm-unknown-client-alias")
        self.assertEqual(result, mock_handler)

        # None alias should fall back to default
        result_none = connections._fetch_handler(None)
        self.assertEqual(result_none, mock_handler)

    def test_monkeypatch_generate_call_context_fallback(self):
        connections._alias_config["default"] = {
            "address": "localhost:19530",
            "db_name": "oncowflow",
        }

        # Unknown alias (e.g. from MilvusClient) should fall back to default db_name
        ctx = connections._generate_call_context("cm-unknown-alias")
        self.assertEqual(ctx.get_db_name(), "oncowflow")
        grpc_metadata = dict(ctx.to_grpc_metadata())
        self.assertEqual(grpc_metadata.get("dbname"), "oncowflow")

    @patch("src.infrastructure.vectorial.database.get_llm_client")
    @patch("src.infrastructure.vectorial.milvus.Milvus")
    @patch("src.infrastructure.vectorial.milvus.db")
    @patch("src.infrastructure.vectorial.milvus.connections")
    @patch("src.infrastructure.vectorial.milvus.utility")
    def test_is_indexed_when_documents_exist(
        self,
        mock_utility,
        mock_connections,
        mock_db,
        mock_milvus_cls,
        mock_get_llm_client,
    ):
        mock_get_llm_client.return_value = self.mock_llm_client
        mock_db.list_database.return_value = ["oncowflow"]

        mock_milvus_instance = MagicMock()
        mock_milvus_cls.return_value = mock_milvus_instance
        mock_client = MagicMock()
        mock_milvus_instance.client = mock_client

        mock_client.has_collection.return_value = True
        mock_client.query.return_value = [{"id": "1", "text": "sample"}]

        db_wrapper = MilvusDB(self.mock_config)
        self.assertTrue(db_wrapper.is_indexed())

    @patch("src.infrastructure.vectorial.database.get_llm_client")
    @patch("src.infrastructure.vectorial.milvus.Milvus")
    @patch("src.infrastructure.vectorial.milvus.db")
    @patch("src.infrastructure.vectorial.milvus.connections")
    @patch("src.infrastructure.vectorial.milvus.utility")
    def test_is_indexed_loads_collection_on_not_loaded_error(
        self,
        mock_utility,
        mock_connections,
        mock_db,
        mock_milvus_cls,
        mock_get_llm_client,
    ):
        mock_get_llm_client.return_value = self.mock_llm_client
        mock_db.list_database.return_value = ["oncowflow"]

        mock_milvus_instance = MagicMock()
        mock_milvus_cls.return_value = mock_milvus_instance
        mock_client = MagicMock()
        mock_milvus_instance.client = mock_client

        mock_client.has_collection.return_value = True
        mock_client.query.side_effect = [
            MilvusException("collection not loaded"),
            [{"id": "1"}],
        ]

        db_wrapper = MilvusDB(self.mock_config)
        self.assertTrue(db_wrapper.is_indexed())
        mock_client.load_collection.assert_called_once_with(
            collection_name=db_wrapper.coll_name
        )

    @patch("src.infrastructure.vectorial.database.get_llm_client")
    @patch("src.infrastructure.vectorial.milvus.Milvus")
    @patch("src.infrastructure.vectorial.milvus.db")
    @patch("src.infrastructure.vectorial.milvus.connections")
    @patch("src.infrastructure.vectorial.milvus.utility")
    def test_is_indexed_false_when_collection_not_found(
        self,
        mock_utility,
        mock_connections,
        mock_db,
        mock_milvus_cls,
        mock_get_llm_client,
    ):
        mock_get_llm_client.return_value = self.mock_llm_client
        mock_db.list_database.return_value = ["oncowflow"]

        mock_milvus_instance = MagicMock()
        mock_milvus_cls.return_value = mock_milvus_instance
        mock_client = MagicMock()
        mock_milvus_instance.client = mock_client

        mock_client.has_collection.return_value = False
        mock_utility.has_collection.return_value = False

        db_wrapper = MilvusDB(self.mock_config)
        self.assertFalse(db_wrapper.is_indexed())

    @patch("src.infrastructure.vectorial.database.get_llm_client")
    @patch("src.infrastructure.vectorial.milvus.Milvus")
    @patch("src.infrastructure.vectorial.milvus.db")
    @patch("src.infrastructure.vectorial.milvus.connections")
    @patch("src.infrastructure.vectorial.milvus.utility")
    def test_add_to_collection_success(
        self,
        mock_utility,
        mock_connections,
        mock_db,
        mock_milvus_cls,
        mock_get_llm_client,
    ):
        mock_get_llm_client.return_value = self.mock_llm_client
        mock_db.list_database.return_value = ["oncowflow"]

        mock_milvus_instance = MagicMock()
        mock_milvus_cls.return_value = mock_milvus_instance

        db_wrapper = MilvusDB(self.mock_config)
        doc = Document(
            page_content="Medical report content", metadata={"patient": "P123"}
        )

        db_wrapper.add_to_collection(doc, flush_before=False)

        mock_milvus_instance.add_documents.assert_called_once()
        call_kwargs = mock_milvus_instance.add_documents.call_args[1]
        self.assertEqual(len(call_kwargs["documents"]), 1)
        self.assertEqual(
            call_kwargs["documents"][0].page_content, "Medical report content"
        )

    @patch("src.infrastructure.vectorial.database.get_llm_client")
    @patch("src.infrastructure.vectorial.milvus.Milvus")
    @patch("src.infrastructure.vectorial.milvus.db")
    @patch("src.infrastructure.vectorial.milvus.connections")
    @patch("src.infrastructure.vectorial.milvus.utility")
    @patch("src.infrastructure.vectorial.milvus.time.sleep")
    def test_add_to_collection_retries_on_partition_error(
        self,
        mock_sleep,
        mock_utility,
        mock_connections,
        mock_db,
        mock_milvus_cls,
        mock_get_llm_client,
    ):
        mock_get_llm_client.return_value = self.mock_llm_client
        mock_db.list_database.return_value = ["oncowflow"]

        mock_milvus_instance = MagicMock()
        mock_milvus_cls.return_value = mock_milvus_instance
        mock_milvus_instance.add_documents.side_effect = [
            MilvusException("partition not found"),
            None,
        ]

        db_wrapper = MilvusDB(self.mock_config)
        doc = Document(page_content="Medical report", metadata={"patient": "P123"})

        db_wrapper.add_to_collection(doc)

        self.assertEqual(mock_milvus_instance.add_documents.call_count, 2)
        mock_sleep.assert_called_once_with(2.0)

    @patch("src.infrastructure.vectorial.database.get_llm_client")
    @patch("src.infrastructure.vectorial.milvus.Milvus")
    @patch("src.infrastructure.vectorial.milvus.db")
    @patch("src.infrastructure.vectorial.milvus.connections")
    @patch("src.infrastructure.vectorial.milvus.utility")
    @patch("src.infrastructure.vectorial.milvus.time.sleep")
    def test_set_clientdb_flush_true_drops_collection(
        self,
        mock_sleep,
        mock_utility,
        mock_connections,
        mock_db,
        mock_milvus_cls,
        mock_get_llm_client,
    ):
        mock_get_llm_client.return_value = self.mock_llm_client
        mock_db.list_database.return_value = ["oncowflow"]
        mock_utility.has_collection.return_value = True

        db_wrapper = MilvusDB(self.mock_config)
        db_wrapper.set_clientdb(flush=True)

        mock_utility.drop_collection.assert_called_with(db_wrapper.coll_name)
        mock_sleep.assert_called_with(2.0)

    @patch("src.infrastructure.vectorial.database.get_llm_client")
    @patch("src.infrastructure.vectorial.milvus.Milvus")
    @patch("src.infrastructure.vectorial.milvus.db")
    @patch("src.infrastructure.vectorial.milvus.connections")
    @patch("src.infrastructure.vectorial.milvus.utility")
    def test_get_version_and_embedding(
        self,
        mock_utility,
        mock_connections,
        mock_db,
        mock_milvus_cls,
        mock_get_llm_client,
    ):
        mock_get_llm_client.return_value = self.mock_llm_client
        mock_db.list_database.return_value = ["oncowflow"]
        mock_utility.get_server_version.return_value = "2.6.24"

        db_wrapper = MilvusDB(self.mock_config)

        self.assertEqual(db_wrapper.get_version(), "2.6.24")
        self.assertEqual(db_wrapper.get_embedding(), db_wrapper.llm_embeddings)
