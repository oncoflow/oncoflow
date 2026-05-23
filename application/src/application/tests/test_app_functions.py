from unittest.mock import MagicMock
from src.application.app_functions import full_read_mtd_agents, delete_document


def test_full_read_mtd_agents(mocker):
    """
    TEST EXPLANATION:
    This test verifies that `full_read_mtd_agents` correctly initializes its parser,
    reads all models from the document, and inserts data into the database
    by mocking `PatientMDTOncologicForm` methods and checking calls.
    """
    # Arrange
    mock_app_conf = MagicMock()
    mock_logger = MagicMock()
    filename = "dummy.pdf"

    mock_form_class = mocker.patch(
        "src.application.app_functions.PatientMDTOncologicForm"
    )
    mock_form_instance = mock_form_class.return_value

    # Act
    full_read_mtd_agents(mock_app_conf, filename, mock_logger, replace=True)

    # Assert
    mock_logger.info.assert_called_once_with(f"Start reading {filename} ...")
    mock_form_class.assert_called_once_with(config=mock_app_conf, document=filename)
    mock_form_instance.read_all_models.assert_called_once()
    mock_form_instance.insert_datas_in_db.assert_called_once()


def test_delete_document_mongodb_deletes_file(mocker):
    """
    TEST EXPLANATION:
    This test validates that `delete_document` instantiates MongoDB when display_type is 'mongodb',
    calls `delete_docs` appropriately, and deletes the local file if `delete_file` is true and the file exists.
    """
    # Arrange
    mock_app_conf = MagicMock()
    mock_app_conf.rcp.display_type = "mongodb"
    mock_app_conf.rcp.path = "/test/path"

    filename = "test_doc.pdf"

    mock_mongodb_class = mocker.patch("src.application.app_functions.Mongodb")
    mock_mongo_instance = mock_mongodb_class.return_value

    mock_os_path_exists = mocker.patch("os.path.exists", return_value=True)
    mock_os_remove = mocker.patch("os.remove")

    # Act
    delete_document(mock_app_conf, filename, delete_file=True)

    # Assert
    mock_mongodb_class.assert_called_once_with(mock_app_conf)
    mock_mongo_instance.delete_docs.assert_called_once_with(
        collections=["rcp_info", "rcp_metadata"], filter={"file": filename}
    )
    mock_os_path_exists.assert_called_once_with(f"/test/path/{filename}")
    mock_os_remove.assert_called_once_with(f"/test/path/{filename}")
    mock_mongo_instance.close.assert_called_once()


def test_delete_document_not_mongodb(mocker):
    """
    TEST EXPLANATION:
    This test ensures that `delete_document` does nothing when display_type is not 'mongodb',
    preventing unintended database or file deletions.
    """
    # Arrange
    mock_app_conf = MagicMock()
    mock_app_conf.rcp.display_type = "other_db"

    filename = "test_doc.pdf"

    mock_mongodb_class = mocker.patch("src.application.app_functions.Mongodb")
    mock_os_remove = mocker.patch("os.remove")

    # Act
    delete_document(mock_app_conf, filename, delete_file=True)

    # Assert
    mock_mongodb_class.assert_not_called()
    mock_os_remove.assert_not_called()
