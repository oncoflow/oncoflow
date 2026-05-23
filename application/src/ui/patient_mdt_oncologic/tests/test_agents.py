from unittest.mock import MagicMock
from src.ui.patient_mdt_oncologic.agents import read


def test_ui_agents_read(mocker):
    """
    TEST EXPLANATION:
    This test verifies that the `read` function in the UI agents script correctly
    instantiates a `DocumentReader` with the given configuration and calls `read_document`.
    The streamlit components like `st.spinner` and `st.toast` are mocked out.
    """
    # Arrange
    # Mocking out the entire streamlit script execution isn't possible normally as it executes on import
    # but since `read` is a function, we can test it directly.
    mocker.patch(
        "src.ui.patient_mdt_oncologic.agents.st"
    )  # Mock Streamlit globally in that module

    mock_app_conf = MagicMock()
    mock_reader_class = mocker.patch(
        "src.ui.patient_mdt_oncologic.agents.DocumentReader"
    )
    mock_reader_instance = mock_reader_class.return_value

    # Act
    read("TNCD.pdf", mock_app_conf)

    # Assert
    mock_reader_class.assert_called_once_with(
        mock_app_conf, document="TNCD.pdf", document_type="ressource"
    )
    mock_reader_instance.read_document.assert_called_once()
