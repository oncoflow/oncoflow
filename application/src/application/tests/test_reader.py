from unittest.mock import MagicMock, patch
from src.application.reader import DocumentReader
from src.application.config import AppConfig


def test_document_reader_init(mocker):
    """
    TEST EXPLANATION:
    This test ensures that `DocumentReader` correctly initializes,
    setting up the document path, checking the configuration,
    and instantiating the vector DB and LLM clients.
    """
    # Arrange
    mock_app_conf = MagicMock(spec=AppConfig)
    mock_app_conf.rcp.path = "/fake/path"
    mock_app_conf.rcp.doc_type = "docling"
    mock_app_conf.llm.type = "Ollama"
    mock_app_conf.llm.embeddings = "fake-embeddings"

    # Mocking external clients to avoid actual instantiation
    mock_vecdb_instance = MagicMock()
    mock_vecdb_class = mocker.patch(
        "src.application.reader.VectorialDataBaseClient",
        return_value=MagicMock(vectordb=mock_vecdb_instance),
    )

    mock_llm_instance = MagicMock()
    mock_llm_instance.embedding = "mocked-embedding"
    mock_llm_class = mocker.patch(
        "src.application.reader.OllamaConnect", return_value=mock_llm_instance
    )

    mocker.patch.object(mock_app_conf, "set_logger")

    # Act
    reader = DocumentReader(
        config=mock_app_conf, document="dummy.pdf", document_type="mtd"
    )

    # Assert
    assert reader.document_path == "/fake/path/dummy.pdf"
    assert reader.vecdb == mock_vecdb_instance
    assert reader.embeddings == "mocked-embedding"
    mock_vecdb_class.assert_called_once()
    mock_llm_class.assert_called_once()


@patch("src.application.reader.DocumentReader._load_document")
def test_document_reader_read_document(mock_load_document, mocker):
    """
    TEST EXPLANATION:
    This test validates the `read_document` method, ensuring it calls
    `_load_document` properly and stores the resulting chunks into the vector database.
    """
    # Arrange
    # Simplest initialization using mocked clients
    mock_app_conf = MagicMock(spec=AppConfig)
    mock_app_conf.rcp.path = "/fake/path"

    mock_vecdb_client = MagicMock()
    mock_llm_client = MagicMock()

    mocker.patch.object(mock_app_conf, "set_logger")

    reader = DocumentReader(
        config=mock_app_conf,
        document="dummy.pdf",
        vecdb_client=mock_vecdb_client,
        llm_client=mock_llm_client,
    )

    mock_load_document.return_value = ["chunk1", "chunk2"]

    # Act
    reader.read_document()

    # Assert
    mock_load_document.assert_called_once_with("/fake/path/dummy.pdf")
    mock_vecdb_client.add_chunked_to_collection.assert_called_once_with(
        ["chunk1", "chunk2"], flush_before=True
    )
