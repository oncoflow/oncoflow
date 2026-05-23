from unittest.mock import MagicMock
from src.infrastructure.vectorial.milvus import MilvusDB


def test_milvus_db_init_client_success(mocker):
    """
    TEST EXPLANATION:
    This test verifies that `MilvusDB.init_client` attempts to connect
    using the correct properties and handles database creation securely.
    """
    mock_app_conf = MagicMock()
    mock_app_conf.milvus.host = "localhost"
    mock_app_conf.milvus.port = "19530"
    mock_app_conf.milvus.token = "token123"
    mock_app_conf.milvus.database = "mydb"
    mock_app_conf.dbvec.collection = "test_coll"
    mock_app_conf.llm.type = "ollama"

    mocker.patch("src.infrastructure.vectorial.database.OllamaConnect")

    mock_connections = mocker.patch(
        "src.infrastructure.vectorial.milvus.connections.connect"
    )
    mock_db = mocker.patch("src.infrastructure.vectorial.milvus.db")
    mock_db.list_database.return_value = ["existing_db"]

    mocker.patch.object(MilvusDB, "set_clientdb")
    mocker.patch.object(MilvusDB, "get_version", return_value="1.0")

    # Act
    db_instance = MilvusDB(config=mock_app_conf, coll_prefix="pref")

    # Assert
    mock_connections.assert_called_once_with(host="localhost", port="19530")
    mock_db.list_database.assert_called_once()
    mock_db.create_database.assert_called_once_with("mydb")
    assert db_instance.uri == "http://localhost:19530"
