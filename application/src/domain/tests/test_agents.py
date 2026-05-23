from unittest.mock import MagicMock
from src.domain.agents import Agents


def test_agents_list_initialization():
    """
    TEST EXPLANATION:
    This test verifies that the `Agents` class correctly initializes its `list` attribute,
    cataloging available agent classes (Administratives, Synthesizer, Experts).
    """
    agents = Agents()
    # the list shouldn't contain the base 'Expert_model' due to logic `"_model" not in cls.__name__`
    assert "Administrative" in agents.list
    assert "synthesizer" in agents.list
    assert "pancreas expert" in agents.list


def test_expert_model_prompt_formatting(mocker):
    """
    TEST EXPLANATION:
    This test verifies that `Expert_model` uses its `expert_type` string
    property to correctly format its `system_prompt`.
    """
    # Arrange
    mock_app_conf = MagicMock()
    mock_app_conf.llm.type = "ollama"
    mock_app_conf.llm.models = "model1"

    mocker.patch("src.application.agent.agent.OllamaConnect")
    mocker.patch("src.application.agent.agent.create_agent")
    mocker.patch("src.application.agent.agent.DocumentReader")

    # Access the specific Pancreas expert class directly to test inheritance mapping
    pancreas_expert = Agents.Pancreas_expert_agent(config=mock_app_conf)

    # Assert
    assert "pancreas diseases" in pancreas_expert.system_prompt
    assert "pancreas expert" == pancreas_expert.agent_name
    assert "TNCDPANCREAS.pdf" in pancreas_expert.ressources
