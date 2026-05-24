import uuid


from typing import Any

from langchain_core.vectorstores import VectorStore, VectorStoreRetriever

from src.application.config import AppConfig
from src.infrastructure.llm.factory import get_llm_client
# Legacy import to support existing patch-based unit tests


class VectorialDataBase:
    client: Any = None
    clientdb: VectorStore
    collection: Any = None

    # Initialize the client, collection and embeddings based on configuration.
    """Initialize the client, collection and embeddings based on configuration."""

    def __init__(self, config: AppConfig, coll_prefix: str | None = None):

        embedding_suffix = (
            config.llm.embeddings.replace("/", "_").replace(":", "_").replace("-", "_")
        )
        if coll_prefix is None:
            self.coll_name = f"{config.dbvec.collection}_{embedding_suffix}"
        else:
            self.coll_name = (
                f"{coll_prefix}_{config.dbvec.collection}_{embedding_suffix}"
            )

        llm_client = get_llm_client(config)
        self.llm_embeddings = llm_client.embedding

        self.config = config
        self.embeddings = self.get_embedding()

        # Initialize the logger early so that subclass init_client calls can safely log warning/retry messages
        self.logger = config.set_logger(
            "vectorial_db",
            default_context={
                "collection": self.coll_name,
                "embeddings": self.embeddings,
                "db_type": config.dbvec.type.lower(),
            },
        )

        self.init_client(config)
        self.set_clientdb()

        db_version = "unknown"
        try:
            db_version = self.get_version()
        except Exception:
            pass

        self.logger.info(
            "Class vectorial_db succesfully init - server version: %s", str(db_version)
        )

    def init_client(self, config: AppConfig):
        """
        Set init client
        """
        return None

    def get_embedding(self) -> Any:
        """Get embedding function."""
        raise NotImplementedError("Subclasses must implement get_embedding")

    def get_version(self) -> str:
        if self.client is None:
            return "unknown"
        return self.client.get_version()

    def set_clientdb(self, flush=False):
        """
        Set the clientdb based on the initialized client, collection and embeddings.

        Parameters:
        flush (bool): Whether to delete and recreate the collection. Defaults to False.

        Returns: None

        Raises:
        ValueError: If the client type is not supported
        """
        return None

    def get_retriever(self, words_number=2) -> VectorStoreRetriever:
        """
        Returns a VectorStoreRetriever instance for this vectorial database.

        This method creates a retriever that can be used to fetch vectors from the underlying database. The retriever is
        bound to this specific database, so all operations will be performed on the data stored in this database.

        :return: A VectorStoreRetriever instance
        """
        self.logger.debug("Return receiver with words_number=%s", str(words_number))
        return self.clientdb.as_retriever(
            # search_kwargs={"k": words_number, "fetch_k": 5}, search_type="mmr"
            search_type="similarity_score_threshold",
            search_kwargs={"score_threshold": 0.8},
        )

    def is_indexed(self) -> bool:
        """
        Checks if the collection exists and has indexed entities.
        """
        return False

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
        # chunked_documents = filter_complex_metadata(chunked_documents)
        for doc in chunked_documents:
            # Add each document to the collection.
            self.add_to_collection(doc)
