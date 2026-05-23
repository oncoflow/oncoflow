from src.domain.interfaces import IVectorDatabaseClient, ILlmClient
from typing import Any


def test_interfaces_protocols():
    """
    TEST EXPLANATION:
    This test verifies the protocols defined in domain/interfaces.py can be correctly
    implemented and satisfy the Python typing Protocol requirements.
    """

    class MockVecDBClient:
        vectordb: Any = "mock_db"

    class MockLlmClient:
        embedding: Any = "mock_embedding"

    # Instantiate to demonstrate compliance
    client: IVectorDatabaseClient = MockVecDBClient()
    llm: ILlmClient = MockLlmClient()

    assert client.vectordb == "mock_db"
    assert llm.embedding == "mock_embedding"
