from unittest.mock import MagicMock
from src.application.agent.tools import (
    search_on_mtd,
    search_on_ressources,
    Context,
)


def test_search_on_mtd():
    """
    TEST EXPLANATION:
    This test verifies that `search_on_mtd` correctly uses the context's vector database client
    to retrieve documents and correctly serializes the output for the LLM.
    """
    # Arrange
    mock_doc = MagicMock()
    mock_doc.metadata = {"page": 1}
    mock_doc.page_content = "This is a test document content."

    mock_reader = MagicMock()
    mock_reader.vecdb.clientdb.max_marginal_relevance_search.return_value = [mock_doc]

    mock_logger = MagicMock()

    context: Context = {
        "reader": mock_reader,
        "additionnal_readers": [],
        "logger": mock_logger,
    }

    runtime = MagicMock()
    runtime.context = context

    # Act
    serialized, retrieved_docs = search_on_mtd.func(
        runtime=runtime, query="test query", config={"callbacks": []}
    )

    # Assert
    assert len(retrieved_docs) == 1
    assert (
        "Source: {'page': 1}\nContent: This is a test document content." in serialized
    )
    mock_reader.vecdb.clientdb.max_marginal_relevance_search.assert_called_once_with(
        "test query", k=4, fetch_k=20, param=None, expr=None, timeout=None, config={"callbacks": []}
    )


def test_search_on_ressources():
    """
    TEST EXPLANATION:
    This test verifies that `search_on_ressources` checks all available additional readers
    and correctly appends all results from their vector databases.
    """
    # Arrange
    mock_doc_1 = MagicMock()
    mock_doc_1.metadata = {"source": "TNCD"}
    mock_doc_1.page_content = "Resource piece 1."

    mock_doc_2 = MagicMock()
    mock_doc_2.metadata = {"source": "Guidelines"}
    mock_doc_2.page_content = "Resource piece 2."

    mock_reader_1 = MagicMock()
    mock_reader_1.vecdb.clientdb.max_marginal_relevance_search.return_value = [
        mock_doc_1
    ]

    mock_reader_2 = MagicMock()
    mock_reader_2.vecdb.clientdb.max_marginal_relevance_search.return_value = [
        mock_doc_2
    ]

    mock_logger = MagicMock()

    context: Context = {
        "reader": MagicMock(),
        "additionnal_readers": [mock_reader_1, mock_reader_2],
        "logger": mock_logger,
    }

    runtime = MagicMock()
    runtime.context = context

    # Act
    serialized, retrieved_docs = search_on_ressources.func(
        runtime=runtime, query="guidelines test", config={"callbacks": []}
    )

    # Assert
    assert len(retrieved_docs) == 2
    assert "Source: {'source': 'TNCD'}" in serialized
    assert "Source: {'source': 'Guidelines'}" in serialized
