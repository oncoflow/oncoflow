import chromadb

from chromadb.utils.embedding_functions.chroma_langchain_embedding_function import (
    create_langchain_embedding,
)

from langchain_chroma import Chroma


from src.application.config import AppConfig
from src.infrastructure.vectorial.database import VectorialDataBase


class Chromadb(VectorialDataBase):
    def init_client(self, config=AppConfig):
        if config.chromadb.client == "HttpClient":
            self.client = chromadb.HttpClient(
                host=config.chromadb.host, port=config.chromadb.port
            )
        elif config.chromadb.client == "PersistentClient":
            self.client = chromadb.PersistentClient()
        # Clear system cache and get or create a collection based on the configuration.
        self.client.clear_system_cache()

    def get_embedding(self):
        return create_langchain_embedding(self.llm_embeddings)

    def set_clientdb(
        self,
        flush=False,
    ):
        if flush:
            # Delete and recreate the collection based on the configuration.
            try:
                self.logger.debug("Flushing collection")
                self.client.delete_collection(self.coll_name)
                self.client.clear_system_cache()
            except Exception:
                pass
        self.collection = self.client.get_or_create_collection(
            self.coll_name,
            embedding_function=self.embeddings,
        )
        # Create a Chroma clientdb using the initialized client, collection and embeddings.
        self.clientdb = Chroma(
            client=self.client,
            collection_name=self.coll_name,
            embedding_function=self.embeddings,
        )
        self.client.get_collection(
            self.coll_name,
            embedding_function=self.embeddings,
        )
