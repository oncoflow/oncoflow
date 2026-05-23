from unittest.mock import MagicMock
from src.infrastructure.parsers.ollama_ocr import OllamaOcrDocumentLoader


def test_ollama_ocr_document_loader(mocker):
    """
    TEST EXPLANATION:
    This test verifies that `OllamaOcrDocumentLoader.load()` properly extracts text
    using the `OCRProcessor` and returns a `Document`.
    """
    # Arrange
    mock_app_conf = MagicMock()
    mock_app_conf.llm.ocrmodels = "test-ocr-model"
    mock_app_conf.llm.url = "http://localhost"
    mock_app_conf.llm.port = "11434"

    mock_ocr_processor_class = mocker.patch(
        "src.infrastructure.parsers.ollama_ocr.OCRProcessor"
    )
    mock_ocr_instance = mock_ocr_processor_class.return_value
    mock_ocr_instance.process_image.return_value = "Extracted Text"

    loader = OllamaOcrDocumentLoader(file_path="test.jpg", config=mock_app_conf)

    # Act
    documents = loader.load()

    # Assert
    assert len(documents) == 1
    assert documents[0].page_content == "Extracted Text"
    assert documents[0].metadata["source"] == "test.jpg"
    mock_ocr_instance.process_image.assert_called_once_with(
        image_path="test.jpg", format_type="text", language="fr"
    )
