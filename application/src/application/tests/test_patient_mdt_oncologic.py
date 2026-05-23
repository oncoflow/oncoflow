from unittest.mock import MagicMock
from src.application.patient_mdt_oncologic import PatientMDTOncologic
from src.application.config import AppConfig


def test_patient_mdt_oncologic_dict_to_models_flat(mocker):
    """
    TEST EXPLANATION:
    This test verifies that `dict_to_models` correctly handles the new 'flat' format
    from the Synthesizer and assigns the parsed models to `mtd_datas`.
    """
    # Arrange
    mock_app_conf = MagicMock(spec=AppConfig)
    mock_app_conf.rcp.display_type = "none"  # Avoid mongodb instantiation

    # Create the instance without calling __init__
    instance = PatientMDTOncologic.__new__(PatientMDTOncologic)
    instance.mtd_datas = {}

    # Mock basemodel_list and default_model for simpler testing
    class MockModel:
        __name__ = "MockKey"
        agents = [MagicMock()]

        @classmethod
        def model_validate(cls, value):
            return f"validated_{value}"

    instance.basemodel_list = [MockModel]

    test_dict = {"MockModel": "flat_data"}

    # Act
    instance.dict_to_models(test_dict)

    # Assert
    assert "MockModel" in instance.mtd_datas
    assert instance.mtd_datas["MockModel"] == "validated_flat_data"


def test_patient_mdt_oncologic_insert_datas_in_db(mocker):
    """
    TEST EXPLANATION:
    This test validates that `insert_datas_in_db` correctly deletes old documents if requested
    and inserts new ones through the Mongodb client.
    """
    mock_app_conf = MagicMock(spec=AppConfig)
    mock_app_conf.rcp.display_type = "none"

    instance = PatientMDTOncologic.__new__(PatientMDTOncologic)
    instance.db_client = MagicMock()
    instance.mtd_datas = {"file": "dummy.pdf", "data": "123"}

    # Act
    instance.insert_datas_in_db(replace=True)

    # Assert
    instance.db_client.delete_docs.assert_called_once_with(
        collections=["rcp_info", "rcp_metadata"], filter={"file": "dummy.pdf"}
    )
    instance.db_client.prepare_insert_doc.assert_called_once_with(
        collection="rcp_info", document=instance.mtd_datas
    )
    instance.db_client.insert_docs.assert_called_once()
    instance.db_client.close.assert_called_once()
