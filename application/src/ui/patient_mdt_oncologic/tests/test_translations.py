import streamlit as st
from src.ui.patient_mdt_oncologic.translations import translate
from src.domain.common_ressources import PatientPriority, WHOPerformanceStatus


def test_translation_french():
    # Set session state to French
    st.session_state["language"] = "Français"

    # Test basic labels
    assert translate("First name of the patient") == "Prénom du patient"
    assert translate("first_name") == "Prénom"

    # Test Enum with class labels (WHOPerformanceStatus)
    assert (
        translate(WHOPerformanceStatus._0)
        == "0 - Pas de limitation des activités (normal)"
    )

    # Test standard Enum (PatientPriority)
    assert (
        translate(PatientPriority.urgent)
        == "Priorité haute (Le patient doit être traité de toute urgence)"
    )

    # Test fallback
    assert translate("Some Unknown Label") == "Some Unknown Label"


def test_translation_english():
    # Set session state to English
    st.session_state["language"] = "English"

    # Verify original text is returned
    assert translate("First name of the patient") == "First name of the patient"
    assert translate("first_name") == "first_name"
    assert translate(WHOPerformanceStatus._0) == "No limitation of activities (none)"
    assert translate(PatientPriority.urgent) == "Patient must be treated urgently"
