import uuid


from langchain_core.vectorstores import VectorStoreRetriever

from src.application.config import AppConfig
from src.infrastructure.llm.ollama import OllamaConnect


class VectorialDataBase:
    client = None

    # Initialize the client, collection and embeddings based on configuration.
    """Initialize the client, collection and embeddings based on configuration."""

    def __init__(self, config=AppConfig, coll_prefix=None):

        if coll_prefix is None:
            self.coll_name = config.dbvec.collection
        else:
            self.coll_name = f"{coll_prefix}_{config.dbvec.collection}"

        if config.llm.type.lower() == "ollama":
            llm_client = OllamaConnect(config)
        else:
            raise ValueError(f"{config.llm.type} not yet supported")
        self.llm_embeddings = llm_client.embedding

        self.config = config
        self.embeddings = self.get_embedding()
        self.init_client(config)
        self.set_clientdb()

        self.logger = config.set_logger(
            "vectorial_db",
            default_context={
                "collection": self.coll_name,
                "embeddings": self.embeddings,
                "db_version": str(self.get_version()),
                "db_type": config.dbvec.type.lower(),
            },
        )

        self.logger.info("Class vectorial_db succesfully init")

    def init_client(self, config=AppConfig):
        """
        Set init client
        """
        return None

    def get_version(self) -> str:
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
