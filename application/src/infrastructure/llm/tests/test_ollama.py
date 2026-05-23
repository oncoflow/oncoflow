from unittest.mock import MagicMock
from src.infrastructure.llm.ollama import OllamaConnect


def test_ollama_connect_init_and_chat(mocker):
    """
    TEST EXPLANATION:
    This test verifies that `OllamaConnect` correctly initializes its `ollama.Client`
    and checks the connection. It also ensures the `chat` method instantiates
    a `ChatOllama` LLM appropriately.
    """
    # Arrange
    mock_app_conf = MagicMock()
    mock_app_conf.llm.url = "http://test"
    mock_app_conf.llm.port = "1234"
    mock_app_conf.llm.embeddings = "test-embed"

    mock_ollama_client_class = mocker.patch(
        "src.infrastructure.llm.ollama.ollama.Client"
    )
    mock_client_instance = mock_ollama_client_class.return_value
    mock_client_instance.list.return_value = {"models": [{"model": "m1"}]}

    mocker.patch("src.infrastructure.llm.ollama.OllamaEmbeddings")
    mock_chat_ollama = mocker.patch("src.infrastructure.llm.ollama.ChatOllama")

    # Act
    connector = OllamaConnect(config=mock_app_conf)

    # Assert
    mock_ollama_client_class.assert_called_once_with(host="http://test:1234")
    mock_client_instance.list.assert_called_once()

    # Act 2 (chat)
    connector.chat(model="m1", output=None, temperature=0.5)

    # Assert 2
    mock_chat_ollama.assert_called_once_with(
        base_url="http://test:1234",
        format="json",
        model="m1",
        temperature=0.5,
        validate_model_on_init=True,
    )
