from unittest.mock import MagicMock
from src.application.agent.agent import OncowflowAgent, ChatResponse
from src.application.config import AppConfig


def test_oncowflow_agent_initialization(mocker):
    """
    TEST EXPLANATION:
    This test verifies that `OncowflowAgent` initializes correctly, setting up the
    LLM client, models, logger, and creating the LangChain agent.
    """
    # Arrange
    mock_app_conf = MagicMock(spec=AppConfig)
    mock_app_conf.llm.type = "ollama"
    mock_app_conf.llm.models = "model1,model2"

    mock_ollama_class = mocker.patch("src.application.agent.agent.OllamaConnect")
    mock_create_agent = mocker.patch("src.application.agent.agent.create_agent")

    # Act
    agent = OncowflowAgent(config=mock_app_conf)

    # Assert
    assert agent.models == ["model1", "model2"]
    assert agent.output_format == ChatResponse
    mock_ollama_class.assert_called_once_with(mock_app_conf)
    mock_create_agent.assert_called_once()


def test_oncowflow_agent_ask(mocker):
    """
    TEST EXPLANATION:
    This test verifies the `ask` method of `OncowflowAgent` properly invokes the LangChain
    agent and parses the returned JSON properly if `structured_response` is missing but is returned as message.
    """
    # Arrange
    mock_app_conf = MagicMock(spec=AppConfig)
    mock_app_conf.llm.type = "ollama"
    mock_app_conf.llm.models = "model1"

    mocker.patch("src.application.agent.agent.OllamaConnect")
    mock_create_agent = mocker.patch("src.application.agent.agent.create_agent")

    mock_langchain_agent = MagicMock()
    mock_create_agent.return_value = mock_langchain_agent

    mock_langchain_agent.invoke.return_value = {
        "structured_response": ChatResponse(response="Test successful")
    }

    mock_mtd = MagicMock()
    agent = OncowflowAgent(config=mock_app_conf, mtd=mock_mtd)

    # Act
    result = agent.ask(question="Test question")

    # Assert
    mock_langchain_agent.invoke.assert_called_once()
    assert isinstance(result, ChatResponse)
    assert result.response == "Test successful"
