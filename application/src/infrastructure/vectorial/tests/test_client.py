from unittest.mock import MagicMock
from src.infrastructure.vectorial.client import VectorialDataBaseClient


def test_vectorial_database_client_chroma(mocker):
    """
    TEST EXPLANATION:
    This test verifies that the factory class `VectorialDataBaseClient` successfully
    returns a `Chromadb` instance when configured with `type = "chromadb"`.
    """
    mock_app_conf = MagicMock()
    mock_app_conf.dbvec.type = "chromadb"

    mock_chromadb_class = mocker.patch("src.infrastructure.vectorial.client.Chromadb")

    # Act
    client = VectorialDataBaseClient(config=mock_app_conf, coll_prefix="test")

    # Assert
    mock_chromadb_class.assert_called_once_with(mock_app_conf, "test")
    assert client.vectordb == mock_chromadb_class.return_value
