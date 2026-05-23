from unittest.mock import MagicMock
from src.infrastructure.documents.mongodb import Mongodb


def test_mongodb_singleton(mocker):
    """
    TEST EXPLANATION:
    This test verifies that `Mongodb` correctly connects to the database via `MongoClient`,
    uses the appropriate configuration, and prepares documents for insertion.
    """
    # Arrange
    mock_app_conf = MagicMock()
    mock_app_conf.mongodb.user = "test_user"
    mock_app_conf.mongodb.password = "pass"
    mock_app_conf.mongodb.host = "localhost"
    mock_app_conf.mongodb.port = "27017"
    mock_app_conf.mongodb.database = "TestDB"

    mocker.patch.object(mock_app_conf, "set_logger")
    mock_mongo_client_class = mocker.patch(
        "src.infrastructure.documents.mongodb.MongoClient"
    )

    # Act
    db = Mongodb(config=mock_app_conf)

    # Assert
    mock_mongo_client_class.assert_called_once_with(
        "mongodb://test_user:pass@localhost:27017"
    )

    # Act 2 (prepare insert)
    db.prepare_insert_doc("test_collection", {"key": "value"})

    # Assert 2
    assert "test_collection" in db.documents_to_insert
    assert db.documents_to_insert["test_collection"][0] == {"key": "value"}
