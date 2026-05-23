from unittest.mock import MagicMock
from src.infrastructure.parsers.openparse import OpenParseDocumentLoader


def test_openparse_document_loader_lazy_load(mocker):
    """
    TEST EXPLANATION:
    This test checks the `lazy_load` method returning Documents out of
    `openparse` parsing nodes.
    """
    # Arrange
    mock_parser_class = mocker.patch(
        "src.infrastructure.parsers.openparse.openparse.DocumentParser"
    )
    mock_parser_instance = mock_parser_class.return_value

    mock_node = MagicMock()
    mock_node.text = "Node Text"
    mock_node.tokens = 10
    mock_node.num_pages = 1
    mock_node.node_id = "node1"
    mock_node.start_page = 1
    mock_node.end_page = 1

    mock_parsed_doc = MagicMock()
    mock_parsed_doc.nodes = [mock_node]
    mock_parser_instance.parse.return_value = mock_parsed_doc

    mock_pdf_class = mocker.patch("src.infrastructure.parsers.openparse.openparse.Pdf")
    mock_pdf_instance = mock_pdf_class.return_value

    loader = OpenParseDocumentLoader(file_path="test.pdf")

    # Act
    documents = list(loader.lazy_load())

    # Assert
    assert len(documents) == 1
    assert documents[0].page_content == "Node Text"
    assert documents[0].metadata["source"] == "test.pdf"
    assert documents[0].metadata["node_id"] == "node1"

    mock_pdf_instance.export_with_bboxes.assert_called_once()
