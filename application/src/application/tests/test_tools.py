from unittest.mock import MagicMock
import time
from src.application.tools import timed


class DummyClass:
    def __init__(self):
        self.logger = MagicMock()
        self.current_model = "test_model"
        self.additional_pdf = "test_pdf"
        self.metadata = {}

    @timed
    def slow_method(self):
        # Simulate a delay
        time.sleep(0.1)
        return "done"


def test_timed_decorator():
    """
    TEST EXPLANATION:
    This test validates the `@timed` decorator on a class method, ensuring it
    records the execution time, logs it properly, and updates the class metadata
    if the metadata attribute exists and is a dictionary.
    """
    # Arrange
    instance = DummyClass()

    # Act
    result = instance.slow_method()

    # Assert
    assert result == "done"
    instance.logger.info.assert_called()
    assert "slow_method" in instance.metadata
    assert "time" in instance.metadata["slow_method"]
    assert instance.metadata["slow_method"]["model"] == "test_model"
    assert instance.metadata["slow_method"]["ressources"] == "test_pdf"
