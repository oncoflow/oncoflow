import chromadb
import uuid

from typing import List, Union

from chromadb.utils.embedding_functions import create_langchain_embedding

from langchain_chroma import Chroma

from langchain_core.vectorstores import VectorStoreRetriever

from src.application.config import AppConfig
from src.application.llm import Llm

# Define a class for working with vectorial databases.


class VectorialDataBase:
    client = None

    # Initialize the client, collection and embeddings based on configuration.
    """Initialize the client, collection and embeddings based on configuration."""

    def __init__(self, config=AppConfig, coll_prefix=None):
        if config.dbvec.type.lower() == "chromadb":
            # Use either HttpClient or PersistentClient depending on the configuration.
            if config.dbvec.client == "HttpClient":
                self.client = chromadb.HttpClient(
                    host=config.dbvec.host, port=config.dbvec.port
                )
            elif config.dbvec.client == "PersistentClient":
                self.client = chromadb.PersistentClient()
            # Clear system cache and get or create a collection based on the configuration.
            self.client.clear_system_cache()
            if coll_prefix is None:
                self.coll_name = config.dbvec.collection
            else:
                self.coll_name = f"{coll_prefix}_{config.dbvec.collection}"

            # self.embeddings = HuggingFaceEmbeddings(model_name=config.dbvec.model)
            self.embeddings = create_langchain_embedding(
                Llm(config, embeddings=True).embeddings
            )

        else:
            raise ValueError(f"{str(config.dbvec.client)} not yet supported")

        self.logger = config.set_logger(
            "vectorial_db",
            default_context={
                "collection": self.coll_name,
                "embeddings": self.embeddings,
                "db_version": str(self.client.get_version()),
                "db_type": config.dbvec.type.lower(),
            },
        )
        self.logger.info("Class vectorial_db succesfully init")
        self.set_clientdb(flush=True)

    def set_clientdb(self, flush=False):
        """
        Set the clientdb based on the initialized client, collection and embeddings.

        Parameters:
        flush (bool): Whether to delete and recreate the collection. Defaults to False.

        Returns: None

        Raises:
        ValueError: If the client type is not supported
        """
        if isinstance(self.client, chromadb.ClientAPI):
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

    def get_retriever(self, words_number=2) -> VectorStoreRetriever:
        """
        Returns a VectorStoreRetriever instance for this vectorial database.

        This method creates a retriever that can be used to fetch vectors from the underlying database. The retriever is
        bound to this specific database, so all operations will be performed on the data stored in this database.

        :return: A VectorStoreRetriever instance
        """
        self.logger.debug("Return receiver with words_number=%s", str(words_number))
        return self.clientdb.as_retriever(
            search_kwargs={"k": words_number, "fetch_k": 5}, search_type="mmr"
        )

    # Add a document to the collection.

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

        self.collection.add(
            ids=[str(uuid.uuid1())], metadatas=doc.metadata, documents=doc.page_content
        )

    def add_chunked_to_collection(self, chunked_documents, flush_before=False):
        """
        This method adds a chunked list of documents to the collection. It first checks if flushing is required
        and then iterates over each document in the chunked list, adding it to the collection using the add_to_collection method.

        Parameters:
            - chunked_documents: A list of documents that need to be added to the collection
            - flush_before (Optional): If True, the clientdb is flushed before adding the documents

        Returns:
            None
        """
        if flush_before:
            # Flush and recreate the clientdb before adding the chunked documents.
            self.set_clientdb(flush=True)

        for doc in chunked_documents:
            # Add each document to the collection.
            self.add_to_collection(doc)
