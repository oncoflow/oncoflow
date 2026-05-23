import logging
from unittest.mock import patch
from src.application.config import AppConfig


def test_app_config_initialization(mocker):
    """
    TEST EXPLANATION:
    This test verifies that `AppConfig` initializes correctly using the default values
    provided in the `environ` definitions when no conflicting environment variables are set.
    """
    with patch("os.environ", {}):
        # We need to mock os.path.dirname to ensure the path validator passes without requiring a real dir setup
        mocker.patch(
            "src.application.config.Path.exists", return_value=True
        )
        config = AppConfig.from_environ()

        # Test basic loading
        assert config.logs.level == "INFO"
        assert config.rcp.doc_type == "docling"
        assert config.llm.type == "Ollama"


def test_set_logger(mocker):
    """
    TEST EXPLANATION:
    This test verifies the `set_logger` method successfully returns a valid configured logger,
    incorporating the optional default contexts and handlers as configured in `AppConfig`.
    """
    with patch("os.environ", {}):
        mocker.patch("src.application.config.Path.exists", return_value=True)
        config = AppConfig.from_environ()

        logger = config.set_logger(
            name="test_logger", default_context={"user": "admin"}
        )

        assert logger.name == "test_logger"
        assert logger.level == logging.INFO
        assert len(logger.handlers) == 1
        assert isinstance(logger.handlers[0], logging.StreamHandler)
