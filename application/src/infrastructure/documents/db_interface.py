from src.application.config import AppConfig
from src.infrastructure.documents.mongodb import Mongodb

app_conf = AppConfig()


def get_db():
    """
    FastAPI dependency generator that yields the database client connection
    and ensures it's closed after the request is finished.
    """
    if app_conf.rcp.display_type == "mongodb":
        client = Mongodb(app_conf)
        try:
            yield client
        finally:
            client.close()
    else:
        yield None
