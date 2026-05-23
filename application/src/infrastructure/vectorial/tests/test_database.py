from unittest.mock import MagicMock
from src.infrastructure.vectorial.database import VectorialDataBase


def test_vectorial_database_init(mocker):
    """
    TEST EXPLANATION:
    This test validates that `VectorialDataBase` appropriately initializes
    the LLM connector for embeddings and configures its prefix collection name.
    """
    # Arrange
    mock_app_conf = MagicMock()
    mock_app_conf.dbvec.collection = "test_coll"
    mock_app_conf.llm.type = "ollama"

    mocker.patch.object(mock_app_conf, "set_logger")
    mocker.patch(
        "src.infrastructure.vectorial.database.OllamaConnect"
    )

    mock_init_client = mocker.patch.object(VectorialDataBase, "init_client")
    mock_set_clientdb = mocker.patch.object(VectorialDataBase, "set_clientdb")
    mock_set_clientdb = mocker.patch.object(VectorialDataBase, "set_clientdb")
    mocker.patch(
        "src.infrastructure.vectorial.database.VectorialDataBase.get_version", return_value="1.0"
    )

    # Act
    db = VectorialDataBase(config=mock_app_conf, coll_prefix="prefix")

    # Assert
    assert db.coll_name == "prefix_test_coll"
    mock_init_client.assert_called_once_with(mock_app_conf)
    mock_set_clientdb.assert_called_once()
