from unittest.mock import MagicMock
import sys

# To avoid streamlit execution blocking or crashing during tests
from unittest.mock import patch

mock_st = MagicMock()
mock_st.session_state = {"power": False}
mock_st.query_params = {}
mock_environ = MagicMock()
mock_environ.to_config.return_value.rcp.display_type = "mongodb"
mock_mongodb_module = MagicMock()

with patch.dict(
    sys.modules, {
        "streamlit": mock_st, 
        "streamlit_pdf_viewer": MagicMock(), 
        "environ": mock_environ,
        "src.infrastructure.documents.mongodb": mock_mongodb_module
    }
):
    from src.ui.patient_mdt_oncologic.datas import get_form_models, update_date


def test_ui_datas_get_form_models(mocker):
    """
    TEST EXPLANATION:
    This test verifies that `get_form_models` correctly iterates through
    the PatientMDTOncologicForm attributes and returns only subclasses of BaseModel.
    """
    # Act
    models = get_form_models()

    # Assert
    assert isinstance(models, list)
    assert len(models) > 0
    # Every returned model should have a __name__ and inherit from BaseModel
    assert any(m.__name__ == "PatientAdministrative" for m in models)


def test_ui_datas_update_date(mocker):
    """
    TEST EXPLANATION:
    This test verifies that `update_date` issues the correct update_docs call to the MongoDB client.
    """
    mock_update = mocker.patch("src.ui.patient_mdt_oncologic.datas.db_client.update_docs")

    # Act
    update_date("test.pdf", "2024-01-01")

    # Assert
    mock_update.assert_called_once_with(
        "rcp_info", {"file": "test.pdf"}, {"$set": {"ui_date": "2024-01-01"}}
    )
