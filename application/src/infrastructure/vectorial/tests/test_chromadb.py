from unittest.mock import MagicMock
from src.infrastructure.vectorial.chromadb import Chromadb


def test_chromadb_init_client(mocker):
    """
    TEST EXPLANATION:
    This test verifies that `Chromadb` overrides `init_client` to instantiate
    chromadb.HttpClient or PersistentClient based on configuration appropriately.
    """
    # Arrange
    mock_app_conf = MagicMock()
    mock_app_conf.dbvec.collection = "test_coll"
    mock_app_conf.llm.type = "ollama"
    mock_app_conf.chromadb.client = "HttpClient"
    mock_app_conf.chromadb.host = "localhost"
    mock_app_conf.chromadb.port = "8000"

    mocker.patch("src.infrastructure.vectorial.database.OllamaConnect")
    mock_chroma_http_client = mocker.patch(
        "src.infrastructure.vectorial.chromadb.chromadb.HttpClient"
    )

    mocker.patch("src.infrastructure.vectorial.chromadb.create_langchain_embedding")

    mocker.patch.object(Chromadb, "set_clientdb")
    mocker.patch("src.infrastructure.vectorial.database.VectorialDataBase.get_version", return_value="1.0")

    # Act
    db = Chromadb(config=mock_app_conf)
    
    # Assert
    assert db is not None
    mock_chroma_http_client.assert_called_once_with(host="localhost", port="8000")
