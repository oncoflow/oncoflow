from unittest.mock import MagicMock
import sys
from datetime import datetime

# To avoid streamlit execution blocking or crashing during tests
from unittest.mock import patch

mock_st = MagicMock()
mock_st.session_state = {"power": False, "list_sort_by": "date", "list_sort_ascending": True}
mock_st.query_params = {"file": "test.pdf"}
mock_mongodb_module = MagicMock()

with patch.dict(sys.modules, {"streamlit": mock_st, "src.infrastructure.documents.mongodb": mock_mongodb_module}):
    from src.ui.patient_mdt_oncologic.cards import get_rcp_data


def test_ui_cards_get_rcp_data(mocker):
    """
    TEST EXPLANATION:
    This test ensures that `get_rcp_data` correctly formats data from MongoDB
    `rcp_info` items into the required list format for Streamlit cards display.
    """
    mock_db_client = mocker.patch("src.ui.patient_mdt_oncologic.cards.db_client")
    mock_db_client.database = {"rcp_info": MagicMock()}

    # Mocking single patient document
    mock_db_client.database["rcp_info"].find.return_value = [
        {
            "file": "test.pdf",
            "ui_date": datetime(2024, 1, 1),
            "PatientAdministrative": {
                "first_name": "Jean",
                "last_name": "Dupont",
                "date_rcp": datetime(2024, 1, 1),
            },
            "ExpertAnswer": {
                "pancreas expert": {
                    "expert_relevant": True,
                    "patient_priority": "urgent",
                }
            },
            "MTDCompleted": {"mtd_complete": {"what_missing": ["biology"]}},
        }
    ]

    # Act
    cards = get_rcp_data()

    # Assert
    print("Cards length: ", len(cards))
    if len(cards) == 0:
        import sys
        print("db_client type:", type(sys.modules["src.ui.patient_mdt_oncologic.cards"].db_client))
        print("hasattr database:", hasattr(sys.modules["src.ui.patient_mdt_oncologic.cards"].db_client, "database"))
    assert len(cards) == 1
    assert cards[0]["patient"] == "Jean Dupont"
    assert cards[0]["urgency"] == "Urgent"
    assert "pancreas expert" in cards[0]["experts"]
    assert "biology" in cards[0]["missing"]
    assert cards[0]["file"] == "test.pdf"
