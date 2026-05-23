from unittest.mock import MagicMock
from src.infrastructure.vectorial.mongodb import Mongodb


def test_mongodb_vectorial_init_client(mocker):
    """
    TEST EXPLANATION:
    This test covers initialization of the Vector DB `Mongodb` client,
    ensuring standard MongoDB client is wrapped correctly for vector searches.
    """
    # Arrange
    mock_app_conf = MagicMock()
    mock_app_conf.mongodb.user = "mongo_user"
    mock_app_conf.mongodb.password = "mongo_pass"
    mock_app_conf.mongodb.host = "127.0.0.1"
    mock_app_conf.mongodb.port = "27017"
    mock_app_conf.mongodb.vectordatabase = "vector_db"
    mock_app_conf.dbvec.collection = "test_coll"
    mock_app_conf.llm.type = "ollama"

    mocker.patch("src.infrastructure.vectorial.database.OllamaConnect")

    # Needs to mock to prevent actual db initialization calls from VectorialDataBase
    mock_mongo_client_class = mocker.patch(
        "src.infrastructure.vectorial.mongodb.MongoClient"
    )

    mocker.patch.object(Mongodb, "set_clientdb")
    mocker.patch("src.infrastructure.vectorial.database.VectorialDataBase.get_version", return_value="1.0")

    # Act
    db = Mongodb(config=mock_app_conf, coll_prefix="prefix")

    # Assert
    mock_mongo_client_class.assert_called_once_with(
        "mongodb://mongo_user:mongo_pass@127.0.0.1:27017"
    )
    # Verify the database and collection assignment are correct
    assert db.mongo_database == mock_mongo_client_class.return_value["vector_db"]
    assert db.mongo_collection == db.mongo_database["prefix_test_coll"]
