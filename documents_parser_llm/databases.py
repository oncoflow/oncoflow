import chromadb
import uuid

from langchain_chroma import Chroma

from langchain_core.vectorstores import VectorStoreRetriever

from langchain_community.embeddings import SentenceTransformerEmbeddings

from config import AppConfig


class vectorial_db:
    client = None
 
    def __init__(self, config=AppConfig):
        if config.dbvec.type.lower() == "chromadb":
            if config.dbvec.client == "HttpClient":
                self.client = chromadb.HttpClient(
                    host=config.dbvec.host, port=config.dbvec.port)
            elif config.dbvec.client == "PersistentClient":
                 self.client = chromadb.PersistentClient()
            self.client.clear_system_cache()
            self.collection = self.client.get_or_create_collection(config.dbvec.collection)
            self.embeddings = SentenceTransformerEmbeddings(model_name=config.dbvec.model)     
        else:
            raise ValueError(
                f"{str(config.dbvec.client)} not yet supported")

        self.set_clientdb()
   
    def set_clientdb(self, flush=False):
        if isinstance(self.client, chromadb.ClientAPI):
            if flush:
                coll_name = self.collection.name
                self.client.delete_collection(coll_name)
                self.collection = self.client.get_or_create_collection(coll_name)
            self.clientdb = Chroma(
                client=self.client,
                collection_name=self.collection.name,
                embedding_function=self.embeddings,
            )
            
    def get_retreiver(self) -> VectorStoreRetriever:
        return self.clientdb.as_retriever()
        
    def add_to_collection(self, doc, flush_before=False):
        if flush_before:
            self.set_clientdb(flush=True)
        
        self.collection.add(
                ids=[str(uuid.uuid1())], metadatas=doc.metadata, documents=doc.page_content)
        
    def add_chunked_to_collection(self, chunked_documents, flush_before=False):
        if flush_before:
            self.set_clientdb(flush=True)
        for doc in chunked_documents:
            self.add_to_collection(doc)