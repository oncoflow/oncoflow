from pymongo import MongoClient
from langchain_mongodb import MongoDBAtlasVectorSearch

from src.application.config import AppConfig
from src.infrastructure.vectorial.database import VectorialDataBase

class Mongodb(VectorialDataBase):

    """
    A class for interacting with a MongoDB database using PyMongo.

    This class initializes a connection to a MongoDB database specified by the provided configuration,
    and provides methods for inserting documents into collections, logging information about the
    connection and operations performed, and closing the database connection when done.
    """

    def init_client(self, config=AppConfig) -> None:

        connection_string = "mongodb://"
        if config.mongodb.user is not None:
            connection_string += f"{config.mongodb.user}:{config.mongodb.password}@"
        connection_string += f"{config.mongodb.host}:{config.mongodb.port}"

        self.client = MongoClient(connection_string)
        self.mongo_database = self.client[config.mongodb.vectordatabase]
        self.mongo_collection = self.mongo_database[self.coll_name]
        

    def set_clientdb(
        self,
        flush=False,
    ):
        self.database = self.client[self.coll_name]

        self.clientdb = MongoDBAtlasVectorSearch(
            collection=self.mongo_collection,
            embedding=self.embeddings,
            index_name=f"{self.coll_name}_idx",
            relevance_score_fn="cosine",
        )
        self.clientdb.create_vector_search_index(dimensions=1536)