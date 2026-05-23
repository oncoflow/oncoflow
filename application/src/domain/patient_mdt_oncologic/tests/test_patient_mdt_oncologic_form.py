import pytest
from datetime import datetime
from pydantic import ValidationError
from src.domain.common_ressources import Gender
from src.domain.patient_mdt_oncologic.patient_mdt_oncologic_form import (
    PatientMDTOncologicForm,
)


def test_patient_administrative_dates_coherence():
    """
    TEST EXPLANATION:
    This test verifies the `@model_validator` in `PatientAdministrative` properly
    checks that the `date_birth` is strictly before the `date_rcp`.
    """
    # Arrange & Act
    valid_model = PatientMDTOncologicForm.PatientAdministrative(
        first_name="Jean",
        last_name="Dupont",
        age=50,
        date_birth=datetime(1974, 1, 1),
        date_rcp=datetime(2024, 1, 1),
        gender=Gender.male,
    )

    # Assert
    assert valid_model.date_birth.year == 1974
    assert valid_model.date_rcp.year == 2024


def test_patient_administrative_dates_incoherent():
    """
    TEST EXPLANATION:
    This test verifies that an error is raised by `PatientAdministrative`
    when `date_birth` is after `date_rcp`.
    """
    with pytest.raises(
        ValidationError, match="Date of birth must be before Date of RCP"
    ):
        PatientMDTOncologicForm.PatientAdministrative(
            first_name="Jean",
            last_name="Dupont",
            age=50,
            date_birth=datetime(2025, 1, 1),  # Birth after RCP
            date_rcp=datetime(2024, 1, 1),
            gender=Gender.male,
        )
