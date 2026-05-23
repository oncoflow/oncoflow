import pytest
from datetime import date
from pydantic import ValidationError
from src.domain.common_ressources import (
    ChildPugh,
    ChemotherapyData,
    TreatmentToleranceEnum,
)


def test_child_pugh_model_validation():
    """
    TEST EXPLANATION:
    This test ensures that `ChildPugh` pydantic model enforces types correctly.
    """
    # Arrange & Act
    valid_model = ChildPugh(
        bilirubin=2, albumine=3, prothrombine=50, ascite=False, encephalopathie=False
    )

    # Assert
    assert valid_model.ascite is False
    assert valid_model.bilirubin == 2


def test_child_pugh_model_invalid_type():
    """
    TEST EXPLANATION:
    This test ensures `ValidationError` is raised when missing attributes
    or wrong types are passed to `ChildPugh`.
    """
    with pytest.raises(ValidationError):
        ChildPugh(
            bilirubin="Should Be Int", albumine=3
        )  # Missing other required fields


def test_chemotherapy_data_validation():
    """
    TEST EXPLANATION:
    This test verifies that `ChemotherapyData` properly instantiates objects
    with ENUM properties.
    """
    model = ChemotherapyData(
        chemotherapy_name="FOLFIRINOX",
        chemotherapy_start_date=date(2023, 1, 1),
        chemotherapy_end_date=None,
        chemotherapy_tolerance=TreatmentToleranceEnum.good,
    )

    assert model.chemotherapy_tolerance == "Good"
    assert model.chemotherapy_start_date.year == 2023
