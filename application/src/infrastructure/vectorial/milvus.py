import uuid
import time
from langchain_milvus import Milvus
from langchain_core.documents import Document
from src.infrastructure.vectorial.database import VectorialDataBase
from src.application.config import AppConfig


from pymilvus import MilvusException, connections, db, utility


class MilvusDB(VectorialDataBase):
    def init_client(self, config=AppConfig):
        retry = 3
        for r in range(retry):
            try:
                connections.connect(
                    host=config.milvus.host, port=config.milvus.port
                )
                self.uri = f"http://{config.milvus.host}:{config.milvus.port}"
                self.token = config.milvus.token
                self.database = config.milvus.database

                try:
                    existing_databases = db.list_database()
                    if config.milvus.database not in existing_databases:
                        db.create_database(self.database)
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
