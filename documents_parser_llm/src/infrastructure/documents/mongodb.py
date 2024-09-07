from pymongo import MongoClient

from src.application.config import AppConfig


class Mongodb:

    def __init__(self, config=AppConfig) -> None:

        self.logger = config.set_logger(
            "mongodb",
            default_context={
                "host": config.mongodb.host,
                "user": config.mongodb.user,
                "database": config.mongodb.database,
            },
        )
        connection_string = "mongodb://"
        if config.mongodb.user is not None:
            connection_string += f"{config.mongodb.user}:{config.mongodb.password}"
        connection_string += config.mongodb.host

        self.client = MongoClient(connection_string)
        self.database = self.client[config.mongodb.database]
        
        self.documents_to_insert = {}

        self.logger.info("Succefully init")
        
    def prepare_insert_doc(self, collection, document):
        if collection not in self.documents_to_insert:
            self.documents_to_insert[collection] = []
        self.documents_to_insert[collection].append(document)

        
    def insert_docs(self):
        self.logger.info("Start inserting documents")
        self.logger.debug("List of document to insert : %s", self.documents_to_insert)
        for collection, documents in self.documents_to_insert.items():
            collection = self.database[collection]
            collection.insert_many(documents)
        self.logger.info("Success inserting documents")
        