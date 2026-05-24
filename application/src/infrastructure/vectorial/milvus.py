import uuid
import time
import inspect
import warnings
from langchain_milvus import Milvus
from langchain_core.documents import Document
from src.infrastructure.vectorial.database import VectorialDataBase
from src.application.config import AppConfig


from pymilvus import MilvusException, connections, db, utility
from pymilvus.exceptions import ConnectionNotExistException


try:
    import pymilvus.exceptions as pymilvus_exceptions

    PyMilvusDeprecationWarning = getattr(
        pymilvus_exceptions, "PyMilvusDeprecationWarning", None
    )
    if PyMilvusDeprecationWarning is not None:
        warnings.filterwarnings("ignore", category=PyMilvusDeprecationWarning)
except ImportError:
    pass

# Monkeypatch PyMilvus connection manager to seamlessly route generated MilvusClient connections
# to the ORM 'default' connection. This is necessary because MilvusClient in Milvus v2.5+
# generates unique connection aliases that are not registered in the legacy ORM connections manager,
# causing ConnectionNotExistException and database context mismatches (SchemaNotReadyException)
# when used alongside legacy ORM Collection objects.
original_fetch_handler = connections._fetch_handler
original_generate_call_context = connections._generate_call_context


def patched_fetch_handler(alias=None):
    if alias is None:
        alias = "default"
    try:
        return original_fetch_handler(alias)
    except ConnectionNotExistException:
        if "default" in connections._alias_handlers:
            return connections._alias_handlers["default"]
        raise


def patched_generate_call_context(alias, **kwargs):
    if alias not in connections._alias_config:
        alias = "default"
    return original_generate_call_context(alias, **kwargs)


connections._fetch_handler = patched_fetch_handler
connections._generate_call_context = patched_generate_call_context


# Monkeypatch Milvus.drop to prevent unawaited coroutine warning in AsyncMilvusClient._get_connection
original_drop = Milvus.drop


def patched_drop(self) -> None:
    if self.client.has_collection(self.collection_name):
        self.client.drop_collection(self.collection_name)
        self._col_cache = None
        self._cache_key = None

        try:
            conn = self.client._get_connection()
            if (
                hasattr(conn, "schema_cache")
                and self.collection_name in conn.schema_cache
            ):
                conn.schema_cache.pop(self.collection_name, None)
        except Exception:
            pass

        if self._async_milvus_client is not None:
            try:
                async_conn = self._async_milvus_client._get_connection()
                if inspect.iscoroutine(async_conn):
                    async_conn.close()
                elif (
                    hasattr(async_conn, "schema_cache")
                    and self.collection_name in async_conn.schema_cache
                ):
                    async_conn.schema_cache.pop(self.collection_name, None)
            except Exception:
                pass


Milvus.drop = patched_drop


class MilvusDB(VectorialDataBase):
    def init_client(self, config: AppConfig):
        retry = 3
        for r in range(retry):
            try:
                connections.connect(host=config.milvus.host, port=config.milvus.port)
                self.uri = f"http://{config.milvus.host}:{config.milvus.port}"
                self.token = config.milvus.token
                self.database = config.milvus.database

                try:
                    existing_databases = db.list_database()
                    if config.milvus.database not in existing_databases:
                        db.create_database(self.database)
                    db.using_database(self.database, using="default")
                    break

                except MilvusException as e:
                    self.logger.error(f"An error occurred: {e}")
            except MilvusException:
                self.logger.info("Milvus still start, wait")
                time.sleep(5)

    def get_embedding(self):
        return self.llm_embeddings

    def set_clientdb(
        self,
        flush=False,
    ):

        self.clientdb = Milvus(
            embedding_function=self.embeddings,
            collection_name=self.coll_name,
            connection_args={
                "uri": self.uri,
                "token": self.token,
                "db_name": self.database,
            },
            index_params={"index_type": "FLAT", "metric_type": "L2"},
            consistency_level="Strong",
            drop_old=flush,  # set to True if seeking to drop the collection with that name if it exists
        )

    def get_version(self):
        return utility.get_server_version()

    def is_indexed(self) -> bool:
        try:
            self.set_clientdb()
            if hasattr(self.clientdb, "client") and self.clientdb.client is not None:
                client = self.clientdb.client
                if client.has_collection(self.coll_name):
                    try:
                        res = client.query(
                            collection_name=self.coll_name, filter="", limit=1
                        )
                        return len(res) > 0
                    except MilvusException as e:
                        if "not loaded" in str(e).lower() or "load" in str(e).lower():
                            try:
                                client.load_collection(collection_name=self.coll_name)
                                res = client.query(
                                    collection_name=self.coll_name, filter="", limit=1
                                )
                                return len(res) > 0
                            except Exception:
                                pass
                        try:
                            stats = client.get_collection_stats(
                                collection_name=self.coll_name
                            )
                            return stats.get("row_count", 0) > 0
                        except Exception:
                            pass
            if utility.has_collection(self.coll_name):
                return True
            return False
        except Exception:
            return False

    def add_to_collection(self, doc, flush_before=False):
        """
        Adds a document to the collection.

        Args:
        - doc (object): The document to be added.
        - flush_before (bool, optional): Whether to flush and recreate the clientdb before adding the document. Defaults to False.

        Returns: None
        """
        if flush_before:
            # Flush and recreate the clientdb before adding the document.
            self.set_clientdb(flush=True)

        # Add the document to the collection with metadata and page content.
        doc = Document(metadatas=doc.metadata, page_content=doc.page_content)

        self.clientdb.add_documents(ids=[str(uuid.uuid1())], documents=[doc])
