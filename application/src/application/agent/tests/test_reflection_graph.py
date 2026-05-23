from unittest.mock import MagicMock
from src.application.agent.reflection_graph import run_reflection_graph


def test_run_reflection_graph_success(mocker):
    """
    TEST EXPLANATION:
    This test simulates the basic execution of `run_reflection_graph`, ensuring
    that the StateGraph is compiled and invoked properly, returning the final output.
    """
    # Arrange
    mock_config = MagicMock()
    mock_mtd = MagicMock()
    mock_logger = MagicMock()

    mock_model = MagicMock()
    mock_model.agents = []  # No experts to run
    mock_model.question = "Test Question?"

    mock_synthesizer_instance = MagicMock()
    mock_synthesizer_instance.ask.return_value.json.return_value = (
        '{"final_key": "synthesized data"}'
    )

    mocker.patch(
        "src.application.agent.reflection_graph.Agents.Synthesizer_agent",
        return_value=mock_synthesizer_instance,
    )

    # Mocking LangGraph elements because the environment or test suite might not have it properly installed
    # It focuses on verifying our code interacts correctly.
    mock_stategraph_class = mocker.patch("langgraph.graph.StateGraph")
    mock_workflow_instance = mock_stategraph_class.return_value
    mock_app_instance = mock_workflow_instance.compile.return_value
    mock_app_instance.invoke.return_value = {
        "final_result": {"final_key": "synthesized data"}
    }

    # Act
    result = run_reflection_graph(
        config=mock_config, mtd=mock_mtd, model=mock_model, logger=mock_logger
    )

    # Assert
    assert result == {"final_key": "synthesized data"}
    mock_workflow_instance.add_node.assert_called()
    mock_workflow_instance.compile.assert_called_once()
    mock_app_instance.invoke.assert_called_once()


def test_run_reflection_graph_langgraph_missing(mocker):
    """
    TEST EXPLANATION:
    This test verifies that `run_reflection_graph` returns an empty dictionary
    gracefully if `langgraph` fails to import.
    """
    # Arrange
    mock_config = MagicMock()
    mock_mtd = MagicMock()
    mock_model = MagicMock()
    mock_logger = MagicMock()

    # Force ImportError
    import builtins

    real_import = builtins.__import__

    def mock_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "langgraph.graph":
            raise ImportError("Mocked ImportError")
        return real_import(name, globals, locals, fromlist, level)

    mocker.patch("builtins.__import__", side_effect=mock_import)

    # Act
    result = run_reflection_graph(
        config=mock_config, mtd=mock_mtd, model=mock_model, logger=mock_logger
    )

    # Assert
    assert result == {}
    mock_logger.error.assert_called_once_with(
        "LangGraph is not installed. Please install it."
    )
