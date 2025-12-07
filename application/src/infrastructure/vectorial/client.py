from src.infrastructure.vectorial.chromadb import Chromadb
from src.infrastructure.vectorial.mongodb import Mongodb
from src.infrastructure.vectorial.milvus import MilvusDB
from src.infrastructure.vectorial.database import VectorialDataBase
from src.application.config import AppConfig

# Define a class for working with vectorial databases.
class VectorialDataBaseClient:
    client = None

    def __init__(self, config=AppConfig, coll_prefix=None) -> VectorialDataBase :
        if config.dbvec.type.lower() == "chromadb":
            self.vectordb = Chromadb(config, coll_prefix)
        elif config.dbvec.type.lower() == "mongodb":
            self.vectordb = Mongodb(config, coll_prefix)
        elif config.dbvec.type.lower() == "milvus":
            self.vectordb = MilvusDB(config, coll_prefix)
        else:
            raise ValueError(f"{str(config.dbvec.client)} not yet supported")
